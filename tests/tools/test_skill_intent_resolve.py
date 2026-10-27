from tools.skill_intent import SkillWriteIntent, normal_skill_context
from tools.skill_intent_resolve import resolve_skill_write_context
import pytest


def test_context_wins_and_a_conflicting_enum_is_refused():
    review = normal_skill_context(task_id="review", session_id="session").with_intent(
        SkillWriteIntent.BACKGROUND_REVIEW
    )

    resolved = resolve_skill_write_context(SkillWriteIntent.BACKGROUND_REVIEW, review)

    assert resolved == review
    with pytest.raises(ValueError):
        resolve_skill_write_context(SkillWriteIntent.USER_LEARN, review)


def test_a_bare_enum_creates_a_base_context_and_absence_stays_normal():
    learned = resolve_skill_write_context(
        SkillWriteIntent.USER_LEARN, task_id="turn", session_id="session"
    )
    absent = resolve_skill_write_context(task_id="turn", session_id="session")

    assert learned.intent is SkillWriteIntent.USER_LEARN
    assert learned.origin == "foreground"
    assert absent.intent is SkillWriteIntent.NORMAL


def test_a_context_missing_turn_identity_is_enriched_without_changing_its_intent():
    learned = normal_skill_context().with_intent(SkillWriteIntent.USER_LEARN)

    resolved = resolve_skill_write_context(
        context=learned, task_id="turn-1", session_id="session-1"
    )

    assert resolved.intent is SkillWriteIntent.USER_LEARN
    assert resolved.task_id == "turn-1"
    assert resolved.session_id == "session-1"


def test_context_identity_cannot_be_rebound_to_another_session():
    learned = normal_skill_context(session_id="session-a").with_intent(
        SkillWriteIntent.USER_LEARN
    )

    with pytest.raises(ValueError, match="does not belong to this turn"):
        resolve_skill_write_context(context=learned, session_id="session-b")
