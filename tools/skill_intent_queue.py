"""Queue item that carries a trusted skill intent beside its prompt text."""

from __future__ import annotations

from dataclasses import dataclass

from tools.skill_intent import SkillWriteIntent, normal_skill_context


@dataclass(frozen=True, slots=True)
class QueuedSkillIntentPrompt:
    text: str
    intent: SkillWriteIntent

    @property
    def context(self):
        return normal_skill_context().with_intent(self.intent)

    def __str__(self) -> str:
        return self.text


def build_queued_learn_prompt(user_request: str) -> QueuedSkillIntentPrompt:
    """Build the expanded learn turn with its dispatcher-owned trust context."""
    from agent.learn_prompt import build_learn_prompt

    return QueuedSkillIntentPrompt(
        build_learn_prompt(user_request), SkillWriteIntent.USER_LEARN
    )
