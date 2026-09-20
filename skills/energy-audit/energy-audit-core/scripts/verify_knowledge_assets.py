#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_knowledge_assets.py — 知识层资产治理检查（2026-09-20 建，设计 P1）

> 位置：`energy-audit-core/scripts/`（**发布给全部角色**）。
> 职责与验收标准见 `energy-audit-core/references/knowledge-base-maintenance.md`。
> knowledger 巡检：退出码 0（P0=0）才算知识层健康。

检查七项（对应《知识参考体系重构设计》§4.5）：
  1 目录规约：rag/standards/ 存在；rag/report/ 下**不得**混放标准 PDF
  2 元数据 schema：Qdrant `energy_audit_reports` 每条须有 type 与 institution_category
  3 重复 / 副本：文件名含"副本/copy/(1)" → 报错；源文件 sha256 重复 → 告警
  4 点数对账：rag/ingest_log.json 各文件切片数之和 == 集合实际点数
  5 死资产：存在但**无人读取**的配置文件（如 rag/qdrant_config.yaml）→ 报错
  6 标准库切片体检：guidelines/quota 两库每份文档切片数须 > 3（防"整篇只切出 1 条
    垃圾摘要"——2026-09-20 发现的报告解析器误用 bug 就是这种症状）
  7 归档完备性：rag/data/<kb>/ 里的每份文件都必须在 rag/standards/ 有同名/同哈希副本
    （2026-09-20 教训：delete_knowledge_document 会连磁盘原件一起 unlink）

用法:
  python verify_knowledge_assets.py                # 只检查（需要 Qdrant 才查第 2/4 项）
  python verify_knowledge_assets.py --write-log    # 从 Qdrant 反查生成/刷新 ingest_log.json

退出码：0 = 无 P0 级问题（告警不计）；1 = 存在问题
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# repo 根：env 覆盖 → 常见默认。装到别的机器时用 EA_REPO_ROOT 指过去。
REPO = os.environ.get("EA_REPO_ROOT") or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent"
sys.path.insert(0, REPO)

HERMES = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "hermes"
RAG = HERMES / "rag"
STD_DIR = RAG / "standards"
REP_DIR = RAG / "report"
LOG_PATH = RAG / "ingest_log.json"
KBMETA = RAG / "data" / ".knowledge_meta.db"
DEAD_CONFIGS = [RAG / "qdrant_config.yaml"]

STD_HINTS = ("定额标准", "能耗限额", "能耗定额", "设计标准", "用水定额")
BAD_NAME_HINTS = ("副本", "copy", "(1)", " - 副本")

STANDARD_KBS = ("energy_audit_technical_guidelines", "energy_quota_standards")
MIN_CHUNKS_PER_DOC = 4      # 低于此值基本可判定"解析器走错路"

problems: list[str] = []
warnings: list[str] = []


def p0(msg: str) -> None:
    problems.append(msg)
    print(f"  ✗ {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  ⚠️ {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_qdrant():
    try:
        from rag.config import reports_collection, qdrant_client_kwargs
        from qdrant_client import QdrantClient
    except Exception as exc:  # noqa: BLE001
        warn(f"无法导入 Qdrant 客户端：{exc}")
        return None, None
    try:
        client = QdrantClient(**qdrant_client_kwargs())
        client.get_collections()
    except Exception as exc:  # noqa: BLE001
        warn(f"Qdrant 不可达（跳过第 2/4 项）：{exc}")
        return None, None
    return client, reports_collection()


def scroll_all(client, collection: str) -> list:
    out, offset = [], None
    while True:
        pts, offset = client.scroll(collection, limit=256, offset=offset,
                                    with_payload=True, with_vectors=False)
        out.extend(pts)
        if offset is None:
            return out


def check_dir_convention() -> None:
    print("\n=== 1 目录规约 ===")
    if STD_DIR.is_dir():
        n = len(list(STD_DIR.rglob("*.pdf")))
        ok(f"rag/standards/ 存在（{n} 份标准 PDF）")
    else:
        p0(f"缺少 rag/standards/：{STD_DIR}")
    stray = [p for p in REP_DIR.rglob("*.pdf") if any(k in str(p) for k in STD_HINTS)]
    if stray:
        p0(f"rag/report/ 下混放标准类 PDF {len(stray)} 份，首个：{stray[0].name}")
    else:
        ok("rag/report/ 下无标准类 PDF")


def check_metadata(client, collection: str) -> None:
    print("\n=== 2 元数据 schema ===")
    if client is None:
        warn("Qdrant 不可达，跳过")
        return
    pts = scroll_all(client, collection)
    total = len(pts)
    no_type = [p for p in pts if not (p.payload or {}).get("type")]
    no_cat = [p for p in pts if not (p.payload or {}).get("institution_category")]
    if no_type:
        p0(f"{len(no_type)}/{total} 条缺 `type`（应为 summary/chapter/paragraph，"
           f"两种导入器 schema 不一致）")
    else:
        ok(f"{total} 条均有 `type`")
    if no_cat:
        p0(f"{len(no_cat)}/{total} 条缺 `institution_category`")
    else:
        ok(f"{total} 条均有 `institution_category`")


def check_duplicates() -> None:
    print("\n=== 3 重复 / 副本 ===")
    # 排除占位/隐藏文件（.gitkeep 等），否则内容相同的空文件会互相误报
    files = [p for p in REP_DIR.rglob("*")
             if p.is_file() and not p.name.startswith(".")]
    bad = [p for p in files if any(k in p.stem for k in BAD_NAME_HINTS)]
    for p in bad:
        p0(f"文件名疑似副本：{p.relative_to(REP_DIR)}")
    if not bad:
        ok("无副本命名")
    seen: dict[str, Path] = {}
    dups = 0
    for p in files:
        try:
            h = sha256(p)
        except OSError:
            continue
        if h in seen:
            dups += 1
            warn(f"内容重复：{p.name} == {seen[h].name}")
        else:
            seen[h] = p
    if not dups:
        ok("无内容重复文件")


def check_point_reconcile(client, collection: str) -> None:
    print("\n=== 4 点数对账 ===")
    if not LOG_PATH.is_file():
        warn(f"缺台账 {LOG_PATH}（用 --write-log 生成）")
        return
    log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    entries = log.get("files") or []
    logged = sum(int(e.get("points") or 0) for e in entries)
    if client is None:
        warn(f"Qdrant 不可达；台账记录 {len(entries)} 文件 / {logged} 切片（无法核对）")
        return
    n = len(scroll_all(client, collection))
    if logged == n:
        ok(f"台账 {len(entries)} 文件 / {logged} 切片 == 集合 {n} 点")
    else:
        warn(f"台账 {logged} 切片 ≠ 集合 {n} 点（差 {n - logged}；重跑 --write-log 刷新）")


def check_dead_assets() -> None:
    print("\n=== 5 死资产 ===")
    alive = False
    for p in DEAD_CONFIGS:
        if not p.is_file():
            continue
        # 判定标准：配置解析入口是否读取该文件（rag/config.py 明写 not read）
        cfg_src = (Path(REPO) / "rag" / "config.py").read_text(encoding="utf-8", errors="replace")
        if p.name in cfg_src and "not read" in cfg_src:
            p0(f"死配置：{p}（rag/config.py 声明未读取）")
            alive = True
    if not alive:
        ok("无已知死配置")


def check_standard_kb_chunks() -> None:
    """6 标准库切片体检：每份文档切片数须 > MIN_CHUNKS_PER_DOC。"""
    print("\n=== 6 标准库切片体检 ===")
    if not KBMETA.is_file():
        p0(f"缺元数据库：{KBMETA}")
        return
    import sqlite3
    conn = sqlite3.connect(f"file:{KBMETA}?mode=ro", uri=True)   # WAL：不可用 immutable
    conn.row_factory = sqlite3.Row
    try:
        for kb_id in STANDARD_KBS:
            rows = conn.execute(
                "SELECT d.file_name, d.chunk_count,"
                " (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.doc_id = d.id) n,"
                " (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.doc_id = d.id"
                "     AND c.chunk_type = 'summary') nsum"
                " FROM knowledge_documents d WHERE d.kb_id = ? ORDER BY d.file_name",
                (kb_id,),
            ).fetchall()
            bad = [r for r in rows if r["n"] < MIN_CHUNKS_PER_DOC]
            if not rows:
                warn(f"{kb_id} 为空库（0 文档）")
            elif bad:
                for r in bad:
                    p0(f"{kb_id} / {r['file_name']}：仅 {r['n']} 条切片"
                       f"（summary {r['nsum']}）——疑似解析器走错或文件无文本层")
            else:
                ok(f"{kb_id}：{len(rows)} 份文档，最少 {min(r['n'] for r in rows)} 条切片")
    finally:
        conn.close()


def check_archive_completeness() -> None:
    """7 归档完备性：kb 根目录的每份文件都必须在 rag/standards/ 有同哈希副本。"""
    print("\n=== 7 归档完备性 ===")
    if not STD_DIR.is_dir():
        p0(f"缺少归档目录：{STD_DIR}")
        return
    # 归档区 sha256 → 路径
    arch: dict[str, Path] = {}
    for p in STD_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".pdf", ".docx", ".doc", ".txt", ".md"):
            try:
                arch.setdefault(sha256(p), p)
            except OSError:
                continue
    missing = []
    checked = 0
    for kb_id in ("energy_audit_technical_guidelines", "energy_quota_standards"):
        root = RAG / "data" / kb_id
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.name.startswith("."):
                continue
            checked += 1
            try:
                if sha256(p) not in arch:
                    missing.append(p)
            except OSError:
                continue
    if missing:
        for p in missing:
            p0(f"库内文件无归档副本：{p}")
    else:
        ok(f"{checked} 份库内文件均有归档副本（归档区共 {len(arch)} 份去重文件）")


def write_log(client, collection: str) -> None:
    if client is None:
        print("[错误] Qdrant 不可达，无法生成台账")
        return
    pts = scroll_all(client, collection)
    agg: dict[str, dict] = {}
    for p in pts:
        pl = p.payload or {}
        name = str(pl.get("filename") or pl.get("file_name") or "?")
        e = agg.setdefault(name, {"file": name, "collection": collection, "points": 0,
                                  "types": [], "institution_category": pl.get("institution_category") or ""})
        e["points"] += 1
        t = pl.get("type")
        if t and t not in e["types"]:
            e["types"].append(t)
    files = sorted(agg.values(), key=lambda x: x["file"])
    for e in files:
        local = next((p for p in REP_DIR.rglob(e["file"]) if p.is_file()), None)
        e["sha256"] = sha256(local) if local else ""
        e["local_path"] = str(local) if local else ""
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "collection": collection,
        "total_files": len(files),
        "total_points": sum(e["points"] for e in files),
        "files": files,
    }
    LOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[完成] 台账已写入 {LOG_PATH}")
    print(f"  {len(files)} 文件 / {sum(e['points'] for e in files)} 切片")
    miss = [e["file"] for e in files if not e["local_path"]]
    if miss:
        print(f"  ⚠️ {len(miss)} 份在 rag/report/ 找不到本地原件（示例：{miss[:3]}）")


def main() -> int:
    ap = argparse.ArgumentParser(description="知识层资产治理检查")
    ap.add_argument("--write-log", action="store_true", help="从 Qdrant 反查生成 ingest_log.json")
    args = ap.parse_args()

    client, collection = load_qdrant()
    if args.write_log:
        write_log(client, collection or "energy_audit_reports")

    print("=" * 62)
    print(f"知识层资产治理检查   rag={RAG}")
    print("=" * 62)
    check_dir_convention()
    check_metadata(client, collection or "energy_audit_reports")
    check_duplicates()
    check_point_reconcile(client, collection or "energy_audit_reports")
    check_dead_assets()
    check_standard_kb_chunks()
    check_archive_completeness()

    print("\n=== 结论 ===")
    print(f"  P0 问题 {len(problems)} 项；告警 {len(warnings)} 项")
    for p in problems:
        print(f"   · {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
