"""Structured trust context for skill writes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class SkillWriteIntent(Enum):
    NORMAL = "normal"
    USER_LEARN = "user_learn"
    BACKGROUND_REVIEW = "background_review"


@dataclass(frozen=True, slots=True)
class SkillWriteIntentContext:
    intent: SkillWriteIntent
    origin: str
    attended: bool
    task_id: str
    session_id: str
    review_run_id: str | None
    review_message_refs: frozenset[int]
    review_snapshot_digest: str | None

    def with_intent(self, intent: SkillWriteIntent) -> SkillWriteIntentContext:
        return replace(self, intent=intent)


def normal_skill_context(
    *,
    task_id: str = "",
    session_id: str = "",
    attended: bool = True,
) -> SkillWriteIntentContext:
    return SkillWriteIntentContext(
        intent=SkillWriteIntent.NORMAL,
        origin="foreground",
        attended=attended,
        task_id=task_id,
        session_id=session_id,
        review_run_id=None,
        review_message_refs=frozenset(),
        review_snapshot_digest=None,
    )
