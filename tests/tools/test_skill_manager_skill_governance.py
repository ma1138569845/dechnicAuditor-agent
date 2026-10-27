import json
from dataclasses import replace

import pytest

from tools import skill_learning_config
from tools.skill_intent import (
    SkillWriteIntent,
    SkillWriteIntentContext,
    bind_skill_write_context,
    reset_skill_write_context,
)
from tools.skill_manager_tool import apply_skill_proposal, skill_manage


SKILL_MD = (
    "---\n"
    "name: audit-report\n"
    "description: Use when writing an audit report.\n"
    "---\n\n"
    "## Procedure\n\nVerify sources before writing.\n"
)


@pytest.fixture
def background_context():
    from tools.skill_manager_guards import _reset_background_review_read_marks

    _reset_background_review_read_marks()
    context = SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-origin",
        session_id="session-origin",
        review_run_id="review-origin",
        review_message_refs=frozenset({2}),
        review_snapshot_digest="sha256:" + "a" * 64,
    )
    token = bind_skill_write_context(context)
    try:
        yield context
    finally:
        reset_skill_write_context(token)
        _reset_background_review_read_marks()


def _mode(monkeypatch, mode: str):
    baseline = skill_learning_config.get_skill_learning_config()
    monkeypatch.setattr(
        skill_learning_config,
        "get_skill_learning_config",
        lambda config=None: replace(baseline, mode=mode),
    )


def test_propose_stages_create_without_touching_skills(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")

    result = json.loads(
        skill_manage(
            operations=[
                {
                    "action": "create",
                    "name": "audit-report",
                    "content": SKILL_MD,
                }
            ],
            proposal_evidence={
                "kind": "user_request",
                "message_refs": [2],
                "reason": "remember this report procedure",
            },
        )
    )

    assert result["proposal_staged"] is True
    assert result["pending_id"].startswith("skp_")
    assert result["base_hash"]
    assert not (tmp_path / "skills" / "audit-report" / "SKILL.md").exists()


def test_off_refuses_background_mutation_before_legacy_staging(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "off")
    monkeypatch.setattr("tools.skill_manager_tool._run_write_gate", lambda _: None)

    result = json.loads(
        skill_manage(action="create", name="audit-report", content=SKILL_MD)
    )

    assert result == {
        "success": False,
        "error": "skill_learning_disabled",
        "message": "Background skill learning is disabled (skills.auto_learning.mode=off).",
    }


def test_auto_requires_evidence_before_direct_write(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "auto")

    result = json.loads(
        skill_manage(action="create", name="audit-report", content=SKILL_MD)
    )

    assert result["error"] == "evidence_required"
    assert result["not_staged"] is True
    assert not (tmp_path / "skills" / "audit-report").exists()


def test_batch_is_one_proposal_and_replays_atomically(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    operations = [
        {"action": "create", "name": "audit-report", "content": SKILL_MD},
        {
            "action": "write_file",
            "name": "audit-report",
            "file_path": "references/checks.md",
            "file_content": "# Checks\n\n- verify sources\n",
        },
    ]

    staged = json.loads(
        skill_manage(
            operations=operations,
            proposal_evidence={
                "kind": "user_correction",
                "message_refs": [2],
                "reason": "include source verification",
            },
        )
    )
    assert staged["proposal_staged"] is True
    from tools.skill_proposals import list_skill_proposals

    assert [item["id"] for item in list_skill_proposals()] == [staged["pending_id"]]
    assert not (tmp_path / "skills" / "audit-report").exists()

    from tools.skill_proposals import get_skill_proposal

    proposal = get_skill_proposal(staged["pending_id"])
    recorded = []
    ledger_writes = []
    monkeypatch.setattr(
        "tools.skill_usage.record_created",
        lambda name, **kwargs: recorded.append((name, kwargs)),
    )
    monkeypatch.setattr(
        "tools.skill_ledger.record_mutation",
        lambda action, name, **kwargs: ledger_writes.append((action, name, kwargs)),
    )
    applied = json.loads(apply_skill_proposal(proposal))

    assert applied["operations_applied"] == 2
    skill_dir = tmp_path / "skills" / "audit-report"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "references" / "checks.md").exists()
    assert recorded == [
        (
            "audit-report",
            {
                "agent_created": True,
                "task_id": "task-origin",
                "session_id": "session-origin",
            },
        )
    ]
    assert ledger_writes[0][2]["evidence"]["origin"] == "background_review"
    assert ledger_writes[0][2]["evidence"]["review_run_id"] == "review-origin"


def test_apply_refuses_to_overwrite_a_target_created_after_review(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    staged = json.loads(
        skill_manage(
            action="create",
            name="audit-report",
            content=SKILL_MD,
            proposal_evidence={
                "kind": "user_request",
                "message_refs": [2],
                "reason": "remember this report procedure",
            },
        )
    )
    from tools.skill_proposals import get_skill_proposal
    from tools import skill_manager_tool

    proposal = get_skill_proposal(staged["pending_id"])
    user_dir = tmp_path / "skills" / "audit-report"
    user_dir.mkdir(parents=True)
    user_content = "---\nname: audit-report\ndescription: User-owned.\n---\n\nKeep me.\n"
    (user_dir / "SKILL.md").write_text(user_content, encoding="utf-8")
    called = []
    monkeypatch.setattr(
        skill_manager_tool, "_create_skill", lambda *args, **kwargs: called.append(args)
    )

    result = json.loads(apply_skill_proposal(proposal))

    assert result["error"] == "target_changed"
    assert called == []
    assert (user_dir / "SKILL.md").read_text(encoding="utf-8") == user_content


def _existing_skill(tmp_path, name="existing"):
    skill_dir = tmp_path / "skills" / name
    (skill_dir / "references").mkdir(parents=True)
    content = (
        f"---\nname: {name}\ndescription: Use when testing {name}.\n---\n\n"
        "Verify sources before writing.\n"
    )
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    (skill_dir / "references" / "old.md").write_text("old reference\n", encoding="utf-8")
    return skill_dir


@pytest.mark.parametrize(
    ("action", "name", "payload"),
    [
        ("create", "new-skill", {"content": SKILL_MD.replace("audit-report", "new-skill")}),
        ("edit", "existing", {"content": SKILL_MD.replace("audit-report", "existing")}),
        ("patch", "existing", {"old_string": "Verify sources", "new_string": "Check sources"}),
        (
            "write_file",
            "existing",
            {"file_path": "references/new.md", "file_content": "new reference\n"},
        ),
        ("remove_file", "existing", {"file_path": "references/old.md"}),
        ("delete", "existing", {"absorbed_into": "umbrella"}),
    ],
)
def test_propose_covers_every_mutating_action_without_touching_target(
    tmp_path, monkeypatch, background_context, action, name, payload
):
    from tools.skill_manager_guards import mark_background_review_skill_read
    from tools.skill_manager_tool import _find_skill
    from tools.skill_proposal_candidate import compute_base_hash

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    existing = _existing_skill(tmp_path)
    mark_background_review_skill_read(existing / "SKILL.md")
    mark_background_review_skill_read(existing / "references" / "old.md")
    if action == "delete":
        from tools import skill_usage

        umbrella = _existing_skill(tmp_path, "umbrella")
        mark_background_review_skill_read(umbrella / "SKILL.md")
        skill_usage.record_created(
            "existing",
            agent_created=True,
            task_id="task-origin",
            session_id="session-origin",
        )
    before = compute_base_hash(existing)

    result = json.loads(
        skill_manage(
            action=action,
            name=name,
            proposal_evidence={
                "kind": "user_correction",
                "message_refs": [2],
                "reason": "apply this verified correction",
            },
            **payload,
        )
    )

    assert result["proposal_staged"] is True
    if action == "create":
        assert _find_skill("new-skill") is None
    else:
        assert _find_skill("existing") is not None
        assert compute_base_hash(existing) == before


def test_propose_does_not_bypass_read_before_write(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    _existing_skill(tmp_path)

    result = json.loads(
        skill_manage(
            action="patch",
            name="existing",
            old_string="Verify sources",
            new_string="Check sources",
            proposal_evidence={
                "kind": "user_correction",
                "message_refs": [2],
                "reason": "apply this verified correction",
            },
        )
    )

    assert result["_read_before_write_required"] is True
    from tools.skill_proposals import list_skill_proposals

    assert list_skill_proposals() == []


def test_propose_wins_before_the_legacy_write_approval_gate(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    monkeypatch.setattr(
        "tools.skill_manager_tool._run_write_gate",
        lambda _build: pytest.fail("legacy gate must not run before a v2 proposal"),
    )

    result = json.loads(
        skill_manage(
            action="create",
            name="audit-report",
            content=SKILL_MD,
            proposal_evidence={
                "kind": "user_request",
                "message_refs": [2],
                "reason": "remember this report procedure",
            },
        )
    )

    assert result["proposal_staged"] is True


def test_auto_with_evidence_still_obeys_the_legacy_gate(
    tmp_path, monkeypatch, background_context
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "auto")
    monkeypatch.setattr(
        "tools.skill_manager_tool._run_write_gate",
        lambda _build: json.dumps({"success": True, "staged": True, "pending_id": "v1"}),
    )

    result = json.loads(
        skill_manage(
            action="create",
            name="audit-report",
            content=SKILL_MD,
            proposal_evidence={
                "kind": "user_request",
                "message_refs": [2],
                "reason": "remember this report procedure",
            },
        )
    )

    assert result == {"success": True, "staged": True, "pending_id": "v1"}
    assert not (tmp_path / "skills" / "audit-report").exists()


@pytest.mark.parametrize("intent", [SkillWriteIntent.NORMAL, SkillWriteIntent.USER_LEARN])
def test_foreground_intents_are_not_governed_by_background_modes(
    tmp_path, monkeypatch, intent
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "off")
    context = SkillWriteIntentContext(
        intent=intent,
        origin="foreground",
        attended=True,
        task_id="turn-1",
        session_id="session-1",
        review_run_id=None,
        review_message_refs=frozenset(),
        review_snapshot_digest=None,
    )
    token = bind_skill_write_context(context)
    try:
        result = json.loads(
            skill_manage(
                action="create",
                name=f"foreground-{intent.value.replace('_', '-')}",
                content=SKILL_MD.replace(
                    "audit-report", f"foreground-{intent.value.replace('_', '-')}"
                ),
            )
        )
    finally:
        reset_skill_write_context(token)

    assert result["success"] is True


def test_v2_apply_bypasses_the_legacy_gate_and_does_not_create_v1_pending(
    tmp_path, monkeypatch, background_context
):
    from tools import skill_manager_tool, write_approval
    from tools.skill_proposals import get_skill_proposal

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    staged = json.loads(
        skill_manage(
            action="create",
            name="audit-report",
            content=SKILL_MD,
            proposal_evidence={
                "kind": "user_request",
                "message_refs": [2],
                "reason": "remember this report procedure",
            },
        )
    )
    proposal = get_skill_proposal(staged["pending_id"])
    monkeypatch.setattr(
        skill_manager_tool,
        "_run_write_gate",
        lambda _build: pytest.fail("v2 replay must bypass the legacy v1 gate"),
    )

    result = json.loads(apply_skill_proposal(proposal))

    assert result["success"] is True
    assert (tmp_path / "skills" / "audit-report" / "SKILL.md").exists()
    assert write_approval.pending_count(write_approval.SKILLS) == 0


def test_proposal_evidence_schema_is_closed_and_optional():
    from tools.skill_manager_tool import SKILL_MANAGE_SCHEMA

    evidence = SKILL_MANAGE_SCHEMA["parameters"]["properties"]["proposal_evidence"]
    assert evidence["type"] == "object"
    assert evidence["additionalProperties"] is False
    assert set(evidence["required"]) == {"kind", "message_refs", "reason"}
    assert "proposal_evidence" not in SKILL_MANAGE_SCHEMA["parameters"]["required"]


def test_read_paths_only_touch_usage_not_skill_content_or_proposals(
    tmp_path, monkeypatch, background_context
):
    from tools.skill_manager_guards import mark_background_review_skill_read
    from tools.skill_proposal_candidate import compute_base_hash
    from tools.skill_proposals import list_skill_proposals
    from tools.skills_tool import skill_view, skills_list

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _mode(monkeypatch, "propose")
    existing = _existing_skill(tmp_path)
    mark_background_review_skill_read(existing / "SKILL.md")
    before = compute_base_hash(existing)

    assert json.loads(skills_list())["success"] is True
    viewed = json.loads(skill_view("existing"))
    assert viewed["success"] is True

    assert compute_base_hash(existing) == before
    assert list_skill_proposals() == []
