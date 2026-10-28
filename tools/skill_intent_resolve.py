"""Resolve one turn's skill-write context without letting a bare enum win."""

from __future__ import annotations

from dataclasses import replace

from tools.skill_intent import (
    SkillWriteIntent,
    SkillWriteIntentContext,
    current_skill_write_context,
    normal_skill_context,
)


def resolve_skill_write_context(
    intent: SkillWriteIntent | None = None,
    context: SkillWriteIntentContext | None = None,
    *,
    task_id: str = "",
    session_id: str = "",
) -> SkillWriteIntentContext:
    """Context is authoritative. A lone enum creates a base context; both must agree."""
    if context is not None and not isinstance(context, SkillWriteIntentContext):
        raise TypeError("skill write context must be SkillWriteIntentContext")
    if intent is not None and not isinstance(intent, SkillWriteIntent):
        raise TypeError("skill write intent must be SkillWriteIntent")
    if context is not None and intent is not None and context.intent is not intent:
        raise ValueError("skill write intent does not match its context")
    if context is not None:
        if context.task_id and task_id and context.task_id != task_id:
            raise ValueError("skill write context does not belong to this turn")
        if context.session_id and session_id and context.session_id != session_id:
            raise ValueError("skill write context does not belong to this turn")
        return replace(
            context,
            task_id=context.task_id or task_id,
            session_id=context.session_id or session_id,
        )
    if intent is None:
        return normal_skill_context(task_id=task_id, session_id=session_id)
    base = normal_skill_context(task_id=task_id, session_id=session_id)
    return base if intent is SkillWriteIntent.NORMAL else base.with_intent(intent)


def parse_skill_write_intent(value) -> SkillWriteIntent | None:
    """Exact enum values only. Text and unknown values cannot create trust."""
    if isinstance(value, SkillWriteIntent):
        return value
    if not isinstance(value, str):
        return None
    try:
        return SkillWriteIntent(value)
    except ValueError:
        return None


def mirror_skill_write_context(context: SkillWriteIntentContext | None = None) -> tuple:
    """Mirror the authoritative context into the legacy origin and attended variables."""
    from tools.skill_provenance import set_current_write_origin, set_review_attended

    active = context or current_skill_write_context()
    origin = "background_review" if active.intent is SkillWriteIntent.BACKGROUND_REVIEW else "foreground"
    return set_current_write_origin(origin), set_review_attended(active.attended)
