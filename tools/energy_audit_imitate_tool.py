from __future__ import annotations

"""
能源审计章节仿写工具（Hermes Agent 入口）

按项目加载数据 → 检索同类参考报告 → 分析段落结构 → Agent 仿写。
支持单章段落，或仿写全部章节并生成 Word。

discover_builtin_tools() 只扫描 tools/*.py，因此本文件必须放在 tools/ 根目录。
"""

from typing import Any, Dict

from hermes_constants import display_hermes_home
from tools.registry import registry, tool_error, tool_result

_DEFAULT_REFERENCE_DIR = f"{display_hermes_home()}/rag/report"


ENERGY_AUDIT_IMITATE_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "被审计单位或项目名称。例如：莘县县政府、山东省人力资源和社会保障厅。",
        },
        "chapter": {
            "type": "string",
            "description": "要仿写的章节。例如：第3章、3、3.1、第三章。",
        },
        "section": {
            "type": "string",
            "description": "可选小节。例如：3.1 机构职责、能源资源管理目标和方针。",
        },
        "institution_category": {
            "type": "string",
            "description": "覆盖机构大类过滤。例如：医疗、教育、党政机关、场馆。缺省用项目自身分类。",
        },
        "specific_type": {
            "type": "string",
            "description": "覆盖具体类型过滤。例如：医院、学校、法院。",
        },
        "audit_type": {
            "type": "string",
            "description": "覆盖审计类型。例如：公共机构、公共建筑。",
        },
        "reference_dir": {
            "type": "string",
            "description": f"同类参考报告根目录。缺省 {_DEFAULT_REFERENCE_DIR}/{{省}}/{{市}}/{{区县}}/{{审计类型}}。检索先匹配区县、再地市、再省份。",
        },
        "extra_context": {
            "type": "string",
            "description": "额外检索上下文，写入 RAG 查询。",
        },
        "top_k": {
            "type": "integer",
            "description": "参考报告片段数量上限，默认 5，最大 10。",
            "minimum": 1,
            "maximum": 10,
        },
        "refresh_from_pg": {
            "type": "boolean",
            "description": "是否强制从 PostgreSQL 重新采集项目数据。默认 false，优先读本地已保存项目。",
        },
    },
    "required": ["project_name", "chapter"],
}


def _handle_imitate_paragraph(args: Dict[str, Any], **kwargs) -> str:
    project_name = str(args.get("project_name") or "").strip()
    chapter = str(args.get("chapter") or "").strip()
    if not project_name:
        return tool_error("project_name 不能为空，请提供被审计单位或项目名称。")
    if not chapter:
        return tool_error("chapter 不能为空，请提供章节，例如 第3章。")

    try:
        top_k = int(args.get("top_k") or 5)
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 10))

    try:
        from tools.energy_audit.imitate_pipeline import result_to_jsonable, run_imitate
    except Exception as e:
        return tool_error(f"仿写流水线加载失败：{e}")

    try:
        result = run_imitate(
            project_name,
            chapter,
            section=str(args.get("section") or "").strip(),
            institution_category=str(args.get("institution_category") or "").strip(),
            specific_type=str(args.get("specific_type") or "").strip(),
            audit_type=str(args.get("audit_type") or "").strip(),
            extra_context=str(args.get("extra_context") or "").strip(),
            top_k=top_k,
            refresh_from_pg=bool(args.get("refresh_from_pg", False)),
            reference_dir=str(args.get("reference_dir") or "").strip(),
        )
    except Exception as e:
        return tool_error(f"仿写失败：{e}")

    payload = result_to_jsonable(result)
    if not payload.get("ok"):
        return tool_error(payload.get("error") or "仿写失败")
    return tool_result(payload)


def rest_imitate_energy_audit_paragraph(
    project_name: str,
    chapter: str,
    section: str = "",
    institution_category: str = "",
    specific_type: str = "",
    audit_type: str = "",
    extra_context: str = "",
    top_k: int = 5,
    refresh_from_pg: bool = False,
) -> dict:
    """REST 版本：返回 dict，供 /api/energy-audit/imitate 使用。"""
    project_name = (project_name or "").strip()
    chapter = (chapter or "").strip()
    if not project_name:
        return {"error": "project_name 不能为空", "message": "请提供单位/项目名称"}
    if not chapter:
        return {"error": "chapter 不能为空", "message": "请提供章节，例如 第3章"}

    try:
        from tools.energy_audit.imitate_pipeline import result_to_jsonable, run_imitate
    except ImportError as e:
        return {"error": "仿写流水线加载失败", "message": str(e)}

    try:
        result = run_imitate(
            project_name,
            chapter,
            section=section or "",
            institution_category=institution_category or "",
            specific_type=specific_type or "",
            audit_type=audit_type or "",
            extra_context=extra_context or "",
            top_k=int(top_k or 5),
            refresh_from_pg=bool(refresh_from_pg),
        )
    except Exception as e:
        return {"error": "仿写失败", "message": str(e)}

    payload = result_to_jsonable(result)
    if not payload.get("ok"):
        return {"error": payload.get("error") or "仿写失败", "message": payload.get("error") or "仿写失败"}
    payload["ok"] = True
    return payload


registry.register(
    name="energy_audit_imitate_paragraph",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_IMITATE_SCHEMA,
    handler=_handle_imitate_paragraph,
    emoji="✍️",
)


ENERGY_AUDIT_IMITATE_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "被审计单位或项目名称。例如：烟台经济技术开发区人民法院。",
        },
        "audit_type": {
            "type": "string",
            "description": "审计类型：公共机构、公共建筑、工业企业。缺省用项目自身类型。",
        },
        "institution_category": {
            "type": "string",
            "description": "覆盖机构大类。例如：党政机关、医疗、教育。",
        },
        "specific_type": {
            "type": "string",
            "description": "覆盖具体类型。例如：法院、医院。",
        },
        "reference_dir": {
            "type": "string",
            "description": f"同类参考报告根目录。缺省 {_DEFAULT_REFERENCE_DIR}/{{省}}/{{市}}/{{区县}}/{{审计类型}}。检索先匹配区县、再地市、再省份。",
        },
        "output_dir": {
            "type": "string",
            "description": "Word 输出目录，默认 ./reports。",
        },
        "top_k": {
            "type": "integer",
            "description": "每章参考报告数量上限，默认 3，最大 8。",
            "minimum": 1,
            "maximum": 8,
        },
    },
    "required": ["project_name"],
}


def _handle_imitate_report(args: Dict[str, Any], **kwargs) -> str:
    project_name = str(args.get("project_name") or "").strip()
    if not project_name:
        return tool_error("project_name 不能为空，请提供被审计单位或项目名称。")
    try:
        top_k = int(args.get("top_k") or 3)
    except (TypeError, ValueError):
        top_k = 3
    top_k = max(1, min(top_k, 8))
    try:
        from tools.energy_audit.imitate_pipeline import result_to_jsonable, run_imitate_report
    except Exception as e:
        return tool_error(f"仿写流水线加载失败：{e}")
    try:
        result = run_imitate_report(
            project_name,
            audit_type=str(args.get("audit_type") or "").strip(),
            institution_category=str(args.get("institution_category") or "").strip(),
            specific_type=str(args.get("specific_type") or "").strip(),
            output_dir=str(args.get("output_dir") or "").strip(),
            top_k=top_k,
            refresh_from_pg=True,
            reference_dir=str(args.get("reference_dir") or "").strip(),
        )
    except Exception as e:
        return tool_error(f"仿写生成报告失败：{e}")
    payload = result_to_jsonable(result)
    if not payload.get("ok"):
        return tool_error(payload.get("error") or "仿写生成报告失败")
    return tool_result(payload)


registry.register(
    name="energy_audit_imitate_report",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_IMITATE_REPORT_SCHEMA,
    handler=_handle_imitate_report,
    emoji="📄",
)
