"""Fail-closed resolution for paths supplied inside a skill package."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath


class SkillPathError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_skill_relative_path(
    skill_dir: Path,
    relative: str,
    allowed_roots: Sequence[Path],
) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise SkillPathError("invalid_path", "skill path must be a non-empty string")

    posix = PurePosixPath(relative.replace("\\", "/"))
    windows = PureWindowsPath(relative)
    if (
        relative.startswith("\\\\")
        or windows.drive
        or posix.is_absolute()
        or windows.is_absolute()
        or "\x00" in relative
        or any(ord(char) < 32 for char in relative)
        or any(part in {"..", ""} for part in posix.parts)
    ):
        raise SkillPathError("path_escape", "skill path escapes its allowed root")

    candidate = (Path(skill_dir) / Path(*posix.parts)).resolve(strict=False)
    validate_resolved_skill_path(Path(skill_dir), candidate, allowed_roots)
    return candidate


def validate_resolved_skill_path(
    skill_dir: Path,
    candidate: Path,
    allowed_roots: Sequence[Path],
) -> None:
    resolved_skill = Path(skill_dir).resolve(strict=False)
    resolved_candidate = Path(candidate).resolve(strict=False)
    for root in allowed_roots:
        resolved_root = Path(root).resolve(strict=False)
        if resolved_skill.is_relative_to(resolved_root) and resolved_candidate.is_relative_to(resolved_root):
            return
    raise SkillPathError("path_escape", "skill path escapes its allowed root")
