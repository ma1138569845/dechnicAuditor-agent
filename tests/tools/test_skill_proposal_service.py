from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext
from tools.skill_proposal_service import (
    approve_skill_proposal,
    reject_skill_proposal,
    submit_skill_proposal,
)


def _background_context() -> SkillWriteIntentContext:
    return SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-1",
        session_id="session-1",
        review_run_id="review-1",
        review_message_refs=frozenset({2, 5}),
        review_snapshot_digest="sha256:" + "a" * 64,
    )


def test_old_review_hash_cannot_approve_after_evidence_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    operation = {
        "action": "create",
        "name": "energy-audit-workflow",
        "content": "---\nname: energy-audit-workflow\ndescription: Use when auditing a building.\n---\n\n## When to Use\nCheck inputs.\n",
    }
    evidence = [{"kind": "user_request", "message_refs": [2], "reason": "remember this workflow"}]
    first = submit_skill_proposal(operation, evidence, _background_context(), now=1_000.0)
    second = submit_skill_proposal(
        operation,
        [{"kind": "user_correction", "message_refs": [5], "reason": "check inputs first"}],
        _background_context(),
        now=1_001.0,
    )

    result = approve_skill_proposal(
        first["pending_id"],
        revision=first["revision"],
        review_hash=first["review_hash"],
        base_hash=first["base_hash"],
        apply_fn=lambda proposal: {"success": True},
        now=1_002.0,
    )

    assert second["revision"] == 2
    assert result["error"] == "review_hash_mismatch"
    assert result["current_review_hash"] == second["review_hash"]


def test_target_change_releases_claim_and_keeps_pending_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    skill_dir = tmp_path / "skills" / "existing"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: existing\ndescription: Use when testing.\n---\n\n## When to Use\nOld.\n",
        encoding="utf-8",
    )
    operation = {
        "action": "patch",
        "name": "existing",
        "old_string": "Old.",
        "new_string": "New.",
    }
    staged = submit_skill_proposal(
        operation,
        [{"kind": "skill_incomplete", "message_refs": [2], "reason": "missing check"}],
        _background_context(),
        now=1_000.0,
    )
    (skill_dir / "SKILL.md").write_text("changed by user\n", encoding="utf-8")

    result = approve_skill_proposal(
        staged["pending_id"],
        revision=staged["revision"],
        review_hash=staged["review_hash"],
        base_hash=staged["base_hash"],
        apply_fn=lambda proposal: {"success": True},
        now=1_001.0,
    )

    assert result["error"] == "target_changed"
    assert result["proposal"]["status"] == "pending"
    assert result["proposal"]["conflict"] == "target_changed"


def test_apply_failure_returns_pending_not_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = submit_skill_proposal(
        {"action": "create", "name": "alpha", "content": "---\nname: alpha\ndescription: Use when testing alpha.\n---\n\n## When to Use\nTest.\n"},
        [{"kind": "user_correction", "message_refs": [2], "reason": "use this sequence"}],
        _background_context(),
        now=1_000.0,
    )

    result = approve_skill_proposal(
        staged["pending_id"],
        revision=staged["revision"],
        review_hash=staged["review_hash"],
        base_hash=staged["base_hash"],
        apply_fn=lambda proposal: {"success": False, "error": "disk full"},
        now=1_001.0,
    )

    assert result["error"] == "apply_failed"
    assert result["proposal"]["status"] == "pending"
    assert result["proposal"]["last_error"] == "disk full"


def test_reject_checks_the_review_hash_and_moves_only_v2_to_history(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = submit_skill_proposal(
        {"action": "create", "name": "alpha", "content": "---\nname: alpha\ndescription: alpha\n---\n"},
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        _background_context(),
        now=1_000.0,
    )

    stale = reject_skill_proposal(
        staged["pending_id"],
        review_hash="sha256:" + "0" * 64,
        now=1_001.0,
    )
    assert stale["error"] == "review_hash_mismatch"
    assert (
        tmp_path / "pending" / "skills" / f"{staged['pending_id']}.json"
    ).exists()

    rejected = reject_skill_proposal(
        staged["pending_id"],
        review_hash=staged["review_hash"],
        now=1_002.0,
    )
    assert rejected["success"] is True
    assert rejected["proposal"]["status"] == "rejected"
    assert not (
        tmp_path / "pending" / "skills" / f"{staged['pending_id']}.json"
    ).exists()
    assert (
        tmp_path / "pending" / "skills" / ".history"
        / f"{staged['pending_id']}.json"
    ).exists()
