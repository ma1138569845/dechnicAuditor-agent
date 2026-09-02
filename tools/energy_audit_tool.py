"""
能源审计 PG 查询工具（Hermes Agent 入口）

把 tools/energy_audit/pg_collector.py 与 pg_query.py 的能力注册为 Hermes 模型工具，
使 Agent 能够通过自然语言查询能源审计项目、设备、建筑、能耗等信息。

注意： discover_builtin_tools() 只扫描 tools/*.py，因此本文件必须放在 tools/ 根目录，
子目录 tools/energy_audit/*.py 中的 registry.register() 不会被自动发现。
"""

import os

from tools.registry import registry, tool_error, tool_result

# 能源审计 PG 查询依赖 psycopg2 / pandas 等可选依赖。
# 若未安装，工具仍会注册，但 check_fn 会阻止其出现在模型 schema 中，
# handler 也会返回友好错误提示。
from tools.energy_audit.project_data import shared_office_metering_sentence

try:
    from tools.energy_audit.pg_collector import collect_from_pg
    from tools.energy_audit.pg_query import PgDataQuery
    _PG_AVAILABLE = True
    _PG_IMPORT_ERROR = ""
except Exception as _pg_import_err:
    _PG_AVAILABLE = False
    _PG_IMPORT_ERROR = str(_pg_import_err)


# ============================================================
# 可用性检查（service-gated tool：未配置 PG 时不向模型暴露）
# ============================================================

def _check_energy_audit_available() -> bool:
    """检查能源审计 PG 数据库是否可连接。"""
    if not _PG_AVAILABLE:
        return False
    try:
        with PgDataQuery() as db:
            return db.ping()
    except Exception:
        return False


def _pg_unavailable_result():
    return tool_error(
        f"能源审计数据库工具当前不可用。可能原因：{_PG_IMPORT_ERROR or 'PG 数据库未配置或无法连接'}。"
        "请安装依赖（pip install psycopg2-binary pandas）并配置数据库。"
    )


# ============================================================
# 格式化辅助
# ============================================================

def _yes_no(v, yes="是", no="否"):
    if v is None:
        return ""
    try:
        return yes if int(v) == 1 else no
    except (TypeError, ValueError):
        return ""


def _format_project_summary(result: dict) -> str:
    """把 collect_from_pg 的完整结果格式化为可读 Markdown。"""
    found = result.get("found", {})
    missing = result.get("missing", [])
    lines = []

    proj = found.get("project", {})
    if proj:
        lines.append("## 项目基本信息")
        lines.append(f"- 单位名称：{proj.get('unit_name', '')}")
        lines.append(f"- 联系人：{proj.get('contact_person', '')}")
        lines.append(f"- 联系电话：{proj.get('contact_phone', '')}")
        lines.append(f"- 审计部门：{proj.get('auditor', '')}")
        if proj.get('audit_org_name'):
            lines.append(f"- 审计机构名称：{proj.get('audit_org_name', '')}")
        if proj.get('audit_org_address'):
            lines.append(f"- 审计机构地址：{proj.get('audit_org_address', '')}")
        if proj.get('audit_org_contact'):
            lines.append(f"- 审计机构负责人：{proj.get('audit_org_contact', '')}")
        if proj.get('audit_org_phone'):
            lines.append(f"- 审计机构联系方式：{proj.get('audit_org_phone', '')}")
        missing_org = [k for k in ('audit_org_address', 'audit_org_contact', 'audit_org_phone')
                       if not proj.get(k)]
        if missing_org:
            lines.append(f"- ⚠️ 审计机构信息待用户提供：{('、'.join({'audit_org_address': '详细地址', 'audit_org_contact': '负责人', 'audit_org_phone': '联系方式'}[k] for k in missing_org))}")
        if proj.get('audit_year'):
            lines.append(f"- 审计年度：{proj.get('audit_year')}")
        if proj.get('data_year'):
            lines.append(f"- 数据年度：{proj.get('data_year')}")
        lines.append("")

    buildings = found.get("buildings", [])
    if buildings:
        lines.append(f"## 建筑信息（{len(buildings)} 栋）")
        for b in buildings:
            lines.append(
                f"- **{b.get('name', '未命名')}**：建筑面积 {b.get('area', 0)} m²，"
                f"地上 {b.get('up_floor', 0)} 层 / 地下 {b.get('down_floor', 0)} 层，"
                f"功能：{b.get('function', '')}{' - ' + b.get('function_zoning', '') if b.get('function_zoning') else ''}"
            )
        lines.append("")

    energy = found.get("energy_yearly", [])
    if energy:
        lines.append(f"## 能耗数据（{len(energy)} 个年度）")
        for e in energy:
            year = e.get('year', '')
            parts = []
            for k, label in [
                ('electricity_kwh', '用电量'),
                ('water_m3', '用水量'),
                ('natural_gas_m3', '天然气'),
                ('heating_energy_heat_gj', '热能'),
                ('petrol_kg', '汽油'),
                ('diesel_kg', '柴油'),
            ]:
                if e.get(k):
                    parts.append(f"{label} {e[k]}")
            lines.append(f"- **{year} 年**：{', '.join(parts) if parts else '仅有费用/原始数据'}")
        lines.append("")

    equipment = found.get("equipment", [])
    if equipment:
        lines.append(_format_equipment_section(equipment))

    metering = found.get("metering", {})
    if metering:
        lines.append("## 计量与监测")
        lines.append(f"- 能耗监测系统：{_yes_no(metering.get('has_monitoring_system'))}")
        lines.append(f"- 分项计量：{_yes_no(metering.get('has_separate_metering'))}")
        lines.append(f"- 分户计量：{_yes_no(metering.get('has_household_metering'))}")
        if 'has_household_payment' in metering:
            lines.append(f"- 分户缴费：{_yes_no(metering.get('has_household_payment'))}")
        shared_line = shared_office_metering_sentence(
            metering.get('has_shared_office'), found.get('shared_offices') or [],
        )
        if shared_line:
            lines.append(f"- {shared_line}")
        for key, label in (
            ('independent_light_socket', '照明插座独立计量'),
            ('independent_power', '动力用电独立计量'),
            ('independent_aircon', '空调用电独立计量'),
            ('independent_special', '特殊用电独立计量'),
            ('independent_construction_elec', '施工用电独立计量'),
            ('independent_construction_water', '施工用水独立计量'),
        ):
            if key in metering:
                lines.append(f"- {label}：{_yes_no(metering.get(key))}")
        other_special = (metering.get('independent_other_special') or '').strip()
        if other_special:
            lines.append(f"- 其他特殊用电独立计量：{other_special}")
        lines.append("")

    shared_offices = found.get("shared_offices") or []
    if shared_offices:
        lines.append(f"## 合署办公（{len(shared_offices)} 家）")
        for row in shared_offices:
            name = row.get("dept_name") or "未命名单位"
            building = row.get("building") or ""
            loc = f" @ {building}" if building else ""
            meter = (row.get("independent_metering") or "").strip()
            meter_part = f" | 独立计量：{meter}" if meter else ""
            area = row.get("area")
            area_part = f" | {area} m²" if area else ""
            lines.append(f"- **{name}**{loc}{area_part}{meter_part}")
        lines.append("")

    team = found.get("team_members", [])
    if team:
        lines.append(f"## 审计组成员（{len(team)} 人）")
        for m in team[:10]:
            lines.append(f"- {m.get('name', '')} / {m.get('role', '')} / {m.get('certification', '')}")
        if len(team) > 10:
            lines.append(f"- ... 等共 {len(team)} 人")
        lines.append("")

    audited = found.get("audited_users", [])
    if audited:
        lines.append(f"## 被审计方配合人员（{len(audited)} 人）")
        for m in audited[:10]:
            lines.append(f"- {m.get('name', '')} / {m.get('role', '')} / {m.get('dept', '')} / {m.get('position', '')}")
        if len(audited) > 10:
            lines.append(f"- ... 等共 {len(audited)} 人")
        lines.append("")

    if missing:
        lines.append("## 缺失数据")
        for m in missing:
            lines.append(f"- ⚠️ {m}")
        lines.append("")

    return "\n".join(lines)


def _format_equipment_section(equipment: list, category: str = None) -> str:
    """格式化设备列表为 Markdown。"""
    if category:
        equipment = [e for e in equipment if e.get("category") == category]
    if not equipment:
        return "## 设备清单\n\n未找到设备记录。\n"

    # 按类别分组
    groups: dict = {}
    for e in equipment:
        cat = e.get("category", "其他")
        groups.setdefault(cat, []).append(e)

    lines = [f"## 设备清单（共 {len(equipment)} 条）\n"]
    for cat in sorted(groups.keys()):
        items = groups[cat]
        lines.append(f"### {cat}（{len(items)} 条）")
        for e in items:
            name = e.get("name", "未命名")
            spec = e.get("spec", "")
            qty = e.get("quantity", 0)
            spec_part = f" | {spec}" if spec else ""
            meter = (e.get("independent_metering") or "").strip()
            meter_part = f" | 独立计量：{meter}" if meter else ""
            desc = (e.get("independent_metering_desc") or "").strip()
            desc_part = f"（{desc}）" if desc else ""
            lines.append(f"- **{name}** × {qty}{spec_part}{meter_part}{desc_part}")
        lines.append("")
    return "\n".join(lines)


def _format_buildings(buildings: list) -> str:
    if not buildings:
        return "未找到建筑信息。"
    lines = [f"共 {len(buildings)} 栋建筑：\n"]
    for b in buildings:
        lines.append(
            f"- **{b.get('name', '未命名')}**：{b.get('area', 0)} m²，"
            f"{b.get('floors', '')}，功能 {b.get('function', '')}"
        )
    return "\n".join(lines)


def _format_energy(energy: list) -> str:
    if not energy:
        return "未找到能耗数据。"
    lines = []
    for e in energy:
        lines.append(f"- **{e.get('year', '')} 年** {e.get('energy_name', '')}："
                     f"本单位 {e.get('unit_total_value', '')} {e.get('energy_unit', '')}")
    return "\n".join(lines)


def _format_energy_meter(meters: list) -> str:
    if not meters:
        return "未找到表具计量信息。"
    type_map = {1: "电表", 2: "水表"}
    lines = [f"共 {len(meters)} 条表具计量记录：\n"]
    for m in meters:
        year = m.get('statistical_year') or '-'
        dtype = type_map.get(m.get('data_type'), '未知')
        parts = [f"类型:{dtype}"]
        if m.get('has_other_meter') == 1:
            parts.append(f"有其他计量表（{m.get('meter_count') or 0} 只）")
        else:
            parts.append("无其他计量表")
        if m.get('sub_metering'):
            parts.append(f"分项计量:{m['sub_metering']}")
        if m.get('measured_depth'):
            parts.append(f"计量深度:{m['measured_depth']}")
        if m.get('month_measured') == 1:
            parts.append("逐月计量:有")
        if m.get('year_measured') == 1:
            parts.append("年度计量:有")
        if m.get('kitchen_water') == 1:
            parts.append("厨房用水单独计量:是")
        if m.get('year_water') == 1 and m.get('year_water_value'):
            parts.append(f"年度用水量:{m['year_water_value']}")
        if m.get('other_metering_scenario'):
            parts.append(f"其他场景:{m['other_metering_scenario']}")
        if m.get('other_situation'):
            parts.append(f"其他情况:{m['other_situation']}")
        lines.append(f"- **{year} 年**：{', '.join(parts)}")
    return "\n".join(lines)


# ============================================================
# Handlers
# ============================================================

def _handle_search_projects(args: dict, **kwargs):
    """按名称模糊搜索能源审计项目。"""
    if not _PG_AVAILABLE:
        return _pg_unavailable_result()
    keyword = args.get("keyword", "").strip()
    if not keyword:
        return tool_error("keyword 不能为空")
    try:
        with PgDataQuery() as db:
            rows = db.get_institution_project(audited_name=keyword)
        if not rows:
            return tool_result({"count": 0, "projects": [], "message": f"未找到匹配 '{keyword}' 的项目"})
        projects = [
            {
                "id": r["id"],
                "audited_name": r["audited_name"],
                "audit_year": r["audit_year"],
                "reference_year": r["reference_year"],
                "customer_id": r["customer_id"],
            }
            for r in rows[:20]
        ]
        lines = [f"找到 {len(projects)} 个匹配项目：\n"]
        for p in projects:
            lines.append(f"- {p['audited_name']}（ID: {p['id']}，审计年度：{p['audit_year'] or '-'}）")
        return "\n".join(lines)
    except Exception as e:
        return tool_error(f"查询失败：{e}")


def _handle_get_project(args: dict, **kwargs):
    """获取单个项目完整信息。"""
    if not _PG_AVAILABLE:
        return _pg_unavailable_result()
    project_name = args.get("project_name", "").strip()
    if not project_name:
        return tool_error("project_name 不能为空")
    try:
        result = collect_from_pg(project_name)
        if not result.get("project_id"):
            return tool_error(f"未找到项目：{project_name}")
        return _format_project_summary(result)
    except Exception as e:
        return tool_error(f"查询失败：{e}")


def _handle_get_equipment(args: dict, **kwargs):
    """获取项目设备清单。"""
    if not _PG_AVAILABLE:
        return _pg_unavailable_result()
    project_name = args.get("project_name", "").strip()
    category = args.get("category", "").strip() or None
    if not project_name:
        return tool_error("project_name 不能为空")
    try:
        with PgDataQuery() as db:
            proj = db.find_project_by_name(project_name)
            if not proj:
                return tool_error(f"未找到项目：{project_name}")
            equipment = db.get_formatted_equipment(
                customer_id=proj["customer_id"], category=category
            )
        if not equipment:
            return f"项目 **{project_name}** 暂未录入设备数据。"
        return _format_equipment_section(equipment, category=category)
    except Exception as e:
        return tool_error(f"查询失败：{e}")


def _handle_get_buildings(args: dict, **kwargs):
    """获取项目建筑信息。"""
    if not _PG_AVAILABLE:
        return _pg_unavailable_result()
    project_name = args.get("project_name", "").strip()
    if not project_name:
        return tool_error("project_name 不能为空")
    try:
        with PgDataQuery() as db:
            proj = db.find_project_by_name(project_name)
            if not proj:
                return tool_error(f"未找到项目：{project_name}")
            buildings = db.get_institution_build(customer_id=proj["customer_id"])
        return _format_buildings(buildings)
    except Exception as e:
        return tool_error(f"查询失败：{e}")


def _handle_get_energy(args: dict, **kwargs):
    """获取项目能耗数据。"""
    if not _PG_AVAILABLE:
        return _pg_unavailable_result()
    project_name = args.get("project_name", "").strip()
    year = args.get("year") or None
    if not project_name:
        return tool_error("project_name 不能为空")
    try:
        with PgDataQuery() as db:
            proj = db.find_project_by_name(project_name)
            if not proj:
                return tool_error(f"未找到项目：{project_name}")
            energy = db.get_institution_energy(customer_id=proj["customer_id"], year=year)
        return _format_energy(energy)
    except Exception as e:
        return tool_error(f"查询失败：{e}")


def _handle_get_energy_meter(args: dict, **kwargs):
    """获取项目用电/用水表具计量信息。"""
    if not _PG_AVAILABLE:
        return _pg_unavailable_result()
    project_name = args.get("project_name", "").strip()
    data_type = args.get("data_type")
    year = args.get("year") or None
    if not project_name:
        return tool_error("project_name 不能为空")
    try:
        with PgDataQuery() as db:
            proj = db.find_project_by_name(project_name)
            if not proj:
                return tool_error(f"未找到项目：{project_name}")
            if data_type is not None:
                data_type = int(data_type)
            if year is not None:
                year = int(year)
            meters = db.get_energy_meter(
                customer_id=proj["customer_id"],
                data_type=data_type,
                year=year,
            )
        return _format_energy_meter(meters)
    except Exception as e:
        return tool_error(f"查询失败：{e}")


# ============================================================
# Schemas
# ============================================================

ENERGY_AUDIT_SEARCH_PROJECTS_SCHEMA = {
    "name": "energy_audit_search_projects",
    "description": (
        "按名称模糊搜索能源审计项目。当用户提到的项目名称不确定、"
        "或需要确认系统中是否存在该项目时使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "项目关键词，例如'省立医院'。支持模糊匹配。",
            },
        },
        "required": ["keyword"],
    },
}

ENERGY_AUDIT_GET_PROJECT_SCHEMA = {
    "name": "energy_audit_get_project",
    "description": (
        "查询能源审计项目的完整信息，包括项目基本信息、建筑、能耗、设备、人员、计量等。"
        "当用户询问某个单位/项目的能源审计整体情况时使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "项目名称或被审计单位名称，例如'省立医院东院'。支持模糊匹配。",
            },
        },
        "required": ["project_name"],
    },
}

ENERGY_AUDIT_GET_EQUIPMENT_SCHEMA = {
    "name": "energy_audit_get_equipment",
    "description": (
        "查询指定能源审计项目的设备清单，包括空调、照明、办公、动力、卫生器具、"
        "生活热水、蒸汽、特殊设备等。当用户问'有哪些设备'时使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "项目名称或被审计单位名称，例如'省立医院东院'。支持模糊匹配。",
            },
            "category": {
                "type": "string",
                "description": (
                    "可选，按设备类别过滤。可选值：空调、照明、办公、动力、卫生器具、"
                    "生活热水、其他设备、特殊设备、蒸汽。不填则返回全部。"
                ),
            },
        },
        "required": ["project_name"],
    },
}

ENERGY_AUDIT_GET_BUILDINGS_SCHEMA = {
    "name": "energy_audit_get_buildings",
    "description": "查询指定能源审计项目的建筑信息。",
    "parameters": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "项目名称或被审计单位名称，例如'省立医院东院'。支持模糊匹配。",
            },
        },
        "required": ["project_name"],
    },
}

ENERGY_AUDIT_GET_ENERGY_SCHEMA = {
    "name": "energy_audit_get_energy",
    "description": "查询指定能源审计项目的能耗数据。",
    "parameters": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "项目名称或被审计单位名称，例如'省立医院东院'。支持模糊匹配。",
            },
            "year": {
                "type": "string",
                "description": "可选，指定年份，例如'2023'。不填则返回所有年度。",
            },
        },
        "required": ["project_name"],
    },
}

ENERGY_AUDIT_GET_ENERGY_METER_SCHEMA = {
    "name": "energy_audit_get_energy_meter",
    "description": (
        "查询指定能源审计项目的用电/用水计量表具信息，包括计量电表数量、分项计量、"
        "计量深度、逐月/年度计量、厨房用水单独计量等。当用户询问'计量表具'、'电表'、'水表'时使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "项目名称或被审计单位名称，例如'省立医院东院'。支持模糊匹配。",
            },
            "data_type": {
                "type": "integer",
                "description": "可选，1=电表，2=水表。不填则返回全部。",
            },
            "year": {
                "type": "string",
                "description": "可选，指定统计年份，例如'2024'。不填则返回所有年度。",
            },
        },
        "required": ["project_name"],
    },
}


# ============================================================
# Registration
# ============================================================

registry.register(
    name="energy_audit_search_projects",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_SEARCH_PROJECTS_SCHEMA,
    handler=_handle_search_projects,
    check_fn=_check_energy_audit_available,
    emoji="🏭",
)

registry.register(
    name="energy_audit_get_project",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_GET_PROJECT_SCHEMA,
    handler=_handle_get_project,
    check_fn=_check_energy_audit_available,
    emoji="🏭",
)

registry.register(
    name="energy_audit_get_equipment",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_GET_EQUIPMENT_SCHEMA,
    handler=_handle_get_equipment,
    check_fn=_check_energy_audit_available,
    emoji="🏭",
)

registry.register(
    name="energy_audit_get_buildings",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_GET_BUILDINGS_SCHEMA,
    handler=_handle_get_buildings,
    check_fn=_check_energy_audit_available,
    emoji="🏭",
)

registry.register(
    name="energy_audit_get_energy",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_GET_ENERGY_SCHEMA,
    handler=_handle_get_energy,
    check_fn=_check_energy_audit_available,
    emoji="🏭",
)

registry.register(
    name="energy_audit_get_energy_meter",
    toolset="energy_audit",
    schema=ENERGY_AUDIT_GET_ENERGY_METER_SCHEMA,
    handler=_handle_get_energy_meter,
    check_fn=_check_energy_audit_available,
    emoji="🏭",
)


# ============================================================
# REST API handlers (web_server.py /api/energy-audit/*)
# ============================================================
# These are separate from the tool handlers above on purpose: tools return JSON
# *strings* for the LLM, while REST endpoints return plain dicts for FastAPI.
# The generation pipeline is CPU-heavy, so web_server wraps these in
# run_in_threadpool.

def rest_search_energy_audit_projects(keyword: str) -> dict:
    """按名称模糊搜索能源审计项目（REST 版本，返回 dict）。"""
    if not _PG_AVAILABLE:
        return {"error": "能源审计数据库工具当前不可用", "message": _PG_IMPORT_ERROR or "PG 数据库未配置或无法连接"}

    keyword = (keyword or "").strip()
    if not keyword:
        return {"error": "keyword 不能为空", "message": "请提供项目关键词"}

    try:
        with PgDataQuery() as db:
            rows = db.get_institution_project(audited_name=keyword)
    except Exception as e:
        return {"error": "查询失败", "message": str(e)}

    projects = [
        {
            "id": r["id"],
            "audited_name": r["audited_name"],
            "audit_year": r["audit_year"],
            "reference_year": r["reference_year"],
            "customer_id": r["customer_id"],
        }
        for r in rows[:20]
    ]
    return {"ok": True, "projects": projects}


def rest_generate_energy_audit_report(
    project_name: str,
    audit_type: str = "公共机构",
    output_dir: str = None,
    mode: str = "template",
    reference_dir: str = None,
) -> dict:
    """从 PG 取数生成能源审计报告 .docx（REST 版本，返回 dict）。

    mode=template：固定章节模板填数。
    mode=imitate：按类型从参考报告目录取同类报告仿写后生成 Word。
    """
    try:
        import docx  # noqa: F401
    except ImportError:
        return {
            "error": "缺少 python-docx",
            "message": "当前 Python 环境未安装 python-docx，无法生成 Word 报告。"
            "请在后端环境执行：uv pip install 'python-docx==1.2.0' "
            "或 uv sync --extra energy",
        }

    if (mode or "template").strip() == "imitate":
        try:
            from tools.energy_audit.imitate_pipeline import result_to_jsonable, run_imitate_report
        except ImportError as e:
            return {"error": "仿写流水线加载失败", "message": str(e)}
        try:
            result = run_imitate_report(
                project_name,
                audit_type=audit_type or "公共机构",
                output_dir=output_dir or "",
                reference_dir=reference_dir or "",
                refresh_from_pg=True,
            )
        except Exception as e:
            return {"error": "仿写生成失败", "message": str(e)}
        if not result.get("ok"):
            msg = result.get("error") or "仿写生成失败"
            return {"error": msg, "message": msg}
        payload = result_to_jsonable(result)
        payload["ok"] = True
        return payload

    if not _PG_AVAILABLE:
        return {"error": "能源审计数据库工具当前不可用", "message": _PG_IMPORT_ERROR or "PG 数据库未配置或无法连接"}

    project_name = (project_name or "").strip()
    if not project_name:
        return {"error": "project_name 不能为空", "message": "请提供单位/项目名称"}

    try:
        from tools.energy_audit.pg_collector import build_and_save_project
        from tools.energy_audit.report_generator import ReportGenerator
    except ImportError as e:
        return {"error": "能源审计报告工具加载失败", "message": str(e)}

    # 报告输出目录：优先调用方指定，其次 config.yaml 的 output.directory，最后回退 ./reports。
    default_dir = output_dir or "./reports"
    try:
        os.makedirs(default_dir, exist_ok=True)
    except OSError as e:
        return {"error": "无法创建输出目录", "message": str(e)}

    try:
        project = build_and_save_project(project_name)
    except Exception as e:
        return {"error": "从数据库取数失败", "message": f"{project_name}: {e}"}

    # build_and_save_project 内部会 save_project；项目未找到时返回空 AuditProject。
    if not project.base.unit_name:
        return {"error": "未找到项目", "message": f"数据库中不存在单位/项目：{project_name}"}

    output_path = os.path.join(default_dir, f"{project_name}能源审计报告.docx")
    try:
        gen = ReportGenerator(audit_type)
        gen.load_from_project(project)
        result_path = gen.generate_word(output_path)
    except Exception as e:
        return {"error": "报告生成失败", "message": str(e)}

    return {"ok": True, "file_path": result_path}
