"""
能源审计报告 RAG 检索工具

检索流程:
  1. Qdrant 向量检索（energy_audit_reports collection）
  2. 本地 wiki 兜底（当 Qdrant 不可用时）
  3. 知识图谱因果诊断兜底（当 wiki 也无结果时）

用法:
  from rag.rag_search import search_reports
  results = search_reports("医院 单位建筑面积非供暖能耗", tags={'institution_category': '医疗'})
"""

import os, json
from typing import Dict, List, Optional
from pathlib import Path

from rag.config import qdrant_client_kwargs, reports_collection

COLLECTION = reports_collection()

# ============================================================
# Layer 0: 标签直查（无需 embedding，适合精确匹配）
# ============================================================

def search_by_tags(tags: Dict, limit: int = 10) -> List[dict]:
    """
    按标签精确筛选（不需要 embedding / API key）
    适用于: 查找"所有医院类报告的第2章"
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = QdrantClient(**qdrant_client_kwargs())

    conditions = []
    for key, value in tags.items():
        conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    qdrant_filter = Filter(must=conditions) if conditions else None

    points, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=qdrant_filter,
        limit=limit,
        with_payload=True,
    )

    return [
        {
            'filename': p.payload.get('filename', ''),
            'chapter': p.payload.get('chapter', ''),
            'text': p.payload.get('text', '')[:2000],
            'tags': {
                'audit_type': p.payload.get('audit_type', ''),
                'institution_category': p.payload.get('institution_category', ''),
                'specific_type': p.payload.get('specific_type', ''),
            },
        }
        for p in points
    ]


# Layer 1: Qdrant 向量检索
# ============================================================

def _embed_query(text: str) -> list:
    """Generate a vector using DashScope text-embedding-v3."""
    from rag.embedding import embed_query
    return embed_query(text)


def search_qdrant(query: str, tags: Optional[Dict] = None, top_k: int = 5) -> List[dict]:
    """
    从 Qdrant 向量库检索相关报告片段

    tags: 标签过滤 {"institution_category": "医疗", "specific_type": "医院"}
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = QdrantClient(**qdrant_client_kwargs())

    # 构建过滤条件
    qdrant_filter = None
    if tags:
        conditions = []
        for key, value in tags.items():
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        if conditions:
            qdrant_filter = Filter(must=conditions)

    vector = _embed_query(query)

    r = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            'score': hit.score,
            'filename': hit.payload.get('filename', ''),
            'chapter': hit.payload.get('chapter', ''),
            'text': hit.payload.get('text', '')[:2000],
            'tags': {
                'audit_type': hit.payload.get('audit_type', ''),
                'institution_category': hit.payload.get('institution_category', ''),
                'specific_type': hit.payload.get('specific_type', ''),
            }
        }
        for hit in r.points
    ]


# ============================================================
# Layer 2: 本地 wiki 兜底
# ============================================================

_WIKI_PATHS = [
    Path(__file__).resolve().parent / "references",                                    # tools/energy_audit/references/
    Path(os.path.expanduser("~/.hermes/skills/energy-audit/energy-audit/references")), # 技能包
]

# User-private Obsidian/wiki vault (optional Layer-2 fallback).
# Default to a cross-platform home-directory "wiki" folder; override with HERMES_OBSIDIAN_WIKI.
_OBSIDIAN_WIKI = Path(os.getenv("HERMES_OBSIDIAN_WIKI", str(Path.home() / "wiki")))

# Auto-generated llm-wiki pages exported by the knowledge-base pipeline.
# Default vault matches rag.api.knowledge_base._DEFAULT_WIKI_VAULT.
_LLM_WIKI_VAULT = Path(os.getenv("HERMES_WIKI_VAULT", str(Path.home() / ".hermes" / "rag" / "wiki")))
_LLM_WIKI_GENERATED = _LLM_WIKI_VAULT / "generated"

# 排除的 wiki 目录/文件（杂项）
_WIKI_EXCLUDE_DIRS = {"_meta", "raw", "未命名.base", ".obsidian"}

def _score_by_keyword_hits(text: str, keywords: list[str]) -> float:
    """Simple keyword overlap score: ratio of query keywords present in text."""
    if not keywords:
        return 0.0
    return sum(1 for kw in keywords if kw in text) / len(keywords)


def _extract_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML-like frontmatter keys into a flat string dict."""
    fm: dict[str, str] = {}
    if not text.startswith("---"):
        return fm
    parts = text.split("---", 2)
    if len(parts) < 3:
        return fm
    for line in parts[1].split("\n"):
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def _matches_wiki_tags(text: str, tags: Dict) -> bool:
    """Return True if the document matches all provided tags.

    Local wiki files do not carry structured tag metadata like Qdrant points.
    When YAML frontmatter contains explicit tag keys (audit_type,
    institution_category, specific_type), we require an exact match.  Otherwise
    we fall back to substring matching in the full text.
    """
    if not tags:
        return True

    fm = _extract_frontmatter(text)
    haystack = text.lower()

    for key, value in tags.items():
        if not value:
            continue
        v = str(value)
        # Prefer exact frontmatter match when the key is present.
        if key in fm:
            if fm[key].strip() != v:
                return False
            continue
        # Fall back to substring matching for keys not in frontmatter.
        if v.lower() not in haystack:
            return False
    return True


def search_wiki(query: str, tags: Optional[Dict] = None) -> List[dict]:
    """
    本地知识库搜索（三层兜底的 Layer 2）

    搜索范围:
      1. references/ 下的 chapter*.md（能源审计章节指南）
      2. llm-wiki 自动生成的 wiki 页面（~/.hermes/rag/wiki/generated/）
      3. Obsidian wiki（HERMES_OBSIDIAN_WIKI，默认 E:/data/wiki）下的所有 .md 文件

    tags 过滤:
      本地 wiki 文件没有结构化标签字段，因此把 tags 中非空值作为必填关键字：
      只有文本或 frontmatter 中包含所有 tag 值的文档才会返回。
      同时 tag 值也会并入查询关键词参与相关性评分。
    """
    results: List[dict] = []
    keywords = [kw for kw in query.split() if kw]
    if tags:
        # Merge tag values into the keyword pool for scoring, preserving order.
        tag_values = [str(v).strip() for v in tags.values() if v]
        for tv in tag_values:
            if tv not in keywords:
                keywords.append(tv)
    if not keywords:
        return []

    def _add_result(score: float, filename: str, title: str, snippet: str, source: str, fm: dict | None = None):
        result_tags: dict = {'source': source}
        if tags:
            result_tags.update({k: str(v) for k, v in tags.items() if v})
        if fm:
            # Surface useful frontmatter metadata when present.
            for key in ('kb_name', 'doc_id', 'folder_id', 'type', 'confidence'):
                if key in fm:
                    result_tags.setdefault(key, fm[key])
        results.append({
            'score': score,
            'filename': filename,
            'chapter': title,
            'text': snippet,
            'tags': result_tags,
        })

    # —— 1. references 下的 chapter*.md ——
    for wiki_path in _WIKI_PATHS:
        if not wiki_path.exists():
            continue
        for md_file in wiki_path.glob("chapter*.md"):
            try:
                text = md_file.read_text(encoding='utf-8')
                if not _matches_wiki_tags(text, tags or {}):
                    continue
                score = _score_by_keyword_hits(text, keywords)
                if score > 0:
                    title = text.split('\n')[0].replace('# ', '') if text.startswith('#') else md_file.stem
                    _add_result(score, md_file.name, title, text[:2000], 'local_wiki')
            except Exception:
                pass

    # —— 2. llm-wiki generated pages ——
    if _LLM_WIKI_GENERATED.exists():
        for md_file in _LLM_WIKI_GENERATED.rglob("*.md"):
            rel = md_file.relative_to(_LLM_WIKI_GENERATED)
            if _is_excluded_wiki_path(rel):
                continue
            if md_file.name == "_index.md":
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                if not _matches_wiki_tags(text, tags or {}):
                    continue
                score = _score_by_keyword_hits(text, keywords)
                if score > 0:
                    fm = _extract_frontmatter(text)
                    _add_result(score, str(rel), _extract_frontmatter(text).get("title") or md_file.stem, text[:2000], 'llm_wiki_generated', fm)
            except Exception:
                pass

    # —— 3. Obsidian wiki ——
    if _OBSIDIAN_WIKI.exists():
        for md_file in _OBSIDIAN_WIKI.rglob("*.md"):
            rel = md_file.relative_to(_OBSIDIAN_WIKI)
            if _is_excluded_wiki_path(rel):
                continue
            if md_file.name in ("index.md", "log.md", "SCHEMA.md"):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                if not _matches_wiki_tags(text, tags or {}):
                    continue
                score = _score_by_keyword_hits(text, keywords)
                if score > 0:
                    _add_result(score, str(rel), _extract_frontmatter(text).get("title") or md_file.stem, text[:2000], 'obsidian_wiki')
            except Exception:
                pass

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:10]


# ============================================================
# Layer 3: 知识图谱因果诊断兜底
# ============================================================

_kg_instance = None


def _get_knowledge_graph():
    """Lazy-load the causal knowledge graph without embedding API calls."""
    global _kg_instance
    if _kg_instance is None:
        try:
            from rag.knowledge_graph.energy_kg import EnergyKnowledgeGraph
            _kg_instance = EnergyKnowledgeGraph()
            _kg_instance.load(build_vectors=False)
        except Exception:
            _kg_instance = None
    return _kg_instance


_SYSTEM_KEYWORDS = {
    '中央空调系统': ['空调', '冷机', 'COP', '冷冻水', '冷却水', '制冷', '供冷', '冷却塔', '风机盘管', '中央空调'],
    '供暖系统': ['供暖', '采暖', '供热', '锅炉', '耗热', '热耗', '暖气'],
    '照明系统': ['照明', '灯具', 'LED', '灯'],
    '变配电系统': ['变压器', '配电', '变配电', '功率因数'],
    '热水系统': ['热水', '太阳能'],
    '电梯系统': ['电梯', '扶梯'],
    '办公设备': ['办公设备', '电脑', '打印机'],
}


def _infer_system(query: str, tags: Dict) -> Optional[str]:
    """从查询和标签中推断用能系统类型。"""
    query_lower = query.lower()
    for system, kws in _SYSTEM_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in query_lower:
                return system
    # 标签中通常不包含 system，但保留扩展点
    for value in tags.values():
        for system, kws in _SYSTEM_KEYWORDS.items():
            for kw in kws:
                if kw.lower() in str(value).lower():
                    return system
    return None


def _format_diagnosis_result(result) -> str:
    """将 DiagnosisResult 格式化为文本片段。"""
    lines = [f"异常: {result.anomaly_description}"]
    if result.primary_cause:
        lines.append(
            f"最可能原因: {result.primary_cause.label} "
            f"(概率: {result.primary_cause.probability:.0%})"
        )
        if result.primary_cause.description:
            lines.append(f"原因说明: {result.primary_cause.description}")
        if result.primary_cause.check_method:
            lines.append(f"检查方法: {result.primary_cause.check_method}")
    if result.recommended_measures:
        lines.append("建议措施:")
        for m in result.recommended_measures:
            lines.append(
                f"- {m.label}: {m.description} "
                f"(投资: {m.investment_level}, 回收期: {m.payback_period}, "
                f"节能量: {m.estimated_saving_rate})"
            )
    if len(result.matched_chains) > 1:
        lines.append("\n相关异常:")
        for chain in result.matched_chains[1:3]:
            lines.append(f"- {chain.anomaly_description}")
    return '\n'.join(lines)


def _format_measures(system: str, measures: List[dict]) -> str:
    """格式化系统级节能措施。"""
    lines = [f"{system} 节能措施推荐:"]
    for m in measures:
        lines.append(
            f"- {m['label']}: {m['description']} "
            f"(投资: {m['investment']}, 回收期: {m['payback']}, "
            f"节能量: {m['saving_rate']})"
        )
    return '\n'.join(lines)


def search_knowledge_graph(query: str, tags: Optional[Dict] = None) -> List[dict]:
    """
    知识图谱因果诊断兜底（Layer 3）。

    适用于异常诊断、系统问题、节能措施类查询。
    先尝试直接诊断查询文本；若未命中且能推断出系统，则返回该系统下的节能措施。
    """
    kg = _get_knowledge_graph()
    if kg is None:
        return []

    tags = tags or {}
    results: List[dict] = []

    # 1) 直接因果诊断
    try:
        result = kg.diagnose(query)
        if result.has_diagnosis:
            results.append({
                'score': max(result.confidence, 0.5),
                'filename': 'knowledge_graph',
                'chapter': result.anomaly_description,
                'text': _format_diagnosis_result(result),
                'tags': {'source': 'knowledge_graph'},
            })
    except Exception:
        pass

    # 2) 系统级措施兜底（当直接诊断无结果时）
    if not results:
        system = _infer_system(query, tags)
        if system:
            try:
                measures = kg.get_measures_for_system(system)
                if measures:
                    results.append({
                        'score': 0.6,
                        'filename': 'knowledge_graph',
                        'chapter': f'{system}节能措施',
                        'text': _format_measures(system, measures[:10]),
                        'tags': {'source': 'knowledge_graph', 'system': system},
                    })
            except Exception:
                pass

    return results


# ============================================================
# 统一检索入口（四级兜底）
# ============================================================

def search_reports(query: str, tags: Optional[Dict] = None, top_k: int = 5) -> dict:
    """
    统一检索入口（四层兜底）

    Layer 0: Qdrant 标签直查（无需 API key）
    Layer 1: Qdrant 向量检索（语义匹配）
    Layer 2: 本地知识库（能源审计 references + Obsidian wiki 关键字匹配）
    Layer 3: 知识图谱因果诊断（异常 / 系统 / 措施）

    返回 {results: [...], source: 'qdrant_tags'|'qdrant_vector'|'wiki'|'knowledge_graph'|'none'}
    """
    # Layer 0: 标签直查
    if tags:
        try:
            results = search_by_tags(tags, top_k)
            if results:
                return {'results': results, 'source': 'qdrant_tags', 'count': len(results)}
        except Exception as e:
            print(f"[RAG] Qdrant tag search failed: {e}")

    # Layer 1: Qdrant 向量
    try:
        results = search_qdrant(query, tags, top_k)
        if results:
            return {'results': results, 'source': 'qdrant_vector', 'count': len(results)}
    except Exception as e:
        print(f"[RAG] Qdrant vector search failed: {e}")

    # Layer 2: wiki
    try:
        results = search_wiki(query, tags)
        if results:
            return {'results': results, 'source': 'wiki', 'count': len(results)}
    except Exception as e:
        print(f"[RAG] Wiki search failed: {e}")

    # Layer 3: knowledge graph
    try:
        results = search_knowledge_graph(query, tags)
        if results:
            return {'results': results, 'source': 'knowledge_graph', 'count': len(results)}
    except Exception as e:
        print(f"[RAG] Knowledge graph search failed: {e}")

    return {'results': [], 'source': 'none', 'count': 0}


def format_reference(results: dict) -> str:
    """格式化检索结果为可嵌入 prompt 的参考文本"""
    if not results.get('results'):
        return ""

    lines = [f"\n### 参考（来源: {results['source']}）\n"]
    for i, r in enumerate(results['results'], 1):
        tags_str = '/'.join(v for v in r.get('tags', {}).values() if v)
        score_str = f" (相似度: {r['score']:.2f})" if 'score' in r else ""
        lines.append(f"**参考{i}** [{tags_str}] {r['chapter']}{score_str}")
        lines.append(r['text'][:500])
        lines.append("---")
    return '\n'.join(lines)


# ============================================================
# Agent 调用接口
# ============================================================

def search_for_chapter(chapter_key: str, tags: Dict, context: str = "") -> str:
    """
    为特定章节检索参考内容

    示例:
      ref = search_for_chapter('第2章', {'institution_category': '医疗'}, '公共机构基本情况')
    """
    query = f"{tags.get('audit_type', '')} {tags.get('institution_category', '')} {tags.get('specific_type', '')} {chapter_key} {context}"
    results = search_reports(query, tags)
    return format_reference(results)


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    print("=== RAG 检索测试 ===\n")

    # 测试 Layer 0: 标签直查（无需 API key）
    print("1. 标签直查: institution_category=医疗")
    r = search_reports("", {'institution_category': '医疗'})
    print(f"  来源: {r['source']}, 结果数: {r['count']}")
    for item in r['results'][:3]:
        print(f"  {item['filename']} | {item['chapter']}")

    # 测试 Layer 0: 精准标签
    print("\n2. 标签直查: specific_type=法院")
    r = search_reports("", {'specific_type': '法院'})
    print(f"  来源: {r['source']}, 结果数: {r['count']}")
    for item in r['results'][:3]:
        print(f"  {item['filename']} | {item['chapter']}")

    # 测试 for chapter
    print("\n3. search_for_chapter: 医院 第2章")
    ref = search_for_chapter('第2章', {'institution_category': '医疗'}, '公共机构基本情况')
    print(ref[:500])

    print("\n✅ RAG 检索工具就绪")
