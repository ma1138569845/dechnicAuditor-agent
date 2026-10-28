"""Canonical candidate construction for proposed skill mutations."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.skill_linter import lint_content
from tools.skill_path_security import SkillPathError, resolve_skill_relative_path
from tools.skills_guard import scan_skill, should_allow_install


_TEXT_FIELDS = ("content", "file_content", "old_string", "new_string")


def compute_base_hash(skill_dir: Path | None) -> str:
    entries: list[tuple[str, str]] = []
    if skill_dir is not None and skill_dir.exists():
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                entries.append(
                    (
                        path.relative_to(skill_dir).as_posix(),
                        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )
            elif path.is_dir() and not any(path.iterdir()):
                entries.append((path.relative_to(skill_dir).as_posix() + "/", "empty"))
    return _digest(entries)


def canonicalize_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(operation)
    if source.get("action") == "batch":
        operations = [
            _canonical_single(op) for op in source.get("operations", []) if isinstance(op, Mapping)
        ]
        canonical = {"action": "batch", "operations": operations}
    else:
        canonical = _canonical_single(source)
    names = operation_target_names(canonical)
    base_hashes = operation_base_hashes(canonical)
    canonical.update(
        {
            "base_hash": base_hash_digest(base_hashes),
            "base_hashes": base_hashes,
            "target_names": names,
        }
    )
    return canonical


def operation_target_names(operation: Mapping[str, Any]) -> list[str]:
    operations = (
        operation.get("operations", [])
        if operation.get("action") == "batch"
        else [operation]
    )
    return list(
        dict.fromkeys(
            str(op.get("name"))
            for op in operations
            if isinstance(op, Mapping) and op.get("name")
        )
    )


def operation_base_hashes(operation: Mapping[str, Any]) -> dict[str, str]:
    result = {}
    for name in operation_target_names(operation):
        target = _target_path(name, operation)
        result[name] = compute_base_hash(target if target and target.exists() else None)
    return result


def base_hash_digest(base_hashes: Mapping[str, str]) -> str:
    if len(base_hashes) == 1:
        return next(iter(base_hashes.values()))
    return _digest(sorted(base_hashes.items()))


def validate_proposed_operation(operation: Mapping[str, Any]) -> str | None:
    """Reconstruct every touched skill in a temp tree and fail with a stable reason."""
    expected_bases = operation.get("base_hashes")
    current_bases = operation_base_hashes(operation)
    if isinstance(expected_bases, Mapping) and dict(expected_bases) != current_bases:
        return "target_changed"
    names = operation_target_names(operation)
    if not names:
        return "not_staged"
    temp_root = Path(tempfile.mkdtemp(prefix="skill-proposal-candidate-"))
    try:
        states = _copy_current_targets(temp_root, names, operation)
        operations = (
            operation.get("operations", [])
            if operation.get("action") == "batch"
            else [operation]
        )
        for op in operations:
            if not isinstance(op, Mapping):
                return "not_staged"
            error = _simulate_operation(temp_root, states, op)
            if error:
                return error
        return _validate_final_states(states)
    except SkillPathError:
        return "unsafe_target"
    except (OSError, ValueError):
        return "not_staged"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _canonical_single(operation: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(operation)
    action = result.get("action")
    if not isinstance(action, str) or not action:
        return {"action": action, "operations": []}
    result["action"] = action
    if result.get("name") is not None:
        result["name"] = str(result["name"])
    if result.get("category") is not None:
        result["category"] = str(result["category"])
    if action in {"patch", "write_file", "remove_file"}:
        result["file_path"] = str(result.get("file_path") or "SKILL.md").replace("\\", "/")
    elif result.get("file_path"):
        result["file_path"] = str(result["file_path"]).replace("\\", "/")
    for key in _TEXT_FIELDS:
        if isinstance(result.get(key), str):
            result[key] = result[key].replace("\r\n", "\n")
    if action == "patch" and result.get("old_string"):
        result["anchor_key"] = _digest(
            {
                "skill": result.get("name"),
                "file_path": result.get("file_path", "SKILL.md"),
                "normalized_old_string": result["old_string"],
            }
        )
    else:
        result["anchor_key"] = None
    result["result_digest"] = _result_digest(result)
    return result


def _result_digest(operation: Mapping[str, Any]) -> str:
    action = operation.get("action")
    if action in {"create", "edit"} or (action == "patch" and operation.get("content")):
        value: Any = operation.get("content", "")
    elif action == "patch":
        value = operation.get("new_string", "")
    elif action == "write_file":
        value = operation.get("file_content", "")
    else:
        value = {"action": action, "file_path": operation.get("file_path")}
    return _digest(value)


def _target_path(name: str, operation: Mapping[str, Any]) -> Path | None:
    from tools import skill_manager_tool as smt

    existing = smt._find_skill(name)
    if existing:
        return Path(existing["path"])
    operations = (
        operation.get("operations", [])
        if operation.get("action") == "batch"
        else [operation]
    )
    create = next(
        (
            op
            for op in operations
            if isinstance(op, Mapping)
            and op.get("action") == "create"
            and op.get("name") == name
        ),
        None,
    )
    return smt._resolve_skill_dir(name, create.get("category")) if create else None


def _copy_current_targets(
    temp_root: Path, names: list[str], operation: Mapping[str, Any]
) -> dict[str, Path]:
    states = {}
    for name in names:
        state = temp_root / name.replace("/", "__")
        source = _existing_target(name)
        if source is not None:
            shutil.copytree(source, state)
        states[name] = state
    return states


def _existing_target(name: str) -> Path | None:
    from tools import skill_manager_tool as smt

    existing = smt._find_skill(name)
    return Path(existing["path"]) if existing else None


def _simulate_operation(
    temp_root: Path, states: dict[str, Path], operation: Mapping[str, Any]
) -> str | None:
    from tools import skill_manager_tool as smt

    action, name = operation.get("action"), str(operation.get("name") or "")
    state = states.get(name)
    if not name or action not in {
        "create",
        "edit",
        "patch",
        "write_file",
        "remove_file",
        "delete",
    }:
        return "not_staged"
    if action == "create":
        content = operation.get("content")
        if state is None or state.exists() or not isinstance(content, str):
            return "not_staged"
        if (
            smt._validate_name(name)
            or smt._validate_category(operation.get("category"))
            or smt._validate_frontmatter(content)
            or smt._validate_content_size(content)
        ):
            return "not_staged"
        state.mkdir(parents=True)
        (state / "SKILL.md").write_text(content, encoding="utf-8")
        return None
    if state is None or not state.exists():
        return "unsafe_target"
    if action == "delete":
        shutil.rmtree(state)
        return None
    if action == "edit":
        content = operation.get("content")
        if not isinstance(content, str):
            return "not_staged"
        if smt._validate_frontmatter(content) or smt._validate_content_size(content):
            return "not_staged"
        (state / "SKILL.md").write_text(content, encoding="utf-8")
        return None
    if action == "patch":
        return _simulate_patch(state, operation)
    if action == "write_file":
        return _simulate_write_file(temp_root, state, operation)
    return _simulate_remove_file(temp_root, state, operation)


def _simulate_patch(state: Path, operation: Mapping[str, Any]) -> str | None:
    from tools import skill_manager_tool as smt

    target = _safe_target(state, str(operation.get("file_path") or "SKILL.md"))
    if not target.exists():
        return "anchor_stale"
    content = operation.get("content")
    if isinstance(content, str) and content:
        if not operation.get("file_path") and smt._validate_frontmatter(content):
            return "not_staged"
        target.write_text(content, encoding="utf-8")
        return None
    old_string, new_string = operation.get("old_string"), operation.get("new_string")
    if not isinstance(old_string, str) or not isinstance(new_string, str):
        return "not_staged"
    from tools.fuzzy_match import fuzzy_find_and_replace

    original = target.read_text(encoding="utf-8-sig")
    updated, match_count, _strategy, match_error = fuzzy_find_and_replace(
        original, old_string, new_string, bool(operation.get("replace_all"))
    )
    if match_error or match_count < 1:
        return "anchor_stale"
    if smt._validate_content_size(updated, label=str(operation.get("file_path") or "SKILL.md")):
        return "not_staged"
    if str(operation.get("file_path") or "SKILL.md") == "SKILL.md" and smt._validate_frontmatter(updated):
        return "not_staged"
    target.write_text(updated, encoding="utf-8")
    return None


def _simulate_write_file(
    temp_root: Path, state: Path, operation: Mapping[str, Any]
) -> str | None:
    from tools import skill_manager_tool as smt

    file_path, content = operation.get("file_path"), operation.get("file_content")
    if smt._validate_file_path(str(file_path or "")) or not isinstance(content, str):
        return "unsafe_target"
    if len(content.encode("utf-8")) > smt.MAX_SKILL_FILE_BYTES:
        return "not_staged"
    if smt._validate_content_size(content, label=str(file_path)):
        return "not_staged"
    target = resolve_skill_relative_path(state, str(file_path), [temp_root])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return None


def _simulate_remove_file(
    temp_root: Path, state: Path, operation: Mapping[str, Any]
) -> str | None:
    from tools import skill_manager_tool as smt

    file_path = str(operation.get("file_path") or "")
    if smt._validate_file_path(file_path):
        return "unsafe_target"
    target = resolve_skill_relative_path(state, file_path, [temp_root])
    if not target.is_file():
        return "anchor_stale"
    target.unlink()
    return None


def _safe_target(state: Path, file_path: str) -> Path:
    if file_path == "SKILL.md":
        return state / "SKILL.md"
    from tools import skill_manager_tool as smt

    if smt._validate_file_path(file_path):
        raise SkillPathError("invalid_path", file_path)
    return resolve_skill_relative_path(state, file_path, [state.parent])


def _validate_final_states(states: Mapping[str, Path]) -> str | None:
    for state in states.values():
        if not state.exists():
            continue
        skill_md = state / "SKILL.md"
        if not skill_md.is_file():
            return "not_staged"
        if any(item.severity == "error" for item in lint_content(skill_md.read_text(encoding="utf-8"))):
            return "blocked_by_lint"
        allowed, _reason = should_allow_install(scan_skill(state, source="agent"), force=False)
        if allowed is not True:
            return "blocked_by_security"
    return None


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
