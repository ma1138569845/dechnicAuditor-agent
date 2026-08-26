#!/usr/bin/env python3
"""
能源审计知识库检索脚本。

三种模式:
  1. template <类别> — 模板直读（零嵌入调用，按元数据过滤 summary + chapter）
  2. search <问题>    — 语义检索 → 匹配报告 → 加载完整结构
  3. load <文件名>    — 直接加载指定报告
"""
import os, re, sys
from collections import Counter

from rag.config import qdrant_client_kwargs, reports_collection

COLLECTION = reports_collection()


def get_client():
    from qdrant_client import QdrantClient
    return QdrantClient(**qdrant_client_kwargs(timeout=30))


def embed_query(text: str) -> list[float]:
    from rag.embedding import embed_query as _embed
    return _embed(text)


# ═══════════════════════════════════════
# 模式1: 模板直读（零嵌入调用）
# ═══════════════════════════════════════

def get_template(cat: str = None, spec: str = None) -> str:
    """
    直接按机构类型读取模板报告结构。
    不走向量检索（零嵌入调用），直接 scroll + 元数据过滤。
    """
    client = get_client()

    summaries = []
    chapters_by_report = {}
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION, limit=500, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in points:
            p_cat = p.payload.get("institution_category", "")
            p_spec = p.payload.get("specific_type", "")
            tp = p.payload.get("type", "")
            fname = p.payload.get("filename", "")

            if cat and p_cat != cat: continue
            if spec and p_spec != spec: continue

            if tp == "summary":
                summaries.append(p.payload)
            elif tp == "chapter":
                if fname not in chapters_by_report:
                    chapters_by_report[fname] = []
                chapters_by_report[fname].append(p.payload)

        if next_offset is None: break
        offset = next_offset

    if not summaries:
        return f"未找到类型 '{cat or '任意'}/{spec or '任意'}' 的报告。"

    parts = [
        f"# 模板检索：{cat or '全部'} / {spec or '全部'}",
        f"匹配 {len(summaries)} 份报告\n"
    ]

    for s in summaries:
        fname = s.get("filename", "")
        unit = s.get("unit_name", fname)
        parts.append(f"## {unit} ({s.get('institution_category','')}/{s.get('specific_type','')})")
        parts.append(f"文件: {fname}\n")
        parts.append(s.get("text", "")[:1500])

        if fname in chapters_by_report:
            parts.append("\n### 章节结构")
            for ch in sorted(chapters_by_report[fname], key=lambda c: c.get("chapter", "")):
                parts.append(f"- **{ch.get('chapter','')}** — {ch.get('text','')[:100]}")
        parts.append("\n---\n")

    return "\n".join(parts)


def list_categories():
    """列出所有可用模板类别（不走嵌入）"""
    client = get_client()
    from collections import Counter
    cats = Counter()
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION, limit=500, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in points:
            if p.payload.get("type") == "summary":
                cat = p.payload.get("institution_category", "未知")
                st = p.payload.get("specific_type", "未知")
                cats[(cat, st)] += 1
        if next_offset is None: break
        offset = next_offset

    print("知识库模板类别（可直接用 template 命令读取）：")
    for (cat, st), cnt in cats.most_common():
        print(f"  {cat}/{st} ({cnt}份)")


# ═══════════════════════════════════════
# 模式2: 语义检索 + 结构加载
# ═══════════════════════════════════════

def search_similar_reports(query: str, top_k: int = 5):
    client = get_client()
    vector = embed_query(query)
    results = client.query_points(
        collection_name=COLLECTION, query=vector,
        limit=top_k * 3, with_payload=True,
    ).points

    seen = {}
    for r in results:
        fname = r.payload.get("filename", "unknown")
        if fname not in seen or r.score > seen[fname][0]:
            seen[fname] = (r.score, r.payload)
    ranked = sorted(seen.items(), key=lambda x: x[1][0], reverse=True)
    return ranked[:top_k]


def load_report(filename: str) -> dict:
    client = get_client()
    chunks = {"summary": [], "chapter": [], "paragraph": []}
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION, limit=200, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in points:
            if p.payload.get("filename") != filename: continue
            tp = p.payload.get("type", "paragraph")
            if tp in chunks: chunks[tp].append(p.payload)
        if next_offset is None: break
        offset = next_offset
    return chunks


def compare_reports(query: str, top_k: int = 3) -> str:
    print(f"🔍 语义检索: {query[:60]}...\n")
    similar = search_similar_reports(query, top_k=top_k)
    if not similar:
        return "未找到相似报告。"

    parts = ["# 语义检索结果\n"]
    for rank, (fname, (score, best)) in enumerate(similar, 1):
        cat = best.get("institution_category", "未知")
        spec = best.get("specific_type", "未知")
        unit = best.get("unit_name", fname)
        parts.append(
            f"## {rank}. {unit}\n"
            f"**类型**: {cat}/{spec} | **相似度**: {score:.3f}\n"
        )
        report = load_report(fname)
        for s in report["summary"]:
            parts.append(f"\n### 📋 摘要\n{s['text']}\n"); break
        if report["chapter"]:
            parts.append("### 📑 章节结构\n")
            for ch in sorted(report["chapter"], key=lambda c: c.get("chapter", "")):
                parts.append(f"- **{ch.get('chapter','')}** — {ch.get('text','')[:120]}...\n")
        if report["paragraph"]:
            parts.append(f"\n### 🔗 相关段落 ({len(report['paragraph'])}段)\n")
            for p in report["paragraph"][:3]:
                parts.append(f"- [{p.get('chapter','')}] {p.get('text','')[:150]}...\n")
        parts.append("\n---\n")
    return "\n".join(parts)


# ═══════════════════════════════════════
# 统计
# ═══════════════════════════════════════

def kb_stats():
    client = get_client()
    info = client.get_collection(COLLECTION)
    files = Counter(); cats = Counter(); types = Counter()
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION, limit=500, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in points:
            files[p.payload.get("filename", "unknown")] += 1
            cats[p.payload.get("institution_category", "unknown")] += 1
            types[p.payload.get("type", "unknown")] += 1
        if next_offset is None: break
        offset = next_offset

    print(f"=== 知识库统计 ===")
    print(f"总 chunks: {info.points_count} | 独立报告: {len(files)}")
    print(f"\n按机构类型:")
    for cat, cnt in cats.most_common():
        print(f"  {cat}: {cnt} chunks")
    print(f"\n按层级:")
    for tp, cnt in types.most_common():
        print(f"  {tp}: {cnt} chunks")


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python energy_audit_search.py stats              # 知识库统计")
        print("  python energy_audit_search.py categories         # 列出模板类别")
        print("  python energy_audit_search.py template <类别>    # 模板直读（零嵌入）")
        print("  python energy_audit_search.py search <问题>      # 语义检索")
        print("  python energy_audit_search.py load <文件名>      # 加载完整报告")
        return

    cmd = sys.argv[1]

    if cmd == "stats":
        kb_stats()

    elif cmd == "categories":
        list_categories()

    elif cmd == "template":
        if len(sys.argv) < 3:
            print("请提供类别，如: python energy_audit_search.py template 医疗")
            print("可用类别用 categories 命令查看")
            return
        cat = sys.argv[2]
        spec = sys.argv[3] if len(sys.argv) > 3 else None
        print(get_template(cat=cat, spec=spec))

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("请提供查询问题")
            return
        print(compare_reports(" ".join(sys.argv[2:])))

    elif cmd == "load":
        if len(sys.argv) < 3:
            print("请提供文件名")
            return
        report = load_report(sys.argv[2])
        print(f"### {sys.argv[2]}\n")
        for s in report['summary']:
            print(s['text'][:500])
        print(f"\n章节 ({len(report['chapter'])}):")
        for ch in report['chapter']:
            print(f"  {ch.get('chapter','')}: {ch.get('text','')[:100]}...")

    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
