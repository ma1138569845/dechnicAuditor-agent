from tools.skill_intent import (
    SkillWriteIntent,
    bind_skill_write_context,
    current_skill_write_context,
    normal_skill_context,
    reset_skill_write_context,
)
from tools.skill_intent_resolve import resolve_skill_write_context

import pytest


def test_with_intent_returns_a_copy_instead_of_mutating_the_context():
    normal = normal_skill_context(task_id="turn-1", session_id="session-1")
    explicit = normal.with_intent(SkillWriteIntent.USER_LEARN)

    assert normal.intent is SkillWriteIntent.NORMAL
    assert explicit.intent is SkillWriteIntent.USER_LEARN
    assert explicit.attended is True
    assert explicit.task_id == "turn-1"
    assert explicit.session_id == "session-1"


def test_context_reset_prevents_cross_turn_trust_leak():
    baseline = current_skill_write_context()
    token = bind_skill_write_context(
        normal_skill_context(task_id="turn-1", session_id="session-1").with_intent(
            SkillWriteIntent.USER_LEARN
        )
    )

    assert current_skill_write_context().intent is SkillWriteIntent.USER_LEARN
    reset_skill_write_context(token)
    assert current_skill_write_context() == baseline


def test_run_conversation_resets_context_when_the_turn_raises(monkeypatch):
    from agent import conversation_loop

    baseline = current_skill_write_context()
    learned = resolve_skill_write_context(
        SkillWriteIntent.USER_LEARN, task_id="turn-1", session_id="session-1"
    )

    def fail_after_binding(*_args, **_kwargs):
        assert current_skill_write_context() == learned
        raise RuntimeError("turn failed")

    monkeypatch.setattr(conversation_loop, "_run_conversation_turn", fail_after_binding)

    class FakeAgent:
        session_id = "session-1"

    with pytest.raises(RuntimeError, match="turn failed"):
        conversation_loop.run_conversation(
            FakeAgent(), "remember this", skill_write_context=learned
        )

    assert current_skill_write_context() == baseline
