import os
from pathlib import Path

import pytest

from agent.skill_utils import iter_skill_index_files
from tools.skill_path_security import SkillPathError, resolve_skill_relative_path


def test_symlink_cycle_is_visited_once(tmp_path):
    skill_dir = tmp_path / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
    references = skill_dir / "references"
    references.mkdir()
    try:
        os.symlink(tmp_path / "skills", references / "loop", target_is_directory=True)
    except OSError:
        pytest.skip("host does not permit directory symlinks")

    found = list(iter_skill_index_files(tmp_path / "skills", "SKILL.md"))

    assert found == [skill_dir / "SKILL.md"]


@pytest.mark.parametrize("candidate", [
    "../escape.md",
    r"C:\Windows\system.ini",
    r"\\server\share\secret.md",
    "references/ok\x00.txt",
    "references/line\nbreak.md",
])
def test_relative_path_rejects_escape_and_control_chars(tmp_path, candidate):
    skill_dir = tmp_path / "skills" / "alpha"
    skill_dir.mkdir(parents=True)

    with pytest.raises(SkillPathError):
        resolve_skill_relative_path(skill_dir, candidate, [tmp_path / "skills"])
