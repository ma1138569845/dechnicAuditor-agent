"""指定 version_code 时采集锁定正式快照；未指定时仍草稿优先。"""

from tools.energy_audit.data_collection_cli import parse_args
from tools.energy_audit.pg_collector import collect_from_pg
from tools.energy_audit.pg_query import PgDataQuery


def _query(version_code=None):
    q = PgDataQuery.__new__(PgDataQuery)
    q.version_code = PgDataQuery.normalize_version_code(version_code)
    captured = []

    def fake_execute(sql, params=None):
        captured.append((sql, params))
        return []

    q._execute = fake_execute
    q.connection = None
    return q, captured


def test_normalize_version_code():
    assert PgDataQuery.normalize_version_code(None) is None
    assert PgDataQuery.normalize_version_code("  ") is None
    assert PgDataQuery.normalize_version_code("null") is None
    assert PgDataQuery.normalize_version_code("PL2026080401") == "PL2026080401"


def test_energy_query_draft_first_when_unspecified():
    q, captured = _query()
    q.get_institution_energy(customer_id=9)
    sql, params = captured[0]
    assert "COALESCE(mm.is_draft, 0) DESC" in sql
    assert "mm.version_code = %s" not in sql
    assert params == (9, 9)


def test_energy_query_locks_published_snapshot():
    q, captured = _query("PL2026080401")
    q.get_institution_energy(customer_id=9)
    sql, params = captured[0]
    assert "COALESCE(mm.is_draft, 0) = 0" in sql
    assert "mm.version_code = %s" in sql
    assert "COALESCE(mm.is_draft, 0) DESC" not in sql
    assert "PL2026080401" in params


def test_build_and_meter_and_saving_lock_snapshot():
    q, captured = _query("PL2026080401")
    q.get_institution_build(customer_id=3)
    q.get_energy_meter(customer_id=3)
    q.get_institution_energy_saving(customer_id=3)
    q.get_institution_scene(customer_id=3)
    assert len(captured) == 4
    for sql, params in captured:
        assert "version_code = %s" in sql
        assert "is_draft, 0) = 0" in sql
        assert "is_draft, 0) DESC" not in sql
        assert "PL2026080401" in params


def test_device_query_locks_snapshot():
    q, captured = _query("PL2026080401")
    q._get_device_by_table("ts_institution_device_light", customer_id=3)
    sql, params = captured[0]
    assert "t.version_code = %s" in sql
    assert "t.id DESC" in sql
    assert params[-1] == "PL2026080401"


def test_invoice_query_locks_snapshot():
    q, captured = _query("PL2026080401")
    q.get_institution_energy_invoice(customer_id=3)
    sql, params = captured[0]
    assert sql.count("version_code = %s") == 2
    assert params.count("PL2026080401") == 2


def test_cli_parses_version_code():
    args = parse_args(["烟台法院", "--version-code", "PL2026080401"])
    assert args.project_name == "烟台法院"
    assert args.version_code == "PL2026080401"
    assert parse_args(["烟台法院"]).version_code is None


def test_collect_from_pg_passes_version_code(monkeypatch):
    seen = {}

    class FakePg:
        def __init__(self, config=None, version_code=None):
            seen["version_code"] = version_code
            self.version_code = version_code

        def connect(self):
            return None

        def disconnect(self):
            return None

    monkeypatch.setattr("tools.energy_audit.pg_collector.PgDataQuery", FakePg)
    monkeypatch.setattr(
        "tools.energy_audit.pg_collector._collect_from_pg_impl",
        lambda pg, name: {"found": {}, "missing": [], "project_id": 1},
    )
    result = collect_from_pg("单位", version_code="PL2026080401")
    assert seen["version_code"] == "PL2026080401"
    assert result["version_code"] == "PL2026080401"
    assert result["project_id"] == 1
