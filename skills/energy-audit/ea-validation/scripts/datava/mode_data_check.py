"""V1 DATA_CHECK — 采集后数据审查。

完整性检查 + 异常检测 + KG 因果诊断 + 月度/年度一致性 + 质量评级 + 自动分诊。

产出：
    validation.json                    兼容 data_analysis.load_analysis_result，附加审查信封
    validation_report.txt              可读报告
    diagnosis_chapter7_material.txt    第7章写作素材（有异常时）
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .common import (
    SEV_P0,
    SEV_P1,
    SEV_P2,
    Finding,
    ReviewResult,
    build_result,
    fmt_num,
    project_data_path,
    project_dir,
    read_json,
    safe_float,
    with_artifacts,
    write_json,
    write_text,
)

MODE = "DATA_CHECK"

# ── 质量等级 ────────────────────────────────────────────────────
GRADE_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "A": {"label": "✅ 优秀", "desc": "数据质量好，可直接进入指标计算"},
    "B": {"label": "⚠️ 可接受", "desc": "数据质量可接受，建议处理异常后再推进"},
    "C": {"label": "🔶 待提高", "desc": "缺失项较多或异常较多，建议补充数据后重验"},
    "D": {"label": "❌ 不满足", "desc": "缺少关键数据，不满足基本分析要求"},
}

# 缺失项 → 严重级别（关键词优先匹配，对应 data_check.check_completeness 的输出文案）
_MISSING_SEVERITY: Tuple[Tuple[str, str], ...] = (
    ("能耗数据", SEV_P0),
    ("被审计单位名称", SEV_P0),
    ("审计机构名称", SEV_P0),
    ("建筑面积", SEV_P0),
    ("用能人数", SEV_P0),
    ("建筑列表", SEV_P0),
    ("报告标题", SEV_P1),
    ("设备清单", SEV_P1),
    ("能源类型", SEV_P1),
    ("审计期", SEV_P1),
    ("基准期", SEV_P1),
    ("地址", SEV_P1),
    ("审计组人员", SEV_P1),   # 基本信息表必备：审计组名单缺失影响报告完整性（原 P2 升级）
    ("审计机构", SEV_P1),     # 能源审计机构信息表：名称/地址/负责人/联系方式
    ("配合人员", SEV_P1),     # 能源审计配合人员名单
    ("简称", SEV_P2),
)

# 异常严重级别 → Finding 级别
_ANOMALY_SEVERITY = {"critical": SEV_P1, "warning": SEV_P2, "info": SEV_P2}

MONTHLY_TOLERANCE_PCT = 5.0
DATA_ERROR_CHANGE_PCT = 200.0
ESSENTIAL_ENERGY = ("电", "水")


# ================================================================
#  AuditProject → report_data
# ================================================================

_ENERGY_LABELS: Tuple[Tuple[str, str], ...] = (
    ("electricity_kwh", "电力"),
    ("water_m3", "水"),
    ("natural_gas_m3", "天然气"),
    ("heating_energy_heat_gj", "热力"),
    ("petrol_kg", "汽油"),
    ("diesel_kg", "柴油"),
)

_MONTHLY_PAIRS: Tuple[Tuple[str, str, str], ...] = (
    ("monthly_electricity_kwh", "electricity_kwh", "电"),
    ("monthly_water_m3", "water_m3", "水"),
    ("monthly_natural_gas_m3", "natural_gas_m3", "天然气"),
)


def detect_energy_types(energy_yearly: Sequence[dict]) -> List[str]:
    """从年度能耗中检测实际使用的能源类型。"""
    return [
        label
        for key, label in _ENERGY_LABELS
        if any(safe_float(row.get(key)) > 0 for row in energy_yearly)
    ]


def project_to_report_data(project: Any) -> dict:
    """将 AuditProject 转为 data_check.check_completeness 所需的 report_data。"""
    from dataclasses import asdict

    raw = asdict(project)
    base = raw.get("base", {}) or {}
    energy_yearly = raw.get("energy_yearly", []) or []

    energy_by_year: Dict[int, dict] = {}
    for row in energy_yearly:
        year = int(safe_float(row.get("year")))
        fields = {key: row.get(key) for key, _ in _ENERGY_LABELS}
        fields.update({monthly: row.get(monthly) for monthly, _, _ in _MONTHLY_PAIRS})
        energy_by_year[year] = fields

    return {
        "cover": {"title": f"{base.get('unit_name', '')}能源审计报告" if base.get("unit_name") else ""},
        "audit_info_tables": {
            "institution": {
                "name": base.get("audit_org_name") or base.get("auditor") or "",
                "address": base.get("audit_org_address", ""),
                "contact": base.get("audit_org_contact", ""),
                "phone": base.get("audit_org_phone", ""),
            },
            "team_members": raw.get("audit_team") or [],
            "cooperation": raw.get("cooperation") or [],
        },
        "chapter1": {
            "audited_unit_short": base.get("unit_short", ""),
            "address": base.get("address", ""),
            "audit_period": base.get("audit_period", ""),
            "base_period": base.get("base_period", ""),
            "audit_time": (
                f"{base.get('audit_start', '')}—{base.get('audit_end', '')}"
                if base.get("audit_start") or base.get("audit_end")
                else ""
            ),
            "energy_types": ", ".join(detect_energy_types(energy_yearly)),
        },
        "chapter2": {
            "building_area": base.get("building_area", 0),
            "people_count": base.get("people_count", 0),
            "buildings": raw.get("buildings", []) or [],
        },
        "chapter5": {"energy_data": energy_by_year},
        "chapter6": {"_equipment": raw.get("equipment", []) or []},
    }


def extract_energy_yearly(project: Any) -> List[dict]:
    from dataclasses import asdict

    return asdict(project).get("energy_yearly", []) or []


# ================================================================
#  纯函数检查（可独立测试，不依赖 tools.energy_audit）
# ================================================================

def missing_severity(item: str) -> str:
    for keyword, severity in _MISSING_SEVERITY:
        if keyword in item:
            return severity
    return SEV_P1


def check_missing(missing: Sequence[str]) -> List[Finding]:
    """把 check_completeness 的缺失清单转为分级 Finding。"""
    findings: List[Finding] = []
    for item in missing:
        flat = " ".join(item.split())
        findings.append(
            Finding(
                code="V1.MISSING",
                category="完整性",
                severity=missing_severity(item),
                title=f"字段缺失：{flat.split('→')[-1].strip() or flat}",
                detail=flat,
                location=flat.split("→")[0].strip() if "→" in flat else "",
                suggestion="按 data.json 字段规范补录后重跑 DATA_CHECK",
            )
        )
    return findings


def check_monthly_consistency(
    energy_yearly: Sequence[dict],
    tolerance_pct: float = MONTHLY_TOLERANCE_PCT,
) -> List[Finding]:
    """月度明细与年度合计的一致性（月度不存在则跳过，不报缺失）。"""
    findings: List[Finding] = []
    for row in energy_yearly:
        year = int(safe_float(row.get("year")))
        for monthly_key, annual_key, label in _MONTHLY_PAIRS:
            monthly = row.get(monthly_key)
            if not monthly:
                continue
            values = [safe_float(v) for v in monthly]
            if len(values) != 12:
                findings.append(
                    Finding(
                        code="V1.MONTHLY.LENGTH",
                        category="数据一致性",
                        severity=SEV_P1,
                        title=f"{year}年{label}月度明细月份数不足",
                        location=f"{year}年 · {label}",
                        expected="12 个月",
                        actual=f"{len(values)} 个月",
                        suggestion="补齐 12 个月数据，否则逐月折线图与 2σ 离群检测失效",
                    )
                )
                continue
            annual = safe_float(row.get(annual_key))
            total = sum(values)
            if annual <= 0:
                findings.append(
                    Finding(
                        code="V1.MONTHLY.NO_ANNUAL",
                        category="数据一致性",
                        severity=SEV_P1,
                        title=f"{year}年{label}有月度明细但年度合计为零",
                        location=f"{year}年 · {label}",
                        expected=f"年度合计 ≈ {fmt_num(total)}",
                        actual="0",
                        suggestion="用月度合计回填年度值，或核实年度值来源",
                    )
                )
                continue
            deviation = abs(total - annual) / annual * 100.0
            if deviation > tolerance_pct:
                findings.append(
                    Finding(
                        code="V1.MONTHLY.SUM_MISMATCH",
                        category="数据一致性",
                        severity=SEV_P1 if deviation > tolerance_pct * 2 else SEV_P2,
                        title=f"{year}年{label}月度合计与年度值偏差 {deviation:.1f}%",
                        detail=f"月度合计 {fmt_num(total)}，年度值 {fmt_num(annual)}",
                        location=f"{year}年 · {label}",
                        expected=f"偏差 ≤ {tolerance_pct:.0f}%",
                        actual=f"{deviation:.1f}%",
                        suggestion="核对抄表口径（是否含分表/跨年结算），二者取其一为准",
                    )
                )
    return findings


# ================================================================
#  Config/Schema 校验（源自早期 config_validator.py，已适配 AuditProject）
# ================================================================
# 与 V1 check_completeness 的分工：
#   completeness 只管"缺不缺"（缺失 → P0/P1/P2）；
#   本检查管"格式/语义对不对"——类型、正数范围、机构类别、审计起止各自必填、
#   能耗年数建议。缺失类重复项（unit_name / 建筑面积 / 用能人数 / 能耗为空）
#   已由 completeness 覆盖，这里不重复报。

# base 上必须非空的字符串字段（completeness 未覆盖的）
_CONFIG_REQUIRED_STR = (
    ("institution_category", "机构类别"),
    ("audit_start", "审计起始"),
    ("audit_end", "审计结束"),
)

# base 上必须 > 0 的数值字段（负值 completeness 判不出，只能靠这里）
_CONFIG_POSITIVE_NUM = (
    ("building_area", "建筑面积", "m²"),
    ("people_count", "用能人数", "人"),
)

# base 上应为数值的字段
_CONFIG_NUMERIC_FIELDS = ("building_area", "people_count", "beds_count")

# base 上应为字符串的字段
_CONFIG_STRING_FIELDS = (
    "unit_name", "unit_short", "address", "unit_type", "institution_category",
    "specific_type", "contact_person", "contact_phone", "auditor", "report_date",
    "province", "audit_start", "audit_end", "data_start", "data_end",
    "admin_affiliation",
)

# 能耗建议年数（不足给出 P2 建议，不做硬性拦截）
_CONFIG_RECOMMENDED_YEARS = 3


def check_config_schema(project: Any) -> List[Finding]:
    """对 AuditProject 做 config_validator 式结构/类型/范围校验。

    入参 load_project 返回的 AuditProject（dataclass），经 asdict 读取 base 标量与
    energy_yearly。产出分级 Finding：类型错误/机构类别/审计起止 → P1，
    负数范围 → P0，能耗年数不足 3 年 → P2。
    """
    from dataclasses import asdict

    raw = asdict(project)
    base = raw.get("base", {}) or {}
    findings: List[Finding] = []

    # 1. 必填字符串（completeness 未覆盖的：机构类别 / 审计起止各自必填）
    for field, label in _CONFIG_REQUIRED_STR:
        value = base.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            findings.append(
                Finding(
                    code="V1.CONFIG.MISSING",
                    category="配置完整性",
                    severity=SEV_P1,
                    title=f"缺少必填字段：{label}",
                    location=f"base.{field}",
                    expected=f"{label}非空",
                    actual=f"{value!r}",
                    suggestion="在 data.json 的 base 中补录该字段后重跑 V1",
                )
            )

    # 2. 字符串字段类型
    for field in _CONFIG_STRING_FIELDS:
        value = base.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            findings.append(
                Finding(
                    code="V1.CONFIG.TYPE",
                    category="配置完整性",
                    severity=SEV_P1,
                    title=f"类型错误：{field} 应为字符串",
                    location=f"base.{field}",
                    expected="str",
                    actual=type(value).__name__,
                    suggestion="将 data.json 中该字段修正为字符串后重跑 V1",
                )
            )

    # 3. 数值字段类型（bool 是 int 子类，单独排除）
    for field in _CONFIG_NUMERIC_FIELDS:
        value = base.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            findings.append(
                Finding(
                    code="V1.CONFIG.TYPE",
                    category="配置完整性",
                    severity=SEV_P1,
                    title=f"类型错误：{field} 应为数值",
                    location=f"base.{field}",
                    expected="int/float",
                    actual=type(value).__name__,
                    suggestion="将 data.json 中该字段修正为数值后重跑 V1",
                )
            )

    # 4. 正数范围（负值 completeness 判不出）
    for field, label, unit in _CONFIG_POSITIVE_NUM:
        value = base.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value <= 0:
                findings.append(
                    Finding(
                        code="V1.CONFIG.RANGE",
                        category="配置完整性",
                        severity=SEV_P0,
                        title=f"{label}必须大于0",
                        location=f"base.{field}",
                        expected=f"> 0 {unit}",
                        actual=f"{value} {unit}",
                        suggestion="修正为正值后重跑 V1",
                    )
                )

    # 5. 能耗年数建议（仅在有数据时给出；为空由 completeness 报 P0）
    energy_yearly = raw.get("energy_yearly", []) or []
    years = [row.get("year") for row in energy_yearly if row.get("year")]
    if years and len(years) < _CONFIG_RECOMMENDED_YEARS:
        findings.append(
            Finding(
                code="V1.CONFIG.ENERGY_YEARS",
                category="配置完整性",
                severity=SEV_P2,
                title=f"能耗数据仅 {len(years)} 年，建议 3 年",
                location="energy_yearly",
                expected=f"{_CONFIG_RECOMMENDED_YEARS} 年（用于基准计算）",
                actual=f"{len(years)} 年",
                suggestion="补充历史年度数据后重跑 V1",
            )
        )

    return findings


def assess_data_quality(findings: Sequence[Finding], anomalies: Sequence[Any]) -> Tuple[str, str]:
    """综合完整性 Finding 与异常清单评定 A/B/C/D。"""
    p0 = sum(1 for f in findings if f.severity == SEV_P0)
    p1 = sum(1 for f in findings if f.severity == SEV_P1)
    criticals = sum(1 for a in anomalies if getattr(a, "severity", "") == "critical")

    if p0 > 0:
        grade = "D"
    elif p1 > 2 or criticals >= 3:
        grade = "C"
    elif p1 > 0 or criticals > 0 or len(anomalies) > 5:
        grade = "B"
    else:
        grade = "A"
    return grade, GRADE_DEFINITIONS[grade]["desc"]


# ================================================================
#  自动分诊（替代原交互式用户确认）
# ================================================================

def triage_anomaly(anomaly: Any) -> Any:
    """对单条异常自动定性，返回新对象。已有结论的原样返回。

    判定为数据错误（is_data_error=True）仅限物理上不可能或量级明显错误的情形；
    其余标记 confirmed=True，原因取 KG 推断，无推断时明确写"待现场核实"，不编造。
    """
    if anomaly.confirmed is not None or anomaly.is_data_error:
        return anomaly

    if safe_float(anomaly.value) < 0:
        return replace(
            anomaly,
            is_data_error=True,
            confirmed=False,
            reason="自动判定：数值为负，非物理可能值",
        )

    change = safe_float(anomaly.change_pct)
    if abs(change) >= DATA_ERROR_CHANGE_PCT:
        return replace(
            anomaly,
            is_data_error=True,
            confirmed=False,
            reason=f"自动判定：变化 {change:+.1f}% 超量级，疑似单位换算或录入错误",
        )

    if anomaly.category == "数据缺失" and anomaly.energy_type in ESSENTIAL_ENERGY:
        return replace(
            anomaly,
            is_data_error=True,
            confirmed=False,
            reason="自动判定：电/水为运行必需能源，某年为零视为采集缺失",
        )

    cause = (anomaly.diagnosis or {}).get("primary_cause") if anomaly.diagnosis else ""
    reason = (
        f"自动确认：KG 推断—{cause}"
        if cause
        else "自动确认：统计规则命中，具体原因待现场核实"
    )
    return replace(anomaly, confirmed=True, reason=reason)


def triage_all(result: Any) -> Any:
    """对 AnalysisResult 的全部异常自动分诊，返回新 AnalysisResult。"""
    return replace(result, anomalies=[triage_anomaly(a) for a in result.anomalies])


def anomalies_to_findings(anomalies: Sequence[Any]) -> List[Finding]:
    findings: List[Finding] = []
    for anomaly in anomalies:
        severity = (
            SEV_P1
            if anomaly.is_data_error
            else _ANOMALY_SEVERITY.get(anomaly.severity, SEV_P2)
        )
        diagnosis = anomaly.diagnosis or {}
        detail_parts = [f"系统: {anomaly.system or '未识别'}", f"定性: {anomaly.reason or '未定性'}"]
        if diagnosis.get("primary_cause"):
            detail_parts.append(
                f"KG: {diagnosis['primary_cause']}"
                f"（置信度 {diagnosis.get('confidence', '—')}）"
            )
        measures = diagnosis.get("measures") or []
        findings.append(
            Finding(
                code=f"V1.ANOMALY.{'DATA_ERROR' if anomaly.is_data_error else 'CONFIRMED'}",
                category=anomaly.category or "异常检测",
                severity=severity,
                title=anomaly.description,
                detail=" | ".join(detail_parts),
                location=f"{anomaly.year or '—'}年"
                + (f"{anomaly.month}月" if anomaly.month else ""),
                suggestion=(
                    "修正原始数据后重跑 DATA_CHECK"
                    if anomaly.is_data_error
                    else (measures[0].get("label", "") if measures else "现场核实后写入第7章")
                ),
            )
        )
    return findings


# ================================================================
#  主流程
# ================================================================

def run(
    project: str,
    *,
    output_dir: Optional[str] = None,
    skip_completeness: bool = False,
    triage: bool = True,
) -> ReviewResult:
    try:
        from tools.energy_audit.data_analysis import (  # noqa: WPS433
            analyze_with_diagnosis,
            format_diagnosis_for_chapter7,
            save_analysis_result,
        )
        from tools.energy_audit.data_check import check_completeness
        from tools.energy_audit.project_data import load_project
    except ImportError as exc:
        # 三段式 reason：缺什么 + 由谁补+怎么补 + 补完回传什么
        # 供 editor（orchestrator）机读解析，转派对应上游工单
        reason = (
            f"V1 依赖待补: tools/energy_audit 导入失败 ({exc}); "
            f"由开发者恢复模块后重跑 V1; "
            f"补完后回传 依赖可用信号"
        )
        return build_result(MODE, project, [], error=reason)

    proj = load_project(project)
    if proj is None:
        # 三段式 reason：缺什么 + 由谁补+怎么补 + 补完回传什么
        # 供 editor（orchestrator）机读解析，转派 datacollection 补采工单
        reason = (
            f"V1 输入待补: 项目 '{project}' 的 data.json 不存在; "
            f"由 datacollection 通过 pg_collector 反查单位名后采集数据; "
            f"补完后回传 {project_data_path(project)} 路径"
        )
        return build_result(MODE, project, [], error=reason)

    energy_yearly = extract_energy_yearly(proj)
    findings: List[Finding] = []

    missing: List[str] = []
    if not skip_completeness:
        _, missing = check_completeness(project_to_report_data(proj))
        findings += check_missing(missing)

    findings += check_monthly_consistency(energy_yearly)
    findings += check_config_schema(proj)

    analysis = analyze_with_diagnosis(energy_yearly, project)
    if triage:
        analysis = triage_all(analysis)
    findings += anomalies_to_findings(analysis.anomalies)

    grade, grade_desc = assess_data_quality(findings, analysis.anomalies)

    result = build_result(
        MODE,
        project,
        findings,
        inputs={
            "buildings": len(proj.buildings),
            "energy_years": len(proj.energy_yearly),
            "equipment": len(proj.equipment),
        },
        extra={
            "grade": grade,
            "grade_desc": grade_desc,
            "grade_label": GRADE_DEFINITIONS[grade]["label"],
            "missing_count": len(missing),
            "anomaly_count": len(analysis.anomalies),
            "diagnosed_count": analysis.diagnosed_count,
            "data_error_count": analysis.error_count,
            "years": analysis.years,
            "energy_types": detect_energy_types(energy_yearly),
        },
    )
    # ── 落盘：validation.json 保持 load_analysis_result 兼容 ──
    save_dir = project_dir(project, output_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    validation_path = save_dir / "validation.json"
    save_analysis_result(analysis, str(validation_path))
    compat = read_json(validation_path) or {}

    artifacts = {"validation.json": str(validation_path)}
    if analysis.anomalies:
        artifacts["diagnosis_chapter7_material.txt"] = write_text(
            save_dir / "diagnosis_chapter7_material.txt",
            format_diagnosis_for_chapter7(analysis),
        )

    result = with_artifacts(result, artifacts)
    result = with_artifacts(
        result,
        {
            "validation_report.txt": write_text(
                save_dir / "validation_report.txt", result.render_text()
            )
        },
    )
    write_json(validation_path, {**compat, "review": result.to_dict()})
    return result
