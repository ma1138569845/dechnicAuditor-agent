from __future__ import annotations

"""
能源审计 RAG / 知识图谱检索工具（Hermes Agent 入口）

把 rag.rag_search 与 rag.knowledge_graph.energy_kg 包装为模型可调用的工具，
支持四层检索兜底：Qdrant 标签直查、Qdrant 向量检索、本地 wiki、知识图谱因果诊断。

返回结构包含：
- 原始报告/知识库文档片段
- 知识图谱异常诊断（可能原因 + 检查方法）
- 节能措施推荐
- 引用标准/条文来源

注意： discover_builtin_tools() 只扫描 tools/*.py，因此本文件必须放在 tools/ 根目录。
"""

from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error, tool_result

try:
    from rag.rag_search import search_reports, search_knowledge_graph
    _RAG_AVAILABLE = True
    _RAG_IMPORT_ERROR = ""
except Exception as _rag_import_err:
    _RAG_AVAILABLE = False
    _RAG_IMPORT_ERROR = str(_rag_import_err)


# ============================================================
# Schema
# ============================================================

ENERGY_AUDIT_RAG_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "检索问题。把省份/地市/区县写进 query（不要当 payload 过滤），再写章节主题。例如：山东 烟台 经济技术开发区 公共机构 能源资源管理状况。",
        },
        "institution_category": {
            "type": "string",
            "description": "机构大类过滤。例如：医疗、教育、党政机关、体育场馆。",
        },
        "specific_type": {
            "type": "string",
            "description": "机构具体类型过滤。例如：医院、学校、法院。",
        },
        "audit_type": {
            "type": "string",
            "description": "审计类型过滤。例如：公共机构能源审计、工业企业能源审计。",
        },
        "system": {
            "type": "string",
            "description": "用能系统过滤，用于知识图谱节能措施检索。例如：中央空调系统、照明系统、供暖系统、变配电系统。",
        },
        "top_k": {
            "type": "integer",
            "description": "返回文档片段数量上限，默认 5，最大 20。",
            "minimum": 1,
            "maximum": 20,
        },
        "include_knowledge_graph": {
            "type": "boolean",
            "description": "是否同时调用知识图谱进行因果诊断与节能措施检索，默认 true。",
        },
    },
    "required": ["query"],
}


# ============================================================
# Helpers
# ============================================================

def _build_tags(args: Dict[str, Any]) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for key in ("institution_category", "specific_type", "audit_type"):
        value = args.get(key)
        if value and str(value).strip():
            tags[key] = str(value).strip()
    return tags


def _load_knowledge_graph() -> Optional["EnergyKnowledgeGraph"]:
    if not _RAG_AVAILABLE:
        return None
    try:
        from rag.knowledge_graph.energy_kg import EnergyKnowledgeGraph
        kg = EnergyKnowledgeGraph()
        kg.load(build_vectors=False)
        return kg
    except Exception:
        return None


def _format_kg_diagnosis(kg_result: Dict[str, Any]) -> Dict[str, Any]:
    text = kg_result.get("text", "")
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    anomaly = ""
    primary_cause = ""
    cause_description = ""
    check_method = ""
    measures: List[Dict[str, str]] = []
    related_anomalies: List[str] = []

    current_section: Optional[str] = None
    for line in lines:
        if line.startswith("异常:"):
            anomaly = line.replace("异常:", "").strip()
            current_section = "anomaly"
        elif line.startswith("最可能原因:"):
            primary_cause = line.replace("最可能原因:", "").strip()
            current_section = "cause"
        elif line.startswith("原因说明:"):
            cause_description = line.replace("原因说明:", "").strip()
        elif line.startswith("检查方法:"):
            check_method = line.replace("检查方法:", "").strip()
        elif line.startswith("建议措施:"):
            current_section = "measures"
        elif line.startswith("- ") and current_section == "measures":
            # Format: "- 措施名: 描述 (投资: X, 回收期: Y, 节能量: Z)"
            content = line[2:]
            label = content.split(":")[0] if ":" in content else content
            measures.append({
                "label": label.strip(),
                "description": content.strip(),
            })
        elif line.startswith("相关异常:"):
            current_section = "related"
        elif line.startswith("- ") and current_section == "related":
            related_anomalies.append(line[2:].strip())

    return {
        "anomaly": anomaly,
        "primary_cause": primary_cause,
        "cause_description": cause_description,
        "check_method": check_method,
        "measures": measures,
        "related_anomalies": related_anomalies,
        "confidence": kg_result.get("score"),
        "source": kg_result.get("tags", {}).get("source"),
    }


def _format_kg_measures(system: str, measures: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "system": system,
        "measures": [
            {
                "label": m.get("label", ""),
                "description": m.get("description", ""),
                "saving_rate": m.get("saving_rate", ""),
                "investment": m.get("investment", ""),
                "payback": m.get("payback", ""),
                "references": m.get("references", []),
            }
            for m in measures
        ],
    }


def _collect_references(results: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    for r in results.get("results", []):
        for key, value in (r.get("tags") or {}).items():
            if value and isinstance(value, str):
                refs.append(value)
    return sorted(set(refs))


# ============================================================
# Handler
# ============================================================

def _handle_energy_audit_rag_search(args: Dict[str, Any], **kwargs) -> str:
    if not _RAG_AVAILABLE:
        return tool_error(
            f"能源审计 RAG 工具当前不可用。可能原因：{_RAG_IMPORT_ERROR or '依赖未安装或知识库未配置'}。"
            "请检查 rag/ 目录及依赖。"
        )

    query = str(args.get("query", "")).strip()
    if not query:
        return tool_error("query 不能为空，请提供检索问题。")

    tags = _build_tags(args)
    top_k = int(args.get("top_k") or 5)
    include_kg = bool(args.get("include_knowledge_graph", True))
    system_filter = str(args.get("system", "")).strip()

    # 1) 统一 RAG 检索（报告 + wiki）
    try:
        rag_results = search_reports(query, tags, top_k)
    except Exception as e:
        rag_results = {"results": [], "source": "none", "count": 0, "error": str(e)}

    documents = [
        {
            "index": i + 1,
            "source": r.get("tags", {}).get("source", rag_results.get("source", "unknown")),
            "filename": r.get("filename", ""),
            "chapter": r.get("chapter", ""),
            "score": r.get("score"),
            "text": r.get("text", ""),
            "tags": r.get("tags", {}),
        }
        for i, r in enumerate(rag_results.get("results", []))
    ]

    # 2) 知识图谱诊断与措施
    kg_diagnosis: Optional[Dict[str, Any]] = None
    kg_measures: Optional[Dict[str, Any]] = None
    kg_references: List[str] = []

    if include_kg:
        kg_query = query
        if system_filter:
            kg_query = f"{system_filter} {query}"

        try:
            kg_results = search_knowledge_graph(kg_query, tags)
            if kg_results:
                kg_diagnosis = _format_kg_diagnosis(kg_results[0])
                kg_references.extend(
                    ref for ref in (kg_results[0].get("tags") or {}).values() if isinstance(ref, str)
                )
        except Exception:
            pass

        # 如果指定了系统，单独获取系统级节能措施
        if system_filter:
            try:
                kg = _load_knowledge_graph()
                if kg:
                    measures = kg.get_measures_for_system(system_filter)
                    if measures:
                        kg_measures = _format_kg_measures(system_filter, measures)
                        for m in measures:
                            kg_references.extend(m.get("references", []))
            except Exception:
                pass

    # 3) 组装返回
    output = {
        "query": query,
        "filters": tags,
        "source": rag_results.get("source", "none"),
        "document_count": len(documents),
        "documents": documents,
        "knowledge_graph": {
            "diagnosis": kg_diagnosis,
            "measures": kg_measures,
        },
        "references": sorted(set(_collect_references(rag_results) + kg_references)),
    }

    if not documents and not kg_diagnosis and not kg_measures:
        output["notice"] = "未找到与查询相关的内容。请尝试调整 query、放宽过滤条件或检查知识库/Qdrant 是否已配置。"

    return tool_result(output)


# ============================================================
# Registration
# ============================================================

registry.register(
    name="energy_audit_rag_search",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_RAG_SEARCH_SCHEMA,
    handler=_handle_energy_audit_rag_search,
    emoji="📚",
)
