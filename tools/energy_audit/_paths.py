"""tools/energy_audit 模块统一的项目根目录解析。

所有 energy_audit 脚本都应通过 `from tools.energy_audit._paths import PROJECT_ROOT`
获取项目根路径，避免在每个脚本里重复硬编码或内联路径解析逻辑。

优先级（3 层降级）：
  Layer 1: 环境变量 HERMES_AGENT_HOME
  Layer 2: 包已安装（pip install -e .）—— 借 import 系统反推
  Layer 3: 从本文件 __file__ 向上爬，匹配 pyproject.toml + tools/energy_audit/

若三层全部失败，抛出 RuntimeError 并打印可操作的诊断信息（$PWD、
$HERMES_AGENT_HOME、__file__），由调用方决定是否降级到 CWD 或退出。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_MARKER_PROJECT = "pyproject.toml"
_MARKER_PACKAGE = "energy_audit"
_PACKAGE_PARENT = "energy_audit"  # 用于判定路径是否落在正确子树下


def _is_valid_root(candidate: Path) -> bool:
    """True 当且仅当 candidate 既是项目根，又包含本包目录。"""
    return (
        (candidate / _MARKER_PROJECT).is_file()
        and (candidate / "tools" / _MARKER_PACKAGE).is_dir()
    )


def project_root() -> Path:
    """解析项目根目录，返回绝对路径。失败时抛 RuntimeError。"""
    # ---------- Layer 1: 环境变量 ----------
    env = os.environ.get("HERMES_AGENT_HOME")
    if env:
        candidate = Path(env).expanduser().resolve()
        if _is_valid_root(candidate):
            return candidate

    # ---------- Layer 2: 包已安装（importable） ----------
    try:
        import tools.energy_audit  # noqa: F401
        # tools/energy_audit/__init__.py → parents[1] 就是项目根
        pkg_file = Path(tools.energy_audit.__file__).resolve()
        candidate = pkg_file.parents[1]
        if _is_valid_root(candidate):
            return candidate
    except ImportError:
        pass

    # ---------- Layer 3: __file__ 向上爬 ----------
    here = Path(__file__).resolve().parent  # .../tools/energy_audit/
    for parent in [here, *here.parents]:
        if _is_valid_root(parent):
            return parent

    # ---------- 全部失败：抛错并打印诊断 ----------
    debug_info = (
        f"$PWD = {os.getcwd()}\n"
        f"$HERMES_AGENT_HOME = {env!r}\n"
        f"__file__ = {__file__}\n"
        f"sys.path[0:3] = {sys.path[:3]}"
    )
    raise RuntimeError(
        "无法定位项目根目录。\n"
        "请按以下任一方式修复：\n"
        "  1. 设置环境变量:  export HERMES_AGENT_HOME=/path/to/project\n"
        "  2. 安装包:        pip install -e .\n"
        "  3. 从项目根目录运行:  cd /path/to/project && python tools/...\n"
        f"\n诊断信息:\n{debug_info}"
    )


# 模块加载即解析一次，下游脚本可直接使用常量
PROJECT_ROOT: Path = project_root()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

__all__ = ["project_root", "PROJECT_ROOT"]