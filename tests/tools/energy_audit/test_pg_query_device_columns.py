"""Schema-aware behavior for generic device-table queries."""

import re

import psycopg2.errors
import pytest

from tools.energy_audit.pg_query import PgDataQuery


TABLE = "ts_institution_device_light"


def _query(columns, version_code=None):
    query = PgDataQuery.__new__(PgDataQuery)
    query.version_code = PgDataQuery.normalize_version_code(version_code)
    query.connection = None
    query._device_table_columns = {TABLE: frozenset(columns)}
    captured = []

    def execute(sql, params=None):
        captured.append((sql, params))
        return []

    query._execute = execute
    return query, captured


def test_partition_omits_power_unit_when_column_is_absent():
    query, captured = _query(
        {
            "id",
            "deleted",
            "customer_id",
            "device_name",
            "power",
            "is_draft",
            "version_code",
        },
    )

    query._get_device_by_table(TABLE, customer_id=3)

    sql, params = captured[-1]
    assert "ROW_NUMBER()" in sql
    assert "t.device_name" in sql
    assert re.search(r"\bt\.power\b", sql)
    assert "t.power_unit" not in sql
    assert "t.customer_id = %s" in sql
    assert params == (3,)


def test_partition_omits_power_and_power_unit_when_both_are_absent():
    query, captured = _query(
        {"id", "deleted", "customer_id", "device_name", "is_draft", "version_code"},
    )

    query._get_device_by_table(TABLE)

    sql, _ = captured[-1]
    assert "t.device_name" in sql
    assert not re.search(r"\bt\.power\b", sql)
    assert "t.power_unit" not in sql


def test_partition_uses_id_fallback_when_device_name_is_absent():
    query, captured = _query(
        {"id", "deleted", "customer_id", "is_draft", "version_code"},
    )

    query._get_device_by_table(TABLE)

    sql, _ = captured[-1]
    assert "t.device_name" not in sql
    assert "'id_' || t.id::text" in sql


def test_unversioned_table_uses_plain_filtered_select():
    query, captured = _query({"id", "deleted", "customer_id", "device_name"})

    query._get_device_by_table(TABLE, customer_id=7)

    sql, params = captured[-1]
    assert sql.startswith("SELECT *")
    assert "ROW_NUMBER()" not in sql
    assert "t.deleted = 0" in sql
    assert "t.customer_id = %s" in sql
    assert params == (7,)


def test_snapshot_lock_is_rejected_for_unversioned_table():
    query, captured = _query(
        {"id", "deleted", "customer_id", "device_name"},
        version_code="PL2026080401",
    )

    with pytest.raises(ValueError, match="version_code"):
        query._get_device_by_table(TABLE)

    assert captured == []


def test_permission_error_propagates_without_fallback_query():
    query, captured = _query(
        {
            "id",
            "deleted",
            "customer_id",
            "device_name",
            "power",
            "is_draft",
            "version_code",
        },
    )

    def deny(sql, params=None):
        captured.append((sql, params))
        raise psycopg2.errors.InsufficientPrivilege("denied")

    query._execute = deny

    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        query._get_device_by_table(TABLE)

    assert len(captured) == 1


def test_table_columns_are_introspected_once_and_cached():
    query = PgDataQuery.__new__(PgDataQuery)
    query.version_code = None
    query.connection = None
    calls = []
    columns = [
        "id",
        "deleted",
        "customer_id",
        "device_name",
        "is_draft",
        "version_code",
    ]

    def execute(sql, params=None):
        calls.append((sql, params))
        if "information_schema.columns" in sql:
            return [{"column_name": column} for column in columns]
        return []

    query._execute = execute

    query._get_device_by_table(TABLE)
    query._get_device_by_table(TABLE)

    metadata_calls = [
        (sql, params) for sql, params in calls if "information_schema.columns" in sql
    ]
    device_calls = [
        (sql, params)
        for sql, params in calls
        if "information_schema.columns" not in sql
    ]
    assert len(metadata_calls) == 1
    assert metadata_calls[0][1] == (TABLE,)
    assert len(device_calls) == 2
