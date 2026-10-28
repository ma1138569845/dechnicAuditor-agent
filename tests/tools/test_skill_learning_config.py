from dataclasses import FrozenInstanceError

import pytest

from hermes_cli.config_defaults import DEFAULT_CONFIG
from tools import skill_learning_config
from tools.skill_learning_config import SkillLearningConfig, get_skill_learning_config


def test_truthy_mode_is_rejected_and_defaults_to_propose():
    cfg = get_skill_learning_config({
        "skills": {
            "auto_learning": {
                "mode": True,
                "proposal_ttl_days": 0,
                "max_pending": -1,
            }
        }
    })

    assert cfg.mode == "propose"
    assert cfg.proposal_ttl_days == 14
    assert cfg.max_pending == 25
    assert any("skills.auto_learning.mode" in warning for warning in cfg.warnings)


def test_empty_config_produces_the_locked_defaults():
    cfg = get_skill_learning_config({})

    assert cfg.mode == "propose"
    assert cfg.max_pending_per_target == 5
    assert cfg.max_pending_per_anchor == 1
    assert cfg.history_retention_days == 30
    assert cfg.reminders_mode == "badge_only"
    assert cfg.max_attempts_per_proposal == 3
    assert cfg.cooldown_hours == 24
    assert cfg.warnings == ()


def test_non_mapping_containers_and_target_cap_fall_back_safely():
    malformed_root = get_skill_learning_config([])  # type: ignore[arg-type]
    assert malformed_root.mode == "propose"
    assert malformed_root.max_pending == 25
    assert any("config root" in warning for warning in malformed_root.warnings)

    malformed = get_skill_learning_config({"skills": {"auto_learning": []}})
    assert malformed.mode == "propose"
    assert malformed.max_pending == 25
    assert any("must be a mapping" in warning for warning in malformed.warnings)

    inconsistent = get_skill_learning_config({
        "skills": {
            "auto_learning": {
                "max_pending": 2,
                "max_pending_per_target": 5,
            }
        }
    })
    assert inconsistent.max_pending == 2
    assert inconsistent.max_pending_per_target == 2
    assert any("max_pending_per_target" in warning for warning in inconsistent.warnings)


@pytest.mark.parametrize("mode", [True, 1, "Auto", "ON", "yes", ""])
def test_mode_accepts_only_exact_lowercase_enum_values(mode):
    cfg = get_skill_learning_config({
        "skills": {"auto_learning": {"mode": mode}}
    })

    assert cfg.mode == "propose"
    assert any("skills.auto_learning.mode" in warning for warning in cfg.warnings)


@pytest.mark.parametrize("mode", ["propose", "off", "auto"])
def test_mode_preserves_exact_supported_values(mode):
    cfg = get_skill_learning_config({
        "skills": {"auto_learning": {"mode": mode}}
    })

    assert cfg.mode == mode
    assert cfg.warnings == ()


@pytest.mark.parametrize(
    ("container", "key", "invalid", "default"),
    [
        ("auto_learning", "proposal_ttl_days", 0, 14),
        ("auto_learning", "max_pending", 501, 25),
        ("auto_learning", "max_pending_per_target", 51, 5),
        ("auto_learning", "max_pending_per_anchor", 11, 1),
        ("auto_learning", "history_retention_days", 366, 30),
        ("reminders", "max_attempts_per_proposal", 11, 3),
        ("reminders", "cooldown_hours", 169, 24),
    ],
)
def test_each_bounded_integer_falls_back_to_its_named_default(
    container, key, invalid, default
):
    if container == "reminders":
        auto_learning = {"reminders": {key: invalid}}
    else:
        auto_learning = {key: invalid}

    cfg = get_skill_learning_config({
        "skills": {"auto_learning": auto_learning}
    })

    assert getattr(cfg, key) == default
    assert any(key in warning for warning in cfg.warnings)


def test_non_mapping_reminders_fall_back_safely():
    cfg = get_skill_learning_config({
        "skills": {"auto_learning": {"reminders": []}}
    })

    assert cfg.reminders_mode == "badge_only"
    assert cfg.max_attempts_per_proposal == 3
    assert cfg.cooldown_hours == 24
    assert any("reminders" in warning for warning in cfg.warnings)


def test_non_mapping_skills_and_invalid_reminder_mode_fall_back_safely():
    malformed_skills = get_skill_learning_config({"skills": []})
    assert malformed_skills.mode == "propose"
    assert any("skills must be a mapping" in warning for warning in malformed_skills.warnings)

    invalid_reminder = get_skill_learning_config({
        "skills": {"auto_learning": {"reminders": {"mode": "popup"}}}
    })
    assert invalid_reminder.reminders_mode == "badge_only"
    assert any("reminders.mode" in warning for warning in invalid_reminder.warnings)


def test_invalid_reminder_limits_report_their_nested_config_path():
    cfg = get_skill_learning_config({
        "skills": {
            "auto_learning": {
                "reminders": {
                    "max_attempts_per_proposal": 11,
                    "cooldown_hours": 169,
                }
            }
        }
    })

    assert cfg.max_attempts_per_proposal == 3
    assert cfg.cooldown_hours == 24
    assert any(
        "skills.auto_learning.reminders.max_attempts_per_proposal" in warning
        for warning in cfg.warnings
    )
    assert any(
        "skills.auto_learning.reminders.cooldown_hours" in warning
        for warning in cfg.warnings
    )
    malformed_skills = get_skill_learning_config({"skills": []})
    assert malformed_skills.mode == "propose"
    assert any("skills must be a mapping" in warning for warning in malformed_skills.warnings)

    invalid_reminder = get_skill_learning_config({
        "skills": {"auto_learning": {"reminders": {"mode": "popup"}}}
    })
    assert invalid_reminder.reminders_mode == "badge_only"
    assert any("reminders.mode" in warning for warning in invalid_reminder.warnings)


@pytest.mark.parametrize(
    ("key", "invalid"),
    [
        ("proposal_ttl_days", "14"),
        ("max_pending", True),
        ("history_retention_days", 30.0),
    ],
)
def test_non_integer_and_bool_values_fall_back(key, invalid):
    cfg = get_skill_learning_config({
        "skills": {"auto_learning": {key: invalid}}
    })

    assert type(getattr(cfg, key)) is int
    assert any(key in warning for warning in cfg.warnings)


def test_config_is_frozen_and_warnings_are_a_tuple():
    cfg = get_skill_learning_config({})

    assert isinstance(cfg, SkillLearningConfig)
    assert isinstance(cfg.warnings, tuple)
    with pytest.raises(FrozenInstanceError):
        cfg.mode = "auto"  # type: ignore[misc]


def test_omitted_config_uses_readonly_loader(monkeypatch):
    calls = 0

    def load_config_readonly():
        nonlocal calls
        calls += 1
        return {"skills": {"auto_learning": {"mode": "off"}}}

    monkeypatch.setattr(skill_learning_config, "load_config_readonly", load_config_readonly)

    cfg = skill_learning_config.get_skill_learning_config()

    assert calls == 1
    assert cfg.mode == "off"


def test_default_config_matches_reader_defaults():
    cfg = get_skill_learning_config(DEFAULT_CONFIG)

    assert cfg.mode == "propose"
    assert cfg.proposal_ttl_days == 14
    assert cfg.max_pending == 25
    assert cfg.max_pending_per_target == 5
    assert cfg.max_pending_per_anchor == 1
    assert cfg.history_retention_days == 30
    assert cfg.reminders_mode == "badge_only"
    assert cfg.max_attempts_per_proposal == 3
    assert cfg.cooldown_hours == 24
    assert cfg.warnings == ()
