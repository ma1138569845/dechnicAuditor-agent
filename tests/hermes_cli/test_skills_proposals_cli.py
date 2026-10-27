import argparse
import json
import time

from hermes_cli.skills_proposals import (
    format_skill_proposal_detail,
    format_skill_proposal_list,
)


def _proposal(**overrides):
    row = {
        "schema_version": 2,
        "id": "skp_report",
        "status": "pending",
        "revision": 3,
        "fingerprint": "sha256:" + "f" * 64,
        "review_hash": "sha256:" + "r" * 64,
        "base_hash": "sha256:" + "b" * 64,
        "created_at": 1_000.0,
        "last_seen_at": 2_000.0,
        "expires_at": 1_000.0 + 14 * 86400,
        "evidence_count": 2,
        "evidence": [
            {
                "kind": "user_correction",
                "message_refs": [2, 8],
                "reason": "verify sources before writing",
            }
        ],
        "target": {"name": "audit-report"},
        "operation": {
            "action": "patch",
            "name": "audit-report",
            "file_path": "SKILL.md",
            "old_string": "Old.",
            "new_string": "New.",
        },
        "preview": {
            "summary": "patch SKILL.md (+1/-0)",
            "diff": "+ Verify sources before writing.\n",
            "lint": [],
            "security": {"verdict": "safe", "findings": []},
        },
        "related": {"possible_duplicates": [], "overlap_count": 0},
        "conflict": None,
        "failure": None,
    }
    row.update(overrides)
    return row


def test_list_uses_stable_codes_and_never_prints_evidence_reasons():
    text = format_skill_proposal_list(
        [_proposal(conflict="target_changed")],
        now=2_100.0,
    )

    assert "skp_report" in text
    assert "audit-report" in text
    assert "patch" in text
    assert "user_correction" in text
    assert "evidence=2" in text
    assert "target_changed" in text
    assert "verify sources before writing" not in text


def test_detail_prints_snapshot_fields_required_for_approval():
    text = format_skill_proposal_detail(_proposal())

    assert "base_hash: sha256:" + "b" * 64 in text
    assert "review_hash: sha256:" + "r" * 64 in text
    assert "revision: 3" in text
    assert "/skills approve skp_report 3" in text
    assert "/skills reject skp_report 3" in text
    assert "approval revalidates target, lint, and security" in text.lower()


def test_proposals_parser_exposes_reviewed_revision_and_profile():
    from hermes_cli.subcommands.skills import build_skills_parser

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    build_skills_parser(subparsers, cmd_skills=lambda _args: None)

    listed = parser.parse_args(["skills", "proposals", "list", "--profile", "work"])
    shown = parser.parse_args(["skills", "proposals", "show", "skp_1", "-p", "work"])
    approved = parser.parse_args(
        [
            "skills",
            "proposals",
            "approve",
            "skp_1",
            "--revision",
            "3",
            "--profile",
            "work",
        ]
    )
    pruned = parser.parse_args(["skills", "proposals", "prune", "--profile", "work"])

    assert listed.profile == "work"
    assert shown.proposal_id == "skp_1"
    assert approved.revision == 3
    assert approved.proposals_action == "approve"
    assert pruned.proposals_action == "prune"
    assert pruned.profile == "work"


def test_prune_command_moves_expired_v2_and_keeps_v1_and_recent_history(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from hermes_cli.skills_proposals import run_skill_proposal_command

    pending = tmp_path / "pending" / "skills"
    history = pending / ".history"
    history.mkdir(parents=True)
    now = time.time()

    def write(path, record):
        path.write_text(json.dumps(record), encoding="utf-8")

    write(
        pending / "skp_expired.json",
        {
            "schema_version": 2,
            "id": "skp_expired",
            "status": "pending",
            "expires_at": now - 1,
            "updated_at": now - 2,
        },
    )
    write(
        pending / "legacy.json",
        {
            "id": "legacy",
            "status": "pending",
            "created_at": now - 60 * 86400,
            "payload": {"action": "create", "name": "legacy"},
        },
    )
    write(
        history / "recent.json",
        {
            "schema_version": 2,
            "id": "recent",
            "status": "applied",
            "updated_at": now - 10 * 86400,
        },
    )
    write(
        history / "old.json",
        {
            "schema_version": 2,
            "id": "old",
            "status": "rejected",
            "updated_at": now - 31 * 86400,
        },
    )

    exit_code = run_skill_proposal_command("prune", None)

    assert exit_code == 0
    assert "expired=1" in capsys.readouterr().out
    assert not (pending / "skp_expired.json").exists()
    assert (history / "skp_expired.json").exists()
    assert (pending / "legacy.json").exists()
    assert (history / "recent.json").exists()
    assert not (history / "old.json").exists()


def test_v1_records_are_visible_but_cannot_use_v2_approve(
    tmp_path, monkeypatch, capsys
):
    from tools import write_approval as wa

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    legacy = wa.stage_write(
        wa.SKILLS,
        {
            "action": "create",
            "name": "legacy",
            "content": "---\nname: legacy\ndescription: legacy\n---\n\nUse it.\n",
        },
        summary="legacy",
        origin=wa.current_origin(),
    )
    from hermes_cli.skills_proposals import run_skill_proposal_command

    exit_code = run_skill_proposal_command("approve", legacy["id"])

    assert exit_code == 2
    assert "legacy_pending_requires_explicit_edit" in capsys.readouterr().err
    assert wa.get_pending(wa.SKILLS, legacy["id"]) is not None


def test_v2_approve_requires_the_revision_the_user_reviewed(
    tmp_path, monkeypatch, capsys
):
    from hermes_cli.skills_proposals import run_skill_proposal_command
    from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext
    from tools.skill_proposal_service import submit_skill_proposal

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    context = SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-1",
        session_id="session-1",
        review_run_id="review-1",
        review_message_refs=frozenset({2}),
        review_snapshot_digest="sha256:" + "a" * 64,
    )
    operation = {
        "action": "create",
        "name": "audit-report",
        "content": (
            "---\nname: audit-report\ndescription: Audit.\n---\n\n"
            "Verify sources.\n"
        ),
    }
    first = submit_skill_proposal(
        operation,
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        context,
        now=time.time(),
    )

    assert run_skill_proposal_command("approve", first["pending_id"]) == 2
    assert "reviewed_revision_required" in capsys.readouterr().err

    submit_skill_proposal(
        operation,
        [{"kind": "user_correction", "message_refs": [2], "reason": "verify"}],
        context,
        now=time.time() + 1,
    )
    assert (
        run_skill_proposal_command(
            "approve", first["pending_id"], reviewed_revision=1
        )
        == 2
    )
    assert "review_hash_mismatch" in capsys.readouterr().err
    assert not (tmp_path / "skills" / "audit-report").exists()


def test_v2_approve_and_reject_apply_only_the_reviewed_snapshot(
    tmp_path, monkeypatch, capsys
):
    from hermes_cli.skills_proposals import run_skill_proposal_command
    from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext
    from tools.skill_proposal_service import submit_skill_proposal

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    context = SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-1",
        session_id="session-1",
        review_run_id="review-1",
        review_message_refs=frozenset({2}),
        review_snapshot_digest="sha256:" + "a" * 64,
    )
    operation = {
        "action": "create",
        "name": "audit-report",
        "content": (
            "---\nname: audit-report\ndescription: Audit.\n---\n\n"
            "Verify sources.\n"
        ),
    }
    approved = submit_skill_proposal(
        operation,
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        context,
        now=time.time(),
    )
    assert (
        run_skill_proposal_command(
            "approve",
            approved["pending_id"],
            reviewed_revision=approved["revision"],
        )
        == 0
    )
    assert (tmp_path / "skills" / "audit-report" / "SKILL.md").exists()
    capsys.readouterr()

    rejected = submit_skill_proposal(
        {**operation, "name": "rejected-report"},
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        context,
        now=time.time() + 2,
    )
    assert (
        run_skill_proposal_command(
            "reject",
            rejected["pending_id"],
            reviewed_revision=rejected["revision"],
        )
        == 0
    )
    assert not (tmp_path / "skills" / "rejected-report").exists()
