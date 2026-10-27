import json
from pathlib import Path

import pytest

from tools.skill_path_security import SkillPathError, resolve_skill_relative_path


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skill_proposals"


def test_path_fixture_cases_are_rejected(tmp_path):
    cases = json.loads((FIXTURES / "path_cases.json").read_text(encoding="utf-8"))
    skill_dir = tmp_path / "skills" / "alpha"
    skill_dir.mkdir(parents=True)

    for candidate in cases:
        with pytest.raises(SkillPathError):
            resolve_skill_relative_path(skill_dir, candidate, [tmp_path / "skills"])
