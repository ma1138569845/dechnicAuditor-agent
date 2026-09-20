"""
能源审计报告 RAG 检索工具

检索流程（逐层降级，任一层命中即返回）:
  1. Qdrant 向量检索（energy_audit_reports collection；tags 作 must-filter）
  2. 本地 wiki 兜底（技能包章节指南 + LLM Wiki 生成页）
  3. 知识图谱因果诊断 —— **不是"检索到历史报告"**

★2026-09-20：原"Layer 0 标签直查"**已废止短路**（它不看 query、命中后使语义检索永不执行）；
  需要按标签枚举时请显式调用 `search_by_tags()`。

⚠️ 第 3 层语义（2026-09-20 修正）：知识图谱是依据查询词生成的**因果推断**，
   不是报告片段。这类结果带 `is_report_chunk=False`，`search_reports` 会返回
   `is_report_retrieval=False` + `note`，`format_reference` 会加显著警示——
   **不得作为报告引用来源**。此前它伪装成 filename='knowledge_graph' 的报告片段，
   检索失败被当成了检索成功。

用法:
  from rag.rag_search import search_reports
  results = search_reports("医院 单位建筑面积非供暖能耗", tags={'institution_category': '医疗'})
"""

import os, json
from typing import Dict, List, Optional
from pathlib import Path

from rag.config import qdrant_client_kwargs, reports_collection

COLLECTION = reports_collection()

# 可用于 Qdrant must-filter 的 payload 键（其余键传进来会让过滤恒空，必须剔除）。
# 省/地市/区县等地理标签**不在 payload 里**，只能写进 query（见 imitate_pipeline 的注释）。
_FILTERABLE_TAG_KEYS = ("audit_type", "institution_category", "specific_type", "chapter",
                        "type", "filename")


def _sanitize_tags(tags: Optional[Dict]) -> Dict:
    """只保留真正存在于 payload 的过滤键，避免"传了不存在的键 → 恒空结果"。"""
    if not tags:
        return {}
    return {k: v for k, v in tags.items() if k in _FILTERABLE_TAG_KEYS and v}
# ============================================================
# 显式工具：按标签枚举（无需 embedding）
# ⚠️ 2026-09-20 起**不再参与** search_reports 的兜底链（原"Layer 0 短路"已废止）
# ============================================================

def search_by_tags(tags: Dict, limit: int = 10) -> List[dict]:
    """
    按标签精确筛选（不需要 embedding / API key）。适用于"把所有医疗类报告的第 2 章列出来"
    这类**按标签枚举**的需求。

    ⚠️ **它不看查询语义**（`scroll` 按内部顺序取前 N 条，结果 score 为空），
    因此**不得**作为 `search_reports` 默认路径使用——见 `search_reports` 的说明。
    要用它，请显式调用本函数。
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = QdrantClient(**qdrant_client_kwargs())

    tags = _sanitize_tags(tags)
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
    tags = _sanitize_tags(tags)
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

def _hermes_home() -> Path:
    """Hermes 数据家目录。

    ★2026-09-20 修：此前本文件用 ``Path.home()/".hermes"`` 拼 wiki 路径，
    而 Windows 上 Hermes 数据实际在 ``%LOCALAPPDATA%\\hermes``
    → wiki 兜底恒返回 0 条（静默失效）。现与
    ``tools/energy_audit/reference_library._hermes_report_dir`` 走同一条解析链。
    """
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        override = os.environ.get("HERMES_HOME")
        if override:
            return Path(override).expanduser()
        local = os.environ.get("LOCALAPPDATA")
        if os.name == "nt" and local:
            return Path(local) / "hermes"
        return Path.home() / ".hermes"


# 技能包章节指南目录（references/chapter*.md）。默认扫已部署的 energy-audit 技能树；
# 可用 HERMES_RAG_WIKI_PATHS（os.pathsep 分隔）覆盖。
_WIKI_PATHS = [
    Path(p).expanduser()
    for p in (os.environ.get("HERMES_RAG_WIKI_PATHS") or "").split(os.pathsep)
    if p.strip()
] or [_hermes_home() / "skills" / "energy-audit"]

# 用户私有 Obsidian/wiki vault（可选；**仅在显式设置环境变量时启用**，
# 此前默认指向不存在的 ~/wiki，属无效兜底）
_OBSIDIAN_WIKI = (
    Path(os.environ["HERMES_OBSIDIAN_WIKI"]).expanduser()
    if os.environ.get("HERMES_OBSIDIAN_WIKI")
    else None
)

# 知识库导入管道自动生成的 llm-wiki 页面（默认 %LOCALAPPDATA%\hermes\rag\wiki\generated）
_LLM_WIKI_VAULT = Path(
    os.getenv("HERMES_WIKI_VAULT") or (_hermes_home() / "rag" / "wiki")
).expanduser()
_LLM_WIKI_GENERATED = _LLM_WIKI_VAULT / "generated"

# 排除的 wiki 目录/文件（杂项）
_WIKI_EXCLUDE_DIRS = {"_meta", "raw", "未命名.base", ".obsidian"}


def _is_excluded_wiki_path(rel: Path) -> bool:
    """是否跳过该 wiki 相对路径。

    ★2026-09-20 修：本函数此前**被调用两次但从未定义**（NameError 一直没暴露，
    因为 wiki 目录不存在、那段代码从没执行到）。修好路径后必须先补上定义。
    """
    parts = list(rel.parts)
    if set(parts) & _WIKI_EXCLUDE_DIRS:
        return True
    # 归档副本不参与检索，避免与 live 文件重复命中
    if any(p == "_archive" or p.startswith("_archive") for p in parts[:-1]):
        return True
    name = rel.name
    return name.startswith("~$") or name.endswith(".bak")

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
      1. 技能包的 chapter*.md 章节指南（`_WIKI_PATHS`，默认 <hermes_home>/skills/energy-audit）
      2. LLM Wiki 自动生成的页面（`_LLM_WIKI_GENERATED`，默认 <hermes_home>/rag/wiki/generated/）
      3. Obsidian wiki（**仅当设置 HERMES_OBSIDIAN_WIKI 时**）下的所有 .md 文件

    注：本层返回的都是**知识库/指南文本**，不是历史报告片段；引用时须注明来源文件。

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

    # —— 1. 技能包章节指南 chapter*.md ——
    for wiki_path in _WIKI_PATHS:
        if not wiki_path.exists():
            continue
        for md_file in wiki_path.rglob("chapter*.md"):
            rel = md_file.relative_to(wiki_path)
            if _is_excluded_wiki_path(rel):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                if not _matches_wiki_tags(text, tags or {}):
                    continue
                score = _score_by_keyword_hits(text, keywords)
                if score > 0:
                    title = text.split('\n')[0].replace('# ', '') if text.startswith('#') else md_file.stem
                    _add_result(score, str(rel), title, text[:2000], 'skill_guide')
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
    if _OBSIDIAN_WIKI and _OBSIDIAN_WIKI.exists():
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
                # ★不是报告片段：显式标注，避免被当历史报告引用（2026-09-20 修）
                'filename': '（知识图谱推断·非报告）',
                'kind': 'knowledge_graph_diagnosis',
                'is_report_chunk': False,
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
                        'filename': '（知识图谱推断·非报告）',
                        'kind': 'knowledge_graph_measures',
                        'is_report_chunk': False,
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

    Layer 1: Qdrant 向量检索（语义匹配；**tags 仅作 must-filter**，不短路）
    Layer 2: 本地知识库（技能包章节指南 + LLM Wiki 关键字匹配）
    Layer 3: 知识图谱因果诊断（异常 / 系统 / 措施）—— **非报告来源**

    返回 {
      results: [...],
      source: 'qdrant_tags'|'qdrant_vector'|'wiki'|'knowledge_graph'|'none',
      count: int,
      is_report_retrieval: bool,   # False ⇒ 结果不是历史报告片段，不得作为报告引用
      degraded: [str],             # 本次降级原因（Qdrant 不通 / wiki 目录缺失 等）
      note: str,                   # 面向调用方的显式说明（未命中时给出）
    }

    ★2026-09-20：此前 Layer 3 的结果与真实报告片段**同形**，导致"检索失败"被当成
    "检索成功"（Qdrant 未启动 + wiki 路径写错时尤其严重）。现显式区分。
    """
    degraded: List[str] = []

    # ★2026-09-20 废止「Layer 0 标签直查短路」：
    #   search_by_tags 用 scroll 按标签取前 N 条，**完全不看 query**
    #   （实测把"东营职业学院/省委党校/山东技师学院"返回给"学校 宿舍 空调用电 分析"，
    #     score 为空），而且一旦命中就直接 return → 真正的语义检索永不执行。
    #   现改为：**tags 只作 filter**，与 query 一起进向量检索（见下方 Layer 1）。
    #   search_by_tags 仍保留为显式工具（要"按标签枚举"时直接调它）。

    # Layer 1: Qdrant 向量检索（tags 作 must-filter）
    try:
        results = search_qdrant(query, tags, top_k)
        if results:
            return {'results': results, 'source': 'qdrant_vector', 'count': len(results),
                    'is_report_retrieval': True, 'degraded': degraded, 'note': ''}
    except Exception as e:
        degraded.append('qdrant_vector')
        print(f"[RAG] ⚠️ Qdrant 向量检索不可用（{e}）；降级到下一层")

    # Layer 2: wiki
    try:
        if not _LLM_WIKI_GENERATED.exists():
            degraded.append('llm_wiki_missing')
        results = search_wiki(query, tags)
        if results:
            return {'results': results, 'source': 'wiki', 'count': len(results),
                    'is_report_retrieval': True, 'degraded': degraded, 'note': ''}
    except Exception as e:
        degraded.append('wiki')
        print(f"[RAG] ⚠️ 本地 wiki 检索失败（{e}）；降级到下一层")

    # Layer 3: knowledge graph —— 不是报告检索，必须显式标注
    try:
        results = search_knowledge_graph(query, tags)
        if results:
            why = '、'.join(degraded) if degraded else '知识库无命中'
            return {
                'results': results, 'source': 'knowledge_graph', 'count': len(results),
                'is_report_retrieval': False, 'degraded': degraded,
                'note': (f'未检索到历史报告（降级链：{why}）。以下为知识图谱依据查询词生成的'
                         f'因果推断，**不得作为报告引用来源**，仅可用于诊断思路与措施候选。'),
            }
    except Exception as e:
        degraded.append('knowledge_graph')
        print(f"[RAG] ⚠️ 知识图谱检索失败（{e}）")

    return {
        'results': [], 'source': 'none', 'count': 0,
        'is_report_retrieval': False, 'degraded': degraded,
        'note': ('未检索到任何内容。降级链：' + ('、'.join(degraded) if degraded else '各层均无命中') +
                 '。请检查 Qdrant 是否启动、wiki 是否已生成，或改用项目本地参考库。'),
    }


def format_reference(results: dict) -> str:
    """格式化检索结果为可嵌入 prompt 的参考文本。

    ★2026-09-20：当来源不是历史报告（如知识图谱推断）时，输出显著警示，
    避免被当作可引用来源写进报告。
    """
    if not results.get('results'):
        return ""

    is_report = results.get('is_report_retrieval', True)
    if is_report:
        lines = [f"\n### 参考（来源: {results['source']}）\n"]
    else:
        lines = [
            f"\n### ⚠️ 非报告来源：知识图谱推断（来源: {results['source']}）",
            f"> {results.get('note') or '未检索到历史报告，以下内容不是报告片段。'}",
            "> 用途限定：仅可作为诊断思路/措施候选；**引用进报告前必须另行取证**。",
            "",
        ]
    for i, r in enumerate(results['results'], 1):
        tags_str = '/'.join(v for v in r.get('tags', {}).values() if v)
        score_str = f" (相似度: {r['score']:.2f})" if 'score' in r else ""
        prefix = "**参考" if is_report else "**推断"
        lines.append(f"{prefix}{i}** [{tags_str}] {r['chapter']}{score_str}")
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

    # 1) 显式按标签枚举（无 query 语义，score 为空——这是 search_by_tags 的定位）
    print("1. search_by_tags 枚举: institution_category=医疗")
    try:
        for item in search_by_tags({'institution_category': '医疗'}, 3):
            print(f"  {item['filename']} | {item['chapter']}")
    except Exception as e:
        print(f"  ⚠️ 跳过（Qdrant 不可达）：{e}")

    # 2) 语义检索 + 标签过滤（tags 只作 filter，不再短路）
    print("\n2. search_reports(语义+filter): 学校 宿舍 空调用电")
    try:
        r = search_reports("学校 宿舍 空调用电", {'institution_category': '教育'})
        print(f"  来源: {r['source']}, 结果数: {r['count']}, degraded={r['degraded']}")
        for item in r['results'][:3]:
            print(f"  {item['filename']} | {item['chapter']} | score={item.get('score')}")
    except Exception as e:
        print(f"  ⚠️ 失败：{e}")

    # 测试 for chapter
    print("\n3. search_for_chapter: 医院 第2章")
    try:
        ref = search_for_chapter('第2章', {'institution_category': '医疗'}, '公共机构基本情况')
        print(ref[:500])
    except Exception as e:
        print(f"  ⚠️ 失败：{e}")

    print("\n✅ RAG 检索工具就绪")
