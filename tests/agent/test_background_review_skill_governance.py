import json
from dataclasses import replace

from agent.background_review import (
    _COMBINED_REVIEW_PROMPT,
    _SKILL_REVIEW_PROMPT,
    _action_lines,
    build_review_skill_context,
    summarize_background_review_actions,
)
from tools import skill_learning_config
from tools.skill_intent import bind_skill_write_context, reset_skill_write_context
from tools.skill_manager_tool import skill_manage
from tools.skill_proposals import list_skill_proposals
from tools.skill_intent import SkillWriteIntent


class _Agent:
    session_id = "session-1"
    _current_task_id = "task-1"


class _Run:
    review_run_id = "review-1"


def test_review_context_can_only_reference_the_snapshot():
    snapshot = [
        {"role": "user", "content": "use the current audit workflow"},
        {"role": "assistant", "content": "completed"},
    ]

    context = build_review_skill_context(_Agent(), snapshot, _Run(), explicit=False)

    assert context.intent is SkillWriteIntent.BACKGROUND_REVIEW
    assert context.task_id == "task-1"
    assert context.session_id == "session-1"
    assert context.review_run_id == "review-1"
    assert context.review_message_refs == frozenset({1, 2})
    assert context.review_snapshot_digest.startswith("sha256:")
    assert len(context.review_snapshot_digest) == 71


def test_prompts_prefer_no_proposal_and_do_not_use_activity_as_evidence():
    assert "Be ACTIVE" not in _SKILL_REVIEW_PROMPT
    assert "Be ACTIVE" not in _COMBINED_REVIEW_PROMPT
    assert "Nothing to propose." in _SKILL_REVIEW_PROMPT
    assert "Nothing to propose." in _COMBINED_REVIEW_PROMPT
    assert "activity alone" in _SKILL_REVIEW_PROMPT.lower()


def test_summary_requires_a_complete_proposal_receipt():
    detail = {"tool": "skill_manage"}
    assert _action_lines({"staged": True, "message": "queued"}, detail, False) == []
    assert (
        _action_lines(
            {"staged": True, "proposal_staged": True, "message": "queued"},
            detail,
            False,
        )
        == []
    )
    assert _action_lines(
        {
            "staged": True,
            "proposal_staged": True,
            "pending_id": "skp_1",
            "message": "Proposal skp_1 queued; skill unchanged.",
        },
        detail,
        False,
    ) == ["Proposal skp_1 queued; skill unchanged."]


def test_unrelated_successful_turn_has_no_skill_summary():
    tool_message = {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": json.dumps({"success": True, "message": "Nothing to propose."}),
    }
    assert summarize_background_review_actions([tool_message], []) == []


def test_combined_review_with_memory_only_does_not_claim_a_skill_update():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-memory",
                    "function": {
                        "name": "memory",
                        "arguments": json.dumps(
                            {
                                "action": "add",
                                "target": "memory",
                                "content": "Use UTC logs.",
                            }
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-memory",
            "content": json.dumps(
                {"success": True, "target": "memory", "message": "Entry added."}
            ),
        },
    ]

    actions = summarize_background_review_actions(messages, [])

    assert len(actions) == 1
    assert "skill" not in actions[0].lower()


_SKILL_BODY = (
    "---\n"
    "name: audit-report\n"
    "description: Use when writing an audit report.\n"
    "---\n\n"
    "Verify sources before writing.\n"
)


def _review_mode(monkeypatch, mode="propose"):
    baseline = skill_learning_config.get_skill_learning_config()
    monkeypatch.setattr(
        skill_learning_config,
        "get_skill_learning_config",
        lambda config=None: replace(baseline, mode=mode),
    )


def _fake_reviewer(context, evidence, snapshot):
    class Reviewer:
        _session_messages = []

        def run_conversation(self, **_kwargs):
            if evidence is None:
                self._session_messages = [
                    {"role": "assistant", "content": "Nothing to propose."}
                ]
                return
            result = skill_manage(
                operations=[
                    {
                        "action": "create",
                        "name": "audit-report",
                        "content": _SKILL_BODY,
                    }
                ],
                proposal_evidence=evidence,
                task_id=context.task_id,
                session_id=context.session_id,
            )
            self._session_messages = [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-skill",
                            "function": {
                                "name": "skill_manage",
                                "arguments": json.dumps(
                                    {
                                        "operations": [
                                            {
                                                "action": "create",
                                                "name": "audit-report",
                                                "content": _SKILL_BODY,
                                            }
                                        ],
                                        "proposal_evidence": evidence,
                                    }
                                ),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-skill",
                    "content": result,
                },
            ]

    reviewer = Reviewer()
    reviewer.snapshot = snapshot
    return reviewer


def _run_review_case(tmp_path, monkeypatch, scenario):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _review_mode(monkeypatch)
    snapshot = [
        {"role": "user", "content": scenario["user"]},
        {"role": "assistant", "content": scenario["assistant"]},
    ]
    context = build_review_skill_context(_Agent(), snapshot, _Run(), explicit=False)
    token = bind_skill_write_context(context)
    try:
        reviewer = _fake_reviewer(context, scenario.get("evidence"), snapshot)
        reviewer.run_conversation()
    finally:
        reset_skill_write_context(token)
    actions = summarize_background_review_actions(reviewer._session_messages, [])
    return actions, list_skill_proposals()


def test_fake_reviewer_does_not_propose_for_ordinary_or_transient_turns(
    tmp_path, monkeypatch
):
    for scenario in (
        {
            "user": "summarize this report",
            "assistant": "The report is summarized.",
        },
        {
            "user": "try the API",
            "assistant": "The network failed once; the retry succeeded.",
        },
        {
            "user": "what did we learn?",
            "assistant": "This idea may be useful.",
        },
    ):
        actions, proposals = _run_review_case(tmp_path, monkeypatch, scenario)
        assert actions == []
        assert proposals == []


def test_fake_reviewer_proposes_only_with_verifiable_evidence(tmp_path, monkeypatch):
    for evidence in (
        {
            "kind": "user_correction",
            "message_refs": [1],
            "reason": "verify sources before writing",
        },
        {
            "kind": "skill_incomplete",
            "message_refs": [2],
            "reason": "the loaded workflow omitted source verification",
        },
        {
            "kind": "repeated_class",
            "message_refs": [1, 2],
            "reason": "the same audit prerequisite recurred",
        },
    ):
        actions, proposals = _run_review_case(
            tmp_path / evidence["kind"],
            monkeypatch,
            {
                "user": "use the audit workflow and fix the omission",
                "assistant": "Source verification was missing and is now required.",
                "evidence": evidence,
            },
        )
        assert len(proposals) == 1
        assert proposals[0]["evidence"][0]["kind"] == evidence["kind"]
        assert len(actions) == 1
        assert "Proposal skp_" in actions[0]
