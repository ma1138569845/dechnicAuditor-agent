#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate a complete, reviewable inventory for the energy-audit package.

The inventory intentionally separates authoritative skill sources, deployment
integration code, RAG runtime code, active RAG assets, and historical RAG
archives. Deployed per-profile copies and caches are generated artifacts and
are not enumerated.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_REPO = Path(
    os.environ.get("EA_INVENTORY_DEPLOY_REPO")
    or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent"
)
HERMES_HOME = Path(
    os.environ.get("EA_INVENTORY_HERMES_HOME")
    or os.environ.get("HERMES_HOME")
    or r"E:\ReloAppData\Local\hermes"
)
SKILL_ROOT = REPO_ROOT / "skills" / "energy-audit"
RAG_ASSET_ROOT = HERMES_HOME / "rag"
OUTPUT = REPO_ROOT / "docs" / "energy-audit-package-inventory.md"

SKIP_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
RAG_TRANSIENT_SUFFIXES = {".db-wal", ".db-shm"}


def files_under(root: Path, *, skip_rag_transient: bool = False) -> list[Path]:
    if not root.is_dir():
        return []
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES or path.name in SKIP_NAMES:
            continue
        if skip_rag_transient and path.suffix.lower() in RAG_TRANSIENT_SUFFIXES:
            continue
        result.append(path)
    return sorted(result, key=lambda p: p.relative_to(root).as_posix().casefold())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not-a-git-worktree"


def select_repo_integration() -> list[Path]:
    selected: set[Path] = set()

    for rel in (
        "tools/energy_audit",
        "tests/tools/energy_audit",
    ):
        selected.update(files_under(DEPLOY_REPO / rel))

    for rel in (
        "tools/energy_audit_tool.py",
        "tools/energy_audit_rag_tool.py",
        "tools/energy_audit_imitate_tool.py",
        "scripts/deploy_ea_skills.py",
        "scripts/sync_ea_skills.py",
        "scripts/tests/test_sync_ea_skills.py",
        "skills/productivity/xlsx/domain_guidance/energy_audit.md",
        "apps/desktop/src/app/chat/composer/energy-audit-dialog.tsx",
        "apps/desktop/src/lib/templates/energy-audit.ts",
        "apps/desktop/src/lib/templates/energy-audit.test.ts",
        "website/docs/developer-guide/energy-audit-agent-flowchart.html",
        "website/docs/developer-guide/energy-audit-agent-flowchart.md",
        "website/docs/developer-guide/energy-audit-architecture.html",
    ):
        path = DEPLOY_REPO / rel
        if path.is_file():
            selected.add(path)

    for pattern in (
        "scripts/ea_*.py",
        "tests/skills/test_energy_audit_*.py",
    ):
        selected.update(path for path in DEPLOY_REPO.glob(pattern) if path.is_file())

    return sorted(selected, key=lambda p: p.relative_to(DEPLOY_REPO).as_posix().casefold())


def active_rag_assets() -> list[Path]:
    selected: set[Path] = set()
    for rel in ("data", "report", "standards", "wiki"):
        selected.update(files_under(RAG_ASSET_ROOT / rel, skip_rag_transient=True))
    ingest_log = RAG_ASSET_ROOT / "ingest_log.json"
    if ingest_log.is_file():
        selected.add(ingest_log)
    return sorted(selected, key=lambda p: p.relative_to(RAG_ASSET_ROOT).as_posix().casefold())


def archived_rag_assets() -> list[Path]:
    selected: list[Path] = []
    if not RAG_ASSET_ROOT.is_dir():
        return selected
    for root in sorted(RAG_ASSET_ROOT.glob("_archive_*")):
        if root.is_dir():
            selected.extend(files_under(root, skip_rag_transient=True))
    return sorted(selected, key=lambda p: p.relative_to(RAG_ASSET_ROOT).as_posix().casefold())


def directory_rollup(root: Path, files: list[Path], relative_to_root: bool = True) -> list[tuple[str, int, int]]:
    buckets: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        rel = path.relative_to(root) if relative_to_root else path.relative_to(DEPLOY_REPO)
        parts = rel.parts
        key = parts[0] if len(parts) > 1 else "(根目录)"
        buckets[key].append(path)
    return [
        (key, len(items), sum(path.stat().st_size for path in items))
        for key, items in sorted(buckets.items(), key=lambda item: item[0].casefold())
    ]


def table_rows(root: Path, files: list[Path], *, rag_transient: bool = False) -> list[str]:
    rows = ["| 文件 | 大小（字节） | SHA-256（前16位） |", "|---|---:|---|"]
    for path in files:
        rel = path.relative_to(root).as_posix()
        rows.append(f"| `{rel}` | {path.stat().st_size:,} | `{sha256(path)[:16]}` |")
    return rows


def rollup_rows(items: list[tuple[str, int, int]]) -> list[str]:
    rows = ["| 一级目录 | 文件数 | 合计大小（字节） |", "|---|---:|---:|"]
    for name, count, size in items:
        rows.append(f"| `{name}` | {count:,} | {size:,} |")
    return rows


def main() -> int:
    skill_files = files_under(SKILL_ROOT)
    repo_integration_files = select_repo_integration()
    rag_code_files = files_under(DEPLOY_REPO / "rag")
    rag_active_files = active_rag_assets()
    rag_archived_files = archived_rag_assets()

    sections = {
        "技能包源文件": skill_files,
        "仓库集成与工具链": repo_integration_files,
        "RAG 运行代码": rag_code_files,
        "RAG 当前资产": rag_active_files,
        "RAG 历史归档": rag_archived_files,
    }
    total_files = sum(len(items) for items in sections.values())
    total_bytes = sum(path.stat().st_size for items in sections.values() for path in items)

    lines = [
        "# 能源审计技能包完整文件清单",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（Asia/Shanghai）",
        "> 生成脚本：`scripts/generate_energy_audit_file_inventory.py`",
        f"> 技能源提交：`{git_head(REPO_ROOT)}`",
        f"> 部署仓库提交：`{git_head(DEPLOY_REPO)}`",
        "",
        "## 路径约定",
        "",
        "| 标记 | 当前机器路径 | 用途 |",
        "|---|---|---|",
        f"| `<SKILL_ROOT>` | `{SKILL_ROOT}` | 技能包权威源 |",
        f"| `<DEPLOY_REPO>` | `{DEPLOY_REPO}` | 正式部署代码仓库 |",
        f"| `<HERMES_HOME>` | `{HERMES_HOME}` | Hermes 运行目录 |",
        "",
        "## 清单口径",
        "",
        "- 技能包源文件包含当前技能、共享资产、SOUL 和历史归档。",
        "- 仓库集成包含 `tools/energy_audit/`、能源审计工具入口、测试、发布脚本和外围界面/文档。",
        "- RAG 运行代码包含 `<DEPLOY_REPO>/rag/` 全部 Python、配置说明和测试。",
        "- RAG 当前资产包含 `data/`、`report/`、`standards/`、`wiki/` 和 `ingest_log.json`。",
        "- RAG 历史归档以 `_archive_*` 开头，单列但不计入正式运行口径。",
        "- 排除 `__pycache__`、`.pytest_cache`、`.ruff_cache`、`.mypy_cache`、`.pyc`、`.pyo` 和 RAG `*.db-wal` / `*.db-shm` 临时文件。",
        "- 不重复列出主 Hermes 和六个 profile 中的部署副本；这些副本由 `sync_ea_skills.py` 生成。",
        "",
        "## 总览",
        "",
        "| 分区 | 文件数 | 合计大小（字节） |",
        "|---|---:|---:|",
    ]
    for name, items in sections.items():
        lines.append(
            f"| {name} | {len(items):,} | "
            f"{sum(path.stat().st_size for path in items):,} |"
        )
    lines.extend(
        [
            f"| **合计** | **{total_files:,}** | **{total_bytes:,}** |",
            "",
            "## 一级目录汇总",
            "",
            "### 技能包源文件",
            "",
            *rollup_rows(directory_rollup(SKILL_ROOT, skill_files)),
            "",
            "### 仓库集成与工具链",
            "",
            *rollup_rows(directory_rollup(DEPLOY_REPO, repo_integration_files, relative_to_root=False)),
            "",
            "### RAG 运行代码",
            "",
            *rollup_rows(directory_rollup(DEPLOY_REPO / "rag", rag_code_files)),
            "",
            "### RAG 当前资产",
            "",
            *rollup_rows(directory_rollup(RAG_ASSET_ROOT, rag_active_files)),
            "",
            "### RAG 历史归档",
            "",
            *rollup_rows(directory_rollup(RAG_ASSET_ROOT, rag_archived_files)),
            "",
            "## 完整文件列表",
            "",
            "### 1. 技能包源文件",
            "",
            f"根目录：`<SKILL_ROOT>`（`{SKILL_ROOT}`）",
            "",
            *table_rows(SKILL_ROOT, skill_files),
            "",
            "### 2. 仓库集成与工具链",
            "",
            f"根目录：`<DEPLOY_REPO>`（`{DEPLOY_REPO}`）",
            "",
            *table_rows(DEPLOY_REPO, repo_integration_files),
            "",
            "### 3. RAG 运行代码",
            "",
            f"根目录：`<DEPLOY_REPO>`（`{DEPLOY_REPO}`）",
            "",
            *table_rows(DEPLOY_REPO, rag_code_files),
            "",
            "### 4. RAG 当前资产",
            "",
            f"根目录：`<HERMES_HOME>/rag`（`{RAG_ASSET_ROOT}`）",
            "",
            *table_rows(RAG_ASSET_ROOT, rag_active_files),
            "",
            "### 5. RAG 历史归档",
            "",
            f"根目录：`<HERMES_HOME>/rag`（`{RAG_ASSET_ROOT}`）",
            "",
            *table_rows(RAG_ASSET_ROOT, rag_archived_files),
            "",
            "## 部署时仍需单独处理的外部项",
            "",
            "| 项目 | 是否在 Git 中 | 处理方法 |",
            "|---|---|---|",
            "| PostgreSQL `dc_energy_audit2` | 否 | 连接现有库或恢复数据库备份 |",
            "| Qdrant 向量集合 | 否 | 连接现有服务或迁移快照 |",
            "| `.env` / API Key | 否 | 使用密钥管理系统或加密迁移 |",
            "| Hermes profile 配置 | 否 | 迁移 `config.yaml`、`profile.yaml` 和 `.env` |",
            "| Hermes 会话、日志、kanban 历史 | 否 | 生产环境通常不迁移 |",
            "",
        ]
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}")
    print(f"Files: {total_files:,}; bytes: {total_bytes:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
