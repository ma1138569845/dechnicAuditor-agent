"""解析 tools/energy_audit 所在的项目根目录，并挂到 sys.path。

解析顺序（先命中先用，全部失败则返回 None，不抛异常）：
    1. 环境变量 EA_TOOLS_ROOT
    2. 从当前工作目录逐级向上查找 tools/energy_audit
    3. hermes profile 的 config.yaml → terminal.cwd
    4. 从本文件位置逐级向上查找

不硬编码任何绝对路径。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterator, Optional, Tuple

_MARKER = Path("tools") / "energy_audit"
_MAX_WALK_UP = 8


def _is_root(path: Path) -> bool:
    return (path / _MARKER).is_dir()


def _walk_up(start: Path) -> Iterator[Path]:
    current = start.resolve()
    for _ in range(_MAX_WALK_UP):
        yield current
        if current.parent == current:
            break
        current = current.parent


def _profile_dir() -> Optional[Path]:
    """向上查找 hermes profile 目录（同时含 config.yaml 与 profile.yaml）。"""
    for candidate in _walk_up(Path(__file__).parent):
        if (candidate / "config.yaml").is_file() and (candidate / "profile.yaml").is_file():
            return candidate
    return None


def _cwd_from_profile_config() -> Optional[Path]:
    """读 profile/config.yaml 的 terminal.cwd（正则解析，不依赖 pyyaml）。"""
    profile = _profile_dir()
    if profile is None:
        return None
    try:
        text = (profile / "config.yaml").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^\s{2,}cwd:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return None
    raw = match.group(1).strip().strip("'\"")
    return Path(raw) if raw else None


def resolve_tools_root() -> Optional[Path]:
    """返回包含 tools/energy_audit 的目录，找不到返回 None。"""
    env_root = os.environ.get("EA_TOOLS_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser()
        if _is_root(candidate):
            return candidate

    for candidate in _walk_up(Path.cwd()):
        if _is_root(candidate):
            return candidate

    config_cwd = _cwd_from_profile_config()
    if config_cwd is not None and _is_root(config_cwd):
        return config_cwd

    for candidate in _walk_up(Path(__file__).parent):
        if _is_root(candidate):
            return candidate

    return None


def ensure_tools_on_path() -> Tuple[Optional[Path], str]:
    """把项目根目录插到 sys.path 头部。返回 (root, 错误信息)，成功时错误信息为 ''。"""
    root = resolve_tools_root()
    if root is None:
        return None, (
            "找不到 tools/energy_audit。请设置 EA_TOOLS_ROOT 指向包含 "
            "tools/energy_audit 的项目根目录，或在该项目目录下运行本脚本。"
        )
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root, ""
