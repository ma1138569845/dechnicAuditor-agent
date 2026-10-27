import argparse
import json

import pytest

from hermes_cli.main_agent_cmds import cmd_skills


def _report():
    return {
        "schema_version": 1,
        "generated_at": "2026-10-27T00:00:00+00:00",
        "window_days": 30,
        "evidence_complete": False,
        "library": {
            "total": 1,
            "active": 1,
            "stale": 0,
            "archived": 0,
            "broken": 0,
            "metadata_chars": 12,
            "estimated_tokens": 3,
            "growth": {"last_7_days": 0, "last_30_days": 0},
        },
        "proposals": {
            "pending": 0,
            "applied": 0,
            "rejected": 0,
            "expired": 0,
            "broken": 0,
            "approval_rate": None,
            "rejection_rate": None,
            "expiration_rate": None,
            "median_handling_seconds": None,
            "max_pending_per_target": 0,
            "max_pending_per_anchor": 0,
            "stale_targets": 0,
            "stale_anchors": 0,
            "possible_duplicates": 0,
        },
        "recommendations": [],
    }


@pytest.mark.parametrize("days", [0, 366, -1])
def test_health_audit_rejects_out_of_range_days_before_enumeration(
    monkeypatch, days
):
    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: pytest.fail("out-of-range days must not enumerate skills"),
    )

    assert cmd_skills(
        argparse.Namespace(skills_action="audit", days=days, json=False, name=None, deep=False)
    ) == 2


def test_non_integer_days_is_an_argparse_error():
    from hermes_cli.subcommands.skills import build_skills_parser

    parser = argparse.ArgumentParser()
    build_skills_parser(parser.add_subparsers(dest="command"), cmd_skills=lambda _args: None)

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["skills", "audit", "--days", "thirty"])

    assert exc.value.code == 2


def test_days_with_name_or_deep_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: pytest.fail("ambiguous audit must not enumerate skills"),
    )

    for name, deep in (("audit-report", False), (None, True)):
        assert cmd_skills(
            argparse.Namespace(
                skills_action="audit", days=30, json=False, name=name, deep=deep
            )
        ) == 2


def test_no_days_keeps_the_legacy_hub_audit(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "hermes_cli.skills_hub.do_audit",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: pytest.fail("legacy hub audit must not run health aggregation"),
    )

    assert cmd_skills(
        argparse.Namespace(skills_action="audit", days=None, json=False, name="alpha", deep=True)
    ) is None
    assert calls == [{"name": "alpha", "deep": True}]


def test_json_output_is_sorted_parseable_and_contains_no_skill_body(
    monkeypatch, capsys
):
    report = _report()
    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: report,
    )

    assert cmd_skills(
        argparse.Namespace(skills_action="audit", days=30, json=True, name=None, deep=False)
    ) == 0
    out = capsys.readouterr().out
    decoded = json.loads(out)

    assert decoded == report
    assert out == json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n"
    assert "TOP_SECRET_SKILL_BODY" not in out


def test_classic_slash_routes_days_to_health_audit(monkeypatch):
    from io import StringIO

    from rich.console import Console

    from hermes_cli.skills_hub import handle_skills_slash

    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: _report(),
    )
    output = StringIO()
    handle_skills_slash("/skills audit --days 30", console=Console(file=output, force_terminal=False))

    assert "Library" in output.getvalue()
    assert '"schema_version": 1' not in output.getvalue()


@pytest.mark.asyncio
async def test_gateway_health_audit_runs_with_legacy_gate_off(monkeypatch):
    from gateway.slash_commands import GatewaySlashCommandsMixin
    from tools import write_approval as wa

    class Event:
        def get_command_args(self):
            return "audit --days 30"

    monkeypatch.setattr(wa, "write_approval_enabled", lambda _subsystem: False)
    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: _report(),
    )

    out = await GatewaySlashCommandsMixin._handle_skills_command(object(), Event())

    assert "Library" in out
    assert "write approval is off" not in out.lower()


def test_tui_health_audit_uses_the_same_report(monkeypatch):
    from tui_gateway import methods_tools

    monkeypatch.setattr(
        methods_tools,
        "_ok",
        lambda rid, payload: {"id": rid, "result": payload},
        raising=False,
    )
    monkeypatch.setattr(
        "tools.skill_health.build_skill_health_report",
        lambda **kwargs: _report(),
    )

    result = methods_tools._cmd_skills(
        "r1", {"session_id": "s1"}, None, "skills", "audit --days 30"
    )

    assert "Library" in result["result"]["output"]
