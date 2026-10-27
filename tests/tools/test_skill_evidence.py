from tools.skill_evidence import validate_proposal_evidence
from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext


def _ctx(*refs: int) -> SkillWriteIntentContext:
    return SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-1",
        session_id="session-1",
        review_run_id="review-1",
        review_message_refs=frozenset(refs),
        review_snapshot_digest="sha256:" + "b" * 64,
    )


def test_invented_message_reference_is_rejected():
    result = validate_proposal_evidence(
        [{"kind": "user_correction", "message_refs": [99], "reason": "check first"}],
        _ctx(2, 5),
    )

    assert not result.ok
    assert result.error == "unverified_message_ref"


def test_repeated_class_requires_two_occurrences():
    result = validate_proposal_evidence(
        [{"kind": "repeated_class", "message_refs": [2], "reason": "same need twice"}],
        _ctx(2, 5),
    )

    assert not result.ok
    assert result.error == "repeated_class_requires_two_refs"


def test_secret_material_blocks_without_echoing_the_secret():
    result = validate_proposal_evidence(
        [{
            "kind": "user_correction",
            "message_refs": [2],
            "reason": "password=super-secret-value",
        }],
        _ctx(2),
    )

    assert not result.ok
    assert result.error == "sensitive_evidence"
    assert "super-secret-value" not in str(result)
