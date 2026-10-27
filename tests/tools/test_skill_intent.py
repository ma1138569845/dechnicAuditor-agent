from tools.skill_intent import SkillWriteIntent, normal_skill_context


def test_with_intent_returns_a_copy_instead_of_mutating_the_context():
    normal = normal_skill_context(task_id="turn-1", session_id="session-1")
    explicit = normal.with_intent(SkillWriteIntent.USER_LEARN)

    assert normal.intent is SkillWriteIntent.NORMAL
    assert explicit.intent is SkillWriteIntent.USER_LEARN
    assert explicit.attended is True
    assert explicit.task_id == "turn-1"
    assert explicit.session_id == "session-1"
