#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库投递入库 —— knowledger 的维护入口（2026-09-20 建，2026-09-20 移入技能）

> 位置：`energy-audit-core/scripts/`（**发布给全部角色**，随技能同步到
> 主库与 6 个 profile）。职责与验收标准见
> `energy-audit-core/references/knowledge-base-maintenance.md`。

投递区（用户把原文丢这里即可）：
    %LOCALAPPDATA%\\hermes\\rag\\standards\\_inbox\\
        guidelines\\         → energy_audit_technical_guidelines（技术规范/办法/导则）
        quota_standards\\    → energy_quota_standards（定额类）
        reports\\            → energy_audit_reports（一般不手工投；交付件走 WORKFLOW S16a）

  说明类文件**不算料**：`README*` / `待投递*` / `说明*` / `index*` / 下划线开头的名字一律跳过
  （投递区里放着给人工看的清单，别被当成待入文档）。

每份文件的处理（幂等）：
    1 查重：sha256 已在 knowledge_documents.file_hash → 跳过
    2 复制到 kb 根目录 rag/data/<kb>/（保留相对子目录）
    3 reconcile_knowledge_base(kb) 扫盘 → 建 folder/document 记录
    4 start_vectorization_v2(doc_id) → 等完成（切片 → Qdrant <base>）
    5 start_graph_build(doc_id)      → 等实体落库（→ <base>_entities）
    6 start_wiki_build(doc_id)       → 等 wiki 页落库（→ <base>_wiki）
    7 归档原件到 rag/standards/<类别>/（--no-archive 可跳过）
    8 追加台账 rag/ingest_log.json → kb_ingests[]

用法：
    python ingest_kb_files.py --dry-run                 # 只看会入哪些
    python ingest_kb_files.py                           # 入投递区全部
    python ingest_kb_files.py --kb energy_quota_standards \
        --from "<...>\\rag\\standards\\机关事务局" --from "<...>\\rag\\standards\\住建厅" --no-archive

退出码：0 = 全部成功（或无需处理）；1 = 有失败项
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# repo 根：env 覆盖 → 常见默认。装到别的机器时用 EA_REPO_ROOT 指过去。
REPO = os.environ.get("EA_REPO_ROOT") or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent"
sys.path.insert(0, REPO)

HERMES = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "hermes"
RAG = HERMES / "rag"
DATA = RAG / "data"
INBOX = RAG / "standards" / "_inbox"
KBMETA = DATA / ".knowledge_meta.db"
LEDGER = RAG / "ingest_log.json"

GUIDELINES = "energy_audit_technical_guidelines"
QUOTA = "energy_quota_standards"
REPORTS = "energy_audit_reports"

DIR_TO_KB = {"guidelines": GUIDELINES, "quota_standards": QUOTA, "reports": REPORTS}
ARCHIVE_DIR = {GUIDELINES: "技术规范", QUOTA: "定额标准", REPORTS: "能源审计报告"}

LANGS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".pptx", ".html", ".htm"}

# 投递区里的"说明类"文件不是料：README / 待投递清单 / 说明 / 下划线开头的一律跳过。
# 2026-09-20 实测：`guidelines/待投递清单.md` 被当成待入文件（--dry-run 里露出来了）。
SKIP_NAME_PREFIX = ("readme", "待投递", "说明", "index", "_")


def is_source_file(p: Path) -> bool:
    if p.suffix.lower() not in LANGS or p.name.startswith("."):
        return False
    return not p.name.lower().startswith(SKIP_NAME_PREFIX)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def kb_root(kb_id: str) -> Path:
    return DATA / kb_id


def existing_hashes() -> dict:
    """file_hash → (kb_id, file_name, doc_id)"""
    out = {}
    if not KBMETA.is_file():
        return out
    # 用 mode=ro（**不加 immutable**）：入库管道是 WAL 模式，immutable 会忽略 -wal
    # 里刚写入的数据 → 等待循环会空转到超时（2026-09-20 踩过）。
    conn = sqlite3.connect(f"file:{KBMETA}?mode=ro", uri=True)
    try:
        for kb_id, doc_id, name, fh in conn.execute(
                "SELECT kb_id, id, file_name, file_hash FROM knowledge_documents"):
            if fh:
                out.setdefault(fh, (kb_id, name, doc_id))
    finally:
        conn.close()
    return out


def doc_counts(doc_id: str) -> dict:
    """该文档的 切片/实体/关系/wiki 计数（只读）。"""
    conn = sqlite3.connect(f"file:{KBMETA}?mode=ro", uri=True)
    try:
        q = lambda sql: conn.execute(sql, (doc_id,)).fetchone()[0]  # noqa: E731
        return {
            "chunks": q("SELECT COUNT(*) FROM knowledge_chunks WHERE doc_id = ?"),
            "entities": q("SELECT COUNT(*) FROM knowledge_entities WHERE doc_id = ?"),
            "relations": q("SELECT COUNT(*) FROM knowledge_relationships WHERE doc_id = ?"),
            "wiki": q("SELECT COUNT(*) FROM knowledge_wiki_pages WHERE doc_id = ?"),
        }
    finally:
        conn.close()


def find_doc(kb, kb_id: str, file_name: str):
    r = kb.list_knowledge_documents(kb_id, {"keyword": file_name, "page_size": 50})
    for it in (r.get("data") or []):
        if it.get("file_name") == file_name:
            return it
    return None


def wait_until(fn, label: str, timeout: int = 900, interval: int = 5) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fn():
            return True
        time.sleep(interval)
    print(f"    ⚠️ {label} 等待超时（{timeout}s）")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库投递入库")
    ap.add_argument("--kb", choices=[GUIDELINES, QUOTA, REPORTS], help="只入某个库（配 --from 用）")
    ap.add_argument("--from", dest="sources", action="append", default=[],
                    help="源目录（可重复）；缺省扫投递区")
    ap.add_argument("--no-archive", action="store_true", help="不把原件归档到 rag/standards/")
    ap.add_argument("--only", default="", help="只处理文件名含该子串的（便于单份验证）")
    ap.add_argument("--reindex-only", action="store_true",
                    help="只对已在 kb 根目录里的文件重建索引（跳过复制/查重；用于改过解析器后重入）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 1) 收集待入文件 → (源文件, 目标 kb)
    todo = []
    if args.reindex_only:
        if not args.kb:
            print("[错误] --reindex-only 必须同时指定 --kb")
            return 1
        for p in sorted(kb_root(args.kb).rglob("*")):
            if p.is_file() and is_source_file(p):
                todo.append((p, args.kb))
    elif args.sources:
        if not args.kb:
            print("[错误] 用 --from 时必须同时指定 --kb")
            return 1
        for src in args.sources:
            d = Path(src).expanduser()
            if not d.is_dir():
                print(f"[错误] 源目录不存在：{d}")
                return 1
            for p in sorted(d.rglob("*")):
                if p.is_file() and is_source_file(p):
                    todo.append((p, args.kb))
    else:
        if not INBOX.is_dir():
            print(f"[提示] 投递区不存在：{INBOX}（先建目录并丢入原文）")
            return 0
        for sub, kb_id in DIR_TO_KB.items():
            d = INBOX / sub
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file() and is_source_file(p):
                    todo.append((p, kb_id))

    if not todo:
        print(f"[提示] 没有待入文件（投递区 {INBOX}）")
        return 0

    if args.only:
        todo = [(p, kb_id) for p, kb_id in todo if args.only in p.name]
        if not todo:
            print(f"[提示] 没有文件名含 '{args.only}' 的待入文件")
            return 0

    print(f"[计划] 待入 {len(todo)} 份：")
    for p, kb_id in todo:
        print(f"   {kb_id:<38} {p.name}")
    if args.dry_run:
        print("\n[dry-run] 未做任何改动")
        return 0

    from rag.api import knowledge_base as kb  # noqa: E402  重量级导入放最后

    seen = existing_hashes()
    done, skipped, failed = [], [], []
    for src, kb_id in todo:
        print(f"\n── {src.name}  →  {kb_id}")
        h = sha256(src)
        if h in seen and not args.reindex_only:
            print(f"   ⏭  已存在（sha256 命中 {seen[h][1]}），跳过")
            skipped.append(src.name)
            continue

        # 2) 复制到 kb 根（--reindex-only 时文件已在根目录，跳过）
        if args.reindex_only:
            dst = src
            print(f"   →  原地重建索引（文件已在库根）：{dst}")
        else:
            dst = kb_root(kb_id) / src.name
            if dst.exists() and sha256(dst) != h:
                dst = kb_root(kb_id) / f"{dst.stem}__{h[:8]}{dst.suffix}"
            kb_root(kb_id).mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"   →  已复制到 {dst}")

        # 3) 扫盘建记录
        kb.reconcile_knowledge_base(kb_id)
        doc = find_doc(kb, kb_id, dst.name)
        if not doc:
            print("   ✗ 扫盘后仍未找到文档记录")
            failed.append(src.name)
            continue
        doc_id = doc["id"]
        print(f"   →  doc_id={doc_id}")

        # 4) 向量化
        job = kb.start_vectorization_v2(doc_id)
        jid = job.get("id") or job.get("job_id")
        ok_vec = wait_until(
            lambda: (kb.get_vectorization_job(jid) or {}).get("status") in ("completed", "failed"),
            "向量化")
        j = kb.get_vectorization_job(jid) or {}
        if not ok_vec or j.get("status") != "completed":
            print(f"   ✗ 向量化失败：{j.get('error')}")
            failed.append(src.name)
            continue
        print(f"   ✓ 向量化完成（{j.get('chunks_done')}/{j.get('chunks_total')} 切片）")

        # 5) 实体 + 关系
        kb.start_graph_build(doc_id)
        wait_until(lambda: doc_counts(doc_id)["entities"] > 0, "实体抽取", timeout=900)
        # 6) wiki 页
        kb.start_wiki_build(doc_id)
        wait_until(lambda: doc_counts(doc_id)["wiki"] > 0, "wiki 生成", timeout=600)
        c = doc_counts(doc_id)
        print(f"   ✓ 实体 {c['entities']} / 关系 {c['relations']} / wiki {c['wiki']}")

        # 7) 归档原件
        if not args.no_archive and not args.reindex_only:
            arch = RAG / "standards" / ARCHIVE_DIR.get(kb_id, kb_id)
            arch.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, arch / src.name)
            print(f"   →  原件已归档 {arch}")

        # 8) 台账
        rec = {"file": src.name, "sha256": h, "kb_id": kb_id, "doc_id": doc_id,
               "chunks": c["chunks"], "entities": c["entities"], "wiki": c["wiki"],
               "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        ledger = {}
        if LEDGER.is_file():
            try:
                ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                ledger = {}
        ledger.setdefault("kb_ingests", []).append(rec)
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        done.append(src.name)

    print("\n=== 汇总 ===")
    print(f"  成功 {len(done)}：{'、'.join(done) if done else '—'}")
    if skipped:
        print(f"  跳过 {len(skipped)}：{'、'.join(skipped)}")
    if failed:
        print(f"  失败 {len(failed)}：{'、'.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
