#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只补实体/wiki，**不重跑向量**（用于 `--vector-only` 入库后的补跑）。

与直接 `--reindex-only` 的区别：那个会把切片重新 embedding（21 份白跑一遍），
本脚本只对"实体=0"或"wiki=0"的文档触发 start_graph_build / start_wiki_build。

用法:
    python backfill_graph_wiki.py --kb energy_audit_reports [--only 名称子串]
        [--timeout 600] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

# repo 根：env 覆盖 → 常见默认（与 ingest_kb_files.py / sync_report_library.py 同约定）
REPO = os.environ.get("EA_REPO_ROOT") or r"D:\data\pyProject\dc_agent\dechnicAuditor-agent"
sys.path.insert(0, REPO)

HERMES = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "hermes"
KBMETA = HERMES / "rag" / "data" / ".knowledge_meta.db"


def counts(doc_id: str) -> dict:
    conn = sqlite3.connect(f"file:{KBMETA}?mode=ro", uri=True)   # WAL：不可加 immutable
    try:
        q = lambda sql: conn.execute(sql, (doc_id,)).fetchone()[0]  # noqa: E731
        return {
            "entities": q("SELECT COUNT(*) FROM knowledge_entities WHERE doc_id = ?"),
            "wiki": q("SELECT COUNT(*) FROM knowledge_wiki_pages WHERE doc_id = ?"),
        }
    finally:
        conn.close()


def docs(kb_id: str) -> list:
    conn = sqlite3.connect(f"file:{KBMETA}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT id, file_name FROM knowledge_documents WHERE kb_id = ? ORDER BY file_name",
            (kb_id,)).fetchall()
    finally:
        conn.close()


def wait_stable(doc_id: str, field: str, timeout: int, interval: int = 15) -> int:
    """等到该字段"非零且连续两次不变"才算完成。

    ★2026-09-21 修：原来只等 `entities > 0`——而 `build_document_graph` 是
    **逐块 DELETE+INSERT**，中途就会 >0（且数值会上下波动，实测 307→137）。
    抓中间态就往下走，会让 wiki 构建与图谱构建**并发**写同一份文档 → 外键冲突。
    """
    t0, prev = time.time(), -1
    while time.time() - t0 < timeout:
        cur = counts(doc_id)[field]
        if cur > 0 and cur == prev:
            return cur
        prev = cur
        time.sleep(interval)
    return counts(doc_id)[field]


def main() -> int:
    ap = argparse.ArgumentParser(description="补实体/wiki（不重跑向量）")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    todo = [d for d in docs(args.kb) if not args.only or args.only in d[1]]
    print(f"[{args.kb}] 文档 {len(todo)} 份；timeout={args.timeout}s")
    need = []
    for doc_id, name in todo:
        c = counts(doc_id)
        flag = "需补" if (c["entities"] == 0 or c["wiki"] == 0) else "齐全"
        print(f"  {flag}  {name}   实体 {c['entities']} / wiki {c['wiki']}")
        if flag == "需补":
            need.append((doc_id, name, c))
    if args.dry_run or not need:
        print(f"\n[{'dry-run' if args.dry_run else '完成'}] 需补 {len(need)} 份")
        return 0

    from rag.api import knowledge_base as kb

    ok, timeout = [], []
    for doc_id, name, c in need:
        print(f"\n── {name}")
        if c["entities"] == 0:
            kb.start_graph_build(doc_id)
            wait_stable(doc_id, "entities", args.timeout)
        if c["wiki"] == 0:
            kb.start_wiki_build(doc_id)
            wait_stable(doc_id, "wiki", args.timeout)
        c2 = counts(doc_id)
        mark = "✓" if (c2["entities"] > 0 and c2["wiki"] > 0) else "⚠"
        print(f"   {mark} 实体 {c2['entities']} / wiki {c2['wiki']}")
        (ok if mark == "✓" else timeout).append(name)

    print("\n=== 汇总 ===")
    print(f"  齐全 {len(ok)}：{'、'.join(ok) if ok else '—'}")
    print(f"  未齐 {len(timeout)}：{'、'.join(timeout) if timeout else '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
