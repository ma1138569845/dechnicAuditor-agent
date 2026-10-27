"""Presentation helpers shared by CLI, slash, Gateway, and TUI health audits."""

from __future__ import annotations

import json
from collections.abc import Sequence

MIN_HEALTH_AUDIT_DAYS = 1
MAX_HEALTH_AUDIT_DAYS = 365


def validate_health_audit_days(days: int | None) -> str | None:
    if isinstance(days, bool) or not isinstance(days, int):
        return "skills_audit_days_must_be_integer"
    if not MIN_HEALTH_AUDIT_DAYS <= days <= MAX_HEALTH_AUDIT_DAYS:
        return (
            "skills_audit_days_out_of_range: "
            f"expected {MIN_HEALTH_AUDIT_DAYS}..{MAX_HEALTH_AUDIT_DAYS}"
        )
    return None


def health_audit_requested(args: Sequence[str]) -> bool:
    return any(token == "--days" or token.startswith("--days=") for token in args)


def _parse_health_audit_args(args: Sequence[str]) -> tuple[int | None, bool, str | None]:
    tokens = list(args)
    if tokens and tokens[0] == "audit":
        tokens = tokens[1:]
    days: int | None = None
    as_json = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--json":
            as_json = True
            index += 1
            continue
        if token == "--days":
            if days is not None or index + 1 >= len(tokens):
                return None, as_json, "skills_audit_days_invalid"
            try:
                days = int(tokens[index + 1])
            except ValueError:
                return None, as_json, "skills_audit_days_must_be_integer"
            index += 2
            continue
        if token.startswith("--days="):
            if days is not None:
                return None, as_json, "skills_audit_days_invalid"
            try:
                days = int(token.split("=", 1)[1])
            except ValueError:
                return None, as_json, "skills_audit_days_must_be_integer"
            index += 1
            continue
        if token == "--deep":
            return None, as_json, "skills_audit_ambiguous_arguments"
        if token.startswith("-"):
            return None, as_json, f"skills_audit_unknown_option: {token}"
        return None, as_json, "skills_audit_ambiguous_arguments"
    if days is None:
        return None, as_json, "skills_audit_days_required"
    if error := validate_health_audit_days(days):
        return days, as_json, error
    return days, as_json, None


def run_skill_health_audit(
    args: Sequence[str],
    *,
    as_json: bool | None = None,
) -> tuple[int, str, str]:
    """Return ``(exit_code, stdout, stderr)`` for one health audit request."""
    days, parsed_json, error = _parse_health_audit_args(args)
    if error or days is None:
        return 2, "", error or "skills_audit_days_required"
    return run_skill_health_audit_days(days, as_json=parsed_json if as_json is None else as_json)


def run_skill_health_audit_days(days: int, *, as_json: bool = False) -> tuple[int, str, str]:
    if error := validate_health_audit_days(days):
        return 2, "", error
    from tools.skill_health import build_skill_health_report, render_skill_health_text

    report = build_skill_health_report(days=days)
    if as_json:
        return 0, json.dumps(report, ensure_ascii=False, sort_keys=True), ""
    return 0, render_skill_health_text(report), ""


__all__ = [
    "MAX_HEALTH_AUDIT_DAYS",
    "MIN_HEALTH_AUDIT_DAYS",
    "health_audit_requested",
    "run_skill_health_audit",
    "run_skill_health_audit_days",
    "validate_health_audit_days",
]
