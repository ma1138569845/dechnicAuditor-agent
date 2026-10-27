import threading
from concurrent.futures import ThreadPoolExecutor

from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext
from tools.skill_proposal_service import (
    approve_skill_proposal,
    reject_skill_proposal,
    submit_skill_proposal,
)
from tools.skill_proposals import get_skill_proposal


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
    assert second["review_hash"] != first["review_hash"]
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
    assert result["proposal"]["revision"] == staged["revision"] + 1
    assert result["proposal"]["review_hash"] != staged["review_hash"]
    refreshed = get_skill_proposal(staged["pending_id"], now=1_001.0)
    assert refreshed is not None
    assert refreshed["revision"] == result["proposal"]["revision"]
    assert refreshed["review_hash"] == result["proposal"]["review_hash"]
    assert refreshed["conflict"] == "target_changed"


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


def test_validation_blocker_requires_a_fresh_review_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_alpha()
    calls = []
    monkeypatch.setattr(
        "tools.skill_proposal_service.validate_proposed_operation",
        lambda operation: "blocked_by_lint",
    )

    result = approve_skill_proposal(
        staged["pending_id"],
        revision=staged["revision"],
        review_hash=staged["review_hash"],
        base_hash=staged["base_hash"],
        apply_fn=lambda proposal: calls.append(proposal) or {"success": True},
        now=1_001.0,
    )

    assert result["error"] == "review_refresh_required"
    assert calls == []
    assert result["proposal"]["conflict"] == "review_refresh_required"
    assert result["proposal"]["last_error"] == "blocked_by_lint"
    assert result["proposal"]["revision"] == staged["revision"] + 1
    assert result["proposal"]["review_hash"] != staged["review_hash"]
    refreshed = get_skill_proposal(staged["pending_id"], now=1_001.0)
    assert refreshed is not None
    assert refreshed["revision"] == result["proposal"]["revision"]
    assert refreshed["review_hash"] == result["proposal"]["review_hash"]
    assert refreshed["last_error"] == "blocked_by_lint"


def test_apply_anchor_stale_persists_conflict_for_refresh(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_alpha()

    result = approve_skill_proposal(
        staged["pending_id"],
        revision=staged["revision"],
        review_hash=staged["review_hash"],
        base_hash=staged["base_hash"],
        apply_fn=lambda proposal: {"success": False, "error": "anchor_stale"},
        now=1_001.0,
    )

    assert result["error"] == "anchor_stale"
    assert result["proposal"]["status"] == "pending"
    assert result["proposal"]["conflict"] == "anchor_stale"
    assert result["proposal"]["revision"] == staged["revision"] + 1
    assert result["proposal"]["review_hash"] != staged["review_hash"]
    refreshed = get_skill_proposal(staged["pending_id"], now=1_001.0)
    assert refreshed is not None
    assert refreshed["conflict"] == "anchor_stale"
    assert refreshed["revision"] == result["proposal"]["revision"]
    assert refreshed["review_hash"] == result["proposal"]["review_hash"]


def test_reject_checks_the_review_hash_and_moves_only_v2_to_history(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = submit_skill_proposal(
        {
            "action": "create",
            "name": "alpha",
            "content": "---\nname: alpha\ndescription: alpha\n---\n\nUse the procedure.\n",
        },
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


def _stage_alpha(*, now: float = 1_000.0):
    return submit_skill_proposal(
        {
            "action": "create",
            "name": "alpha",
            "content": (
                "---\nname: alpha\ndescription: Use when testing alpha.\n---\n\n"
                "## When to Use\nTest.\n"
            ),
        },
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        _background_context(),
        now=now,
    )


def test_expired_proposal_never_calls_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_alpha(now=1_000.0)
    calls = []

    result = approve_skill_proposal(
        staged["pending_id"],
        revision=staged["revision"],
        review_hash=staged["review_hash"],
        base_hash=staged["base_hash"],
        apply_fn=lambda proposal: calls.append(proposal) or {"success": True},
        now=1_000.0 + 15 * 86400,
    )

    assert result == {"success": False, "error": "expired"}
    assert calls == []
    history = tmp_path / "pending" / "skills" / ".history" / f"{staged['pending_id']}.json"
    assert history.exists()


def test_concurrent_approve_has_one_applier(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_alpha()
    entered = threading.Event()
    second_entered = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def apply(proposal):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
        else:
            second_entered.set()
        assert release.wait(timeout=2)
        return {"success": True}

    def approve():
        return approve_skill_proposal(
            staged["pending_id"],
            revision=staged["revision"],
            review_hash=staged["review_hash"],
            base_hash=staged["base_hash"],
            apply_fn=apply,
            now=1_001.0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(approve)
        assert entered.wait(timeout=2)
        second = pool.submit(approve)
        second_entered.wait(timeout=0.5)
        release.set()
        results = [first.result(timeout=3), second.result(timeout=3)]

    assert len(calls) == 1
    assert not second_entered.is_set()
    assert sorted(result["success"] for result in results) == [False, True]
    assert next(result for result in results if not result["success"])["error"] == "already_being_reviewed"


def test_reject_cannot_race_an_active_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_alpha()
    entered = threading.Event()
    release = threading.Event()

    def apply(proposal):
        entered.set()
        assert release.wait(timeout=2)
        return {"success": True}

    with ThreadPoolExecutor(max_workers=1) as pool:
        approval = pool.submit(
            approve_skill_proposal,
            staged["pending_id"],
            revision=staged["revision"],
            review_hash=staged["review_hash"],
            base_hash=staged["base_hash"],
            apply_fn=apply,
            now=1_001.0,
        )
        assert entered.wait(timeout=2)
        rejected = reject_skill_proposal(
            staged["pending_id"],
            review_hash=staged["review_hash"],
            now=1_002.0,
        )
        release.set()
        approved = approval.result(timeout=3)

    assert rejected["error"] == "already_being_reviewed"
    assert approved["success"] is True
    history = tmp_path / "pending" / "skills" / ".history" / f"{staged['pending_id']}.json"
    assert history.exists()
    assert '"status": "applied"' in history.read_text(encoding="utf-8-sig")


def test_evidence_merge_cannot_change_a_proposal_while_it_is_applying(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    staged = _stage_alpha()
    entered = threading.Event()
    release = threading.Event()

    def apply(proposal):
        entered.set()
        assert release.wait(timeout=2)
        return {"success": True}

    with ThreadPoolExecutor(max_workers=1) as pool:
        approval = pool.submit(
            approve_skill_proposal,
            staged["pending_id"],
            revision=staged["revision"],
            review_hash=staged["review_hash"],
            base_hash=staged["base_hash"],
            apply_fn=apply,
            now=1_001.0,
        )
        assert entered.wait(timeout=2)
        merged = submit_skill_proposal(
            {
                "action": "create",
                "name": "alpha",
                "content": (
                    "---\nname: alpha\ndescription: Use when testing alpha.\n---\n\n"
                    "## When to Use\nTest.\n"
                ),
            },
            [{"kind": "user_correction", "message_refs": [5], "reason": "check first"}],
            _background_context(),
            now=1_002.0,
        )
        release.set()
        approved = approval.result(timeout=3)

    assert merged["error"] == "proposal_in_review"
    assert approved["success"] is True
