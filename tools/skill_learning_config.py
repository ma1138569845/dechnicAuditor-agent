"""Validated read-only access to skill learning configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hermes_cli.config import load_config_readonly


@dataclass(frozen=True)
class SkillLearningConfig:
    mode: str
    proposal_ttl_days: int
    max_pending: int
    max_pending_per_target: int
    max_pending_per_anchor: int
    history_retention_days: int
    reminders_mode: str
    max_attempts_per_proposal: int
    cooldown_hours: int
    warnings: tuple[str, ...]


_DEFAULTS = SkillLearningConfig(
    mode="propose",
    proposal_ttl_days=14,
    max_pending=25,
    max_pending_per_target=5,
    max_pending_per_anchor=1,
    history_retention_days=30,
    reminders_mode="badge_only",
    max_attempts_per_proposal=3,
    cooldown_hours=24,
    warnings=(),
)


def _bounded_int(
    raw: Mapping[str, Any],
    key: str,
    default: int,
    low: int,
    high: int,
    warnings: list[str],
    prefix: str = "skills.auto_learning",
) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        warnings.append(
            f"{prefix}.{key} must be {low}..{high}; using {default}"
        )
        return default
    return value


def get_skill_learning_config(
    config: Mapping[str, Any] | None = None,
) -> SkillLearningConfig:
    warnings: list[str] = []
    root = load_config_readonly() if config is None else config
    if not isinstance(root, Mapping):
        warnings.append("config root must be a mapping; using skill defaults")
        root = {}

    raw_skills = root.get("skills")
    if raw_skills is None:
        skills: Mapping[str, Any] = {}
    elif isinstance(raw_skills, Mapping):
        skills = raw_skills
    else:
        warnings.append("skills must be a mapping; using defaults")
        skills = {}

    raw_auto = skills.get("auto_learning")
    if raw_auto is None:
        raw: Mapping[str, Any] = {}
    elif isinstance(raw_auto, Mapping):
        raw = raw_auto
    else:
        warnings.append("skills.auto_learning must be a mapping; using defaults")
        raw = {}

    mode = raw.get("mode", _DEFAULTS.mode)
    if not isinstance(mode, str) or mode not in {"propose", "off", "auto"}:
        warnings.append(
            "skills.auto_learning.mode must be one of propose|off|auto; using propose"
        )
        mode = _DEFAULTS.mode

    raw_reminders = raw.get("reminders")
    if raw_reminders is None:
        reminders: Mapping[str, Any] = {}
    elif isinstance(raw_reminders, Mapping):
        reminders = raw_reminders
    else:
        warnings.append(
            "skills.auto_learning.reminders must be a mapping; using defaults"
        )
        reminders = {}

    reminder_mode = reminders.get("mode", _DEFAULTS.reminders_mode)
    if not isinstance(reminder_mode, str) or reminder_mode != "badge_only":
        warnings.append("skills.auto_learning.reminders.mode must be badge_only")
        reminder_mode = _DEFAULTS.reminders_mode

    max_pending = _bounded_int(
        raw, "max_pending", _DEFAULTS.max_pending, 1, 500, warnings
    )
    max_target = _bounded_int(
        raw,
        "max_pending_per_target",
        _DEFAULTS.max_pending_per_target,
        1,
        50,
        warnings,
    )
    if max_target > max_pending:
        fallback_target = min(_DEFAULTS.max_pending_per_target, max_pending)
        warnings.append(
            "skills.auto_learning.max_pending_per_target must be <= max_pending; "
            f"using {fallback_target}"
        )
        max_target = fallback_target

    return SkillLearningConfig(
        mode=mode,
        proposal_ttl_days=_bounded_int(
            raw,
            "proposal_ttl_days",
            _DEFAULTS.proposal_ttl_days,
            1,
            365,
            warnings,
        ),
        max_pending=max_pending,
        max_pending_per_target=max_target,
        max_pending_per_anchor=_bounded_int(
            raw,
            "max_pending_per_anchor",
            _DEFAULTS.max_pending_per_anchor,
            1,
            10,
            warnings,
        ),
        history_retention_days=_bounded_int(
            raw,
            "history_retention_days",
            _DEFAULTS.history_retention_days,
            1,
            365,
            warnings,
        ),
        reminders_mode=reminder_mode,
        max_attempts_per_proposal=_bounded_int(
            reminders,
            "max_attempts_per_proposal",
            _DEFAULTS.max_attempts_per_proposal,
            1,
            10,
            warnings,
        "skills.auto_learning.reminders",
        ),
        cooldown_hours=_bounded_int(
            reminders,
            "cooldown_hours",
            _DEFAULTS.cooldown_hours,
            1,
            168,
            warnings,
        "skills.auto_learning.reminders",
        ),
        warnings=tuple(warnings),
    )
