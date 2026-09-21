#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_report_library.py — 交付件入库 + 成稿库↔向量库一致性（S16a 的唯一入口）

## 治什么问题

WORKFLOW 的 **S16a「交付件入库」**此前只有文档、没有接线：`ea-authoring/SKILL.md`
没写、kanban 任务图没有这一步、也没有门禁检查。结果本地成稿目录（17 份）与向量库
（4 份）**交集为空**——两条"参考"路径装的不是一批料（2026-09-20 实测）。

本脚本把 S16a 变成**一条命令**：

```bash
# 交付件定稿后（author 的收尾动作）
python <skills>/energy-audit-core/scripts/sync_report_library.py \
    --add "<项目>/output/交付件/<单位>能源审计报告.docx"

# 自检：两张清单都应为 0
python <skills>/energy-audit-core/scripts/sync_report_library.py --check

# 全量同步：把本地成稿目录里尚未入库的全部入向量库
python <skills>/energy-audit-core/scripts/sync_report_library.py
```

## 落位规则（沿用目录里现成命名，不新造类别）

    hermes/rag/report/能源审计报告/<审计类型>/<类别目录>/<文件名>

审计类型取 `公共机构 / 公共建筑 / 工业企业`；类别目录映射：
`医疗→医院`、`教育→学校`、`党政机关→党政机关`、`体育→体育场馆`，其余原样。
**工业企业 / 公共建筑不建类别层**（与现成目录一致）。

## 两张清单的含义（`--check`）

| 清单 | 级别 | 含义 |
|---|---|---|
| 目录有、向量库没有 | P1 | 待入库（跑本脚本即可） |
| 向量库有、目录没有 | **P0** | 孤儿：一旦误删就没有归档副本（丢 4452 就是这么丢的） |

退出码：0 = 两张清单都空；1 = 有清单非空或入库失败。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INGEST = HERE / "ingest_kb_files.py"

# repo 根：env 覆盖 → 常见默认（与 ingest_kb_files.py 同一约定）。
# 本脚本要 import tools.energy_audit.* 做分类与落位。
REPO = os.environ.get("EA_REPO_ROOT") or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent"
sys.path.insert(0, REPO)

KB_ID = "energy_audit_reports"
CATALOG_ROOT = "能源审计报告"
EXTS = {".docx", ".doc", ".pdf", ".md", ".txt"}
SKIP_NAMES = {"readme.md", "说明.md", "index.md"}

CATEGORY_DIR = {
    "医疗": "医院",
    "教育": "学校",
    "党政机关": "党政机关",
    "体育": "体育场馆",
    "场馆机构": "场馆",
}


def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "hermes" if local else Path.home() / ".hermes"


def rag_root() -> Path:
    return hermes_home() / "rag"


def catalog_files() -> list:
    root = rag_root() / "report"
    out = []
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix.lower() not in EXTS or p.name.lower() in SKIP_NAMES:
            continue
        out.append(p)
    return sorted(out)


def kb_files() -> list:
    meta = rag_root() / "data" / ".knowledge_meta.db"
    if not meta.is_file():
        return []
    conn = sqlite3.connect(f"file:{meta}?mode=ro", uri=True)   # WAL：不可加 immutable
    try:
        rows = conn.execute(
            "SELECT file_name FROM knowledge_documents WHERE kb_id = ? ORDER BY file_name",
            (KB_ID,)).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def catalog_vs_kb() -> dict:
    """两张清单。供本脚本 --check 与 verify_knowledge_assets.py 第 8 项共用。"""
    cat = catalog_files()
    cat_names = {p.name for p in cat}
    kb_names = set(kb_files())
    return {
        "catalog_count": len(cat),
        "kb_count": len(kb_names),
        "only_catalog": sorted(cat_names - kb_names),   # 待入库（P1）
        "only_kb": sorted(kb_names - cat_names),        # 孤儿（P0）
    }


def classify_for_placement(name: str, audit_type: str = "", category: str = ""):
    """返回 (审计类型, 类别目录)。调用方可显式覆盖。"""
    from tools.energy_audit.institution_classifier import classify_institution
    from tools.energy_audit.reference_library import infer_audit_type

    cat, _spec = classify_institution(name)
    if not category and cat in ("医疗", "教育", "党政机关", "体育", "场馆机构"):
        category = CATEGORY_DIR.get(cat, cat)
    if not category:
        category = cat or "其他"
    if not audit_type:
        audit_type = infer_audit_type(Path(name), name)
    return audit_type, category


def place_target(name: str, audit_type: str, category: str) -> Path:
    base = rag_root() / "report" / CATALOG_ROOT / audit_type
    if audit_type in ("工业企业", "公共建筑"):
        return base / name          # 这两类不建类别层（与现成目录一致）
    return base / category / name


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_ingest(from_dir: Path, only: str, *, vector_only: bool, dry: bool) -> int:
    cmd = [sys.executable, str(INGEST), "--kb", KB_ID, "--from", str(from_dir),
           "--no-archive", "--only", only]
    if vector_only:
        cmd.append("--vector-only")
    if dry:
        cmd.append("--dry-run")
    print(f"[入库] {' '.join(cmd[1:])}")
    return subprocess.run(cmd).returncode


def cmd_check(_args) -> int:
    r = catalog_vs_kb()
    print(f"本地成稿目录：{r['catalog_count']} 份")
    print(f"向量库 {KB_ID}：{r['kb_count']} 份")
    print("=" * 78)
    print(f"[P1] 目录有、向量库没有（待入库）{len(r['only_catalog'])} 份：")
    for n in r["only_catalog"]:
        print(f"    · {n}")
    print(f"[P0] 向量库有、目录没有（孤儿）{len(r['only_kb'])} 份：")
    for n in r["only_kb"]:
        print(f"    · {n}")
    print("=" * 78)
    if r["only_kb"] or r["only_catalog"]:
        print(f"✗ 两张清单非空（孤儿 {len(r['only_kb'])} / 待入库 {len(r['only_catalog'])}）")
        return 1
    print("✓ 目录与向量库一致")
    return 0


def cmd_add(args) -> int:
    ok = True
    for raw in args.add:
        src = Path(raw).expanduser()
        if not src.is_file():
            print(f"✗ 交付件不存在：{src}")
            ok = False
            continue
        audit_type, category = classify_for_placement(src.name, args.audit_type,
                                                      args.category)
        dst = place_target(src.name, audit_type, category)
        print(f"· {src.name}")
        print(f"    判定：审计类型={audit_type}　类别目录={category}")
        print(f"    落位：{dst}")
        if dst.is_file():
            same = _sha(dst) == _sha(src)
            print(f"    目标已存在，内容{'相同' if same else '不同'}；"
                  f"{'跳过复制' if same else '保留原文件（请人工确认）'}")
            if not same:
                ok = False
                continue
        elif args.dry_run:
            print("    [dry-run] 不复制")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print("    已复制（原件保留）")
        rc = run_ingest(dst.parent, dst.name,
                        vector_only=not args.full, dry=args.dry_run)
        ok = ok and rc == 0
    return 0 if ok else 1


def cmd_sync(args) -> int:
    root = rag_root() / "report"
    if not root.is_dir():
        print(f"[错误] 成稿目录不存在：{root}")
        return 1
    return run_ingest(root, args.only, vector_only=not args.full, dry=args.dry_run)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="交付件入库 / 成稿库一致性（S16a 入口）")
    ap.add_argument("--check", action="store_true", help="只比对两张清单，不落盘")
    ap.add_argument("--add", action="append", default=[], metavar="交付件路径",
                    help="把交付件落入库目录并入向量库（可重复）")
    ap.add_argument("--only", default="", help="全量同步时只处理文件名含该子串的")
    ap.add_argument("--audit-type", default="", help="覆盖审计类型（公共机构/公共建筑/工业企业）")
    ap.add_argument("--category", default="", help="覆盖类别目录（如 医院/学校/党政机关）")
    ap.add_argument("--full", action="store_true",
                    help="入库时同时跑实体抽取与 wiki（默认只做切片+向量）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.check:
        return cmd_check(args)
    if args.add:
        return cmd_add(args)
    return cmd_sync(args)


if __name__ == "__main__":
    sys.exit(main())
