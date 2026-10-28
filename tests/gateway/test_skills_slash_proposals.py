import time

from hermes_cli.write_approval_commands import handle_pending_subcommand
from tools import write_approval as wa
from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext
from tools.skill_proposal_service import submit_skill_proposal


def _background_context():
    return SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-1",
        session_id="session-1",
        review_run_id="review-1",
        review_message_refs=frozenset({2}),
        review_snapshot_digest="sha256:" + "a" * 64,
    )


def _stage_v2(name="audit-report", now=None):
    return submit_skill_proposal(
        {
            "action": "create",
            "name": name,
            "content": (
                f"---\nname: {name}\ndescription: Use when auditing.\n---\n\n"
                "Verify sources.\n"
            ),
        },
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        _background_context(),
        now=time.time() if now is None else now,
    )


def _stage_v1():
    return wa.stage_write(
        wa.SKILLS,
        {
            "action": "create",
            "name": "legacy",
            "content": "---\nname: legacy\ndescription: legacy\n---\n\nUse it.\n",
        },
        summary="legacy pending",
        origin=wa.current_origin(),
    )


def test_shared_pending_lists_v1_and_v2_without_the_legacy_gate(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    legacy = _stage_v1()
    proposal = _stage_v2()

    out = handle_pending_subcommand(wa.SKILLS, ["pending"])

    assert legacy["id"] in out
    assert proposal["pending_id"] in out
    assert "legacy pending" in out
    assert "audit-report" in out


def test_v2_slash_show_and_approve_use_shared_revision_binding(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_v2()

    shown = handle_pending_subcommand(
        wa.SKILLS, ["show", staged["pending_id"]]
    )
    assert f"/skills approve {staged['pending_id']} {staged['revision']}" in shown

    approved = handle_pending_subcommand(
        wa.SKILLS,
        ["approve", staged["pending_id"], str(staged["revision"])],
    )
    assert "Approved" in approved
    assert (tmp_path / "skills" / "audit-report" / "SKILL.md").exists()


def test_v2_all_is_refused_while_v1_reject_remains_available(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    legacy = _stage_v1()
    _stage_v2()

    refused = handle_pending_subcommand(wa.SKILLS, ["approve", "all"])
    assert "reviewed_revision_required" in refused

    rejected = handle_pending_subcommand(
        wa.SKILLS, ["reject", legacy["id"]]
    )
    assert "Rejected" in rejected
    assert wa.get_pending(wa.SKILLS, legacy["id"]) is None
    assert not (
        tmp_path / "pending" / "skills" / ".history" / f"{legacy['id']}.json"
    ).exists()


def test_v1_individual_approve_is_blocked_without_writing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    legacy = _stage_v1()

    out = handle_pending_subcommand(
        wa.SKILLS, ["approve", legacy["id"]]
    )

    assert "legacy_pending_requires_explicit_edit" in out
    assert wa.get_pending(wa.SKILLS, legacy["id"]) is not None
    assert not (tmp_path / "skills" / "legacy").exists()


def test_stale_v2_revision_does_not_refresh_the_hash_or_write(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    first = _stage_v2()
    _stage_v2(now=time.time() + 1)

    out = handle_pending_subcommand(
        wa.SKILLS,
        ["approve", first["pending_id"], str(first["revision"])],
    )

    assert "review_hash_mismatch" in out
    assert not (tmp_path / "skills" / "audit-report").exists()


def test_v2_review_surface_remains_visible_when_legacy_gate_is_off(
    tmp_path, monkeypatch
):
    from hermes_cli.skills_proposals import skill_review_surface_available

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(wa, "write_approval_enabled", lambda _subsystem: False)
    _stage_v2()

    assert skill_review_surface_available(False) is True
