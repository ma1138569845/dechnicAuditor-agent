#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""山东公共建筑能耗限额指标计算（DB37/T 5076/5078/5079-2024）。

输入使用普通 dict，便于 caliber_agent 从 AuditProject 适配。所有定额值只从
`standards/shandong/public_building/quota-values.json` 读取。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve()
DEFAULT_QUOTA_PATH = (
    HERE.parents[2]
    / "energy-audit-core"
    / "references"
    / "standards"
    / "shandong"
    / "public_building"
    / "quota-values.json"
)

SHANDONG_CITIES = (
    "济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁",
    "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽",
)


def load_quota_values(path: str | Path | None = None) -> dict[str, Any]:
    quota_path = Path(path) if path else DEFAULT_QUOTA_PATH
    with quota_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _norm_city(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("市", "地区", "特别行政区"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def infer_city(project: dict[str, Any]) -> str:
    city = _norm_city(project.get("city"))
    if city in SHANDONG_CITIES:
        return city
    address = str(project.get("address") or "")
    for candidate in SHANDONG_CITIES:
        if candidate in address:
            return candidate
    raise ValueError("无法识别山东项目所在市；必须提供 city 或在 address 中写明地市")


def _grade_two(value: float, tiers: list[float]) -> str:
    constraint, advanced = tiers[0], tiers[1]
    if value <= advanced:
        return "达到先进值"
    if value <= constraint:
        return "符合约束值"
    return "超过约束值"


def _multiply_tiers(tiers: list[float], factor: float) -> list[float]:
    return [round(float(item) * factor, 4) for item in tiers]


def _correction_factor(project: dict[str, Any], year: dict[str, Any], subtype: str) -> tuple[float, dict[str, Any]]:
    merged = dict(project.get("correction") or {})
    merged.update(year.get("correction") or {})
    if subtype == "business_office":
        hours = _f(merged.get("annual_use_hours"))
        area_per_person = _f(merged.get("area_per_person"))
        if hours > 0 and area_per_person > 0:
            alpha1 = 0.3 + 0.7 * hours / 2900.0
            alpha2 = 0.7 + 0.3 * 10.0 / area_per_person
            return alpha1 * alpha2, {
                "alpha1_use_hours": round(alpha1, 6),
                "alpha2_people_density": round(alpha2, 6),
                "annual_use_hours": hours,
                "area_per_person": area_per_person,
            }
    elif subtype == "hotel":
        occupancy = _f(merged.get("occupancy"))
        room_ratio = _f(merged.get("room_area_ratio"))
        if occupancy > 0 and room_ratio > 0:
            alpha1 = 0.4 + 0.6 * occupancy / 0.5
            alpha2 = 0.5 + 0.5 * 0.7 / room_ratio
            return alpha1 * alpha2, {
                "alpha1_occupancy": round(alpha1, 6),
                "alpha2_room_area_ratio": round(alpha2, 6),
                "occupancy": occupancy,
                "room_area_ratio": room_ratio,
            }
    elif subtype == "hospital":
        equipment_hours = _f(merged.get("equipment_hours"))
        ac_days = _f(merged.get("ac_days"))
        outpatient_visits = _f(merged.get("outpatient_visits"))
        if equipment_hours > 0 and ac_days > 0 and outpatient_visits > 0:
            f = 0.42 + 0.204 * equipment_hours / 2555.0
            d = 0.147 + 0.173 * ac_days / 134.0
            e = 0.1 + 0.039 * outpatient_visits / 1_000_000.0
            return 1.0 + f * d * e, {
                "equipment_hours_factor": round(f, 6),
                "air_conditioning_days_factor": round(d, 6),
                "outpatient_visits_factor": round(e, 6),
                "equipment_hours": equipment_hours,
                "ac_days": ac_days,
                "outpatient_visits": outpatient_visits,
            }
    return 1.0, {"applied": False, "reason": "修正参数未完整提供"}


def _hospital_level(project: dict[str, Any]) -> str:
    """把显式医院等级映射到 DB37/T 5079 的四个子类。

    名称、单位全称和机构类别都不参与猜测。平台二级码 A/B/C 可映射为
    一级/二级/三级；其他字段则只接受标准中的中文规范值。
    """
    raw = str(
        project.get("hospital_level")
        or project.get("children_func")
        or ""
    ).strip().upper()
    if raw in ("A", "一级", "1", "ONE"):
        return "一级"
    if raw in ("B", "二级", "二级及以下", "2", "TWO"):
        level = "二级及以下"
    elif raw in ("C", "三级", "3", "THREE"):
        level = "三级"
    else:
        raise ValueError(
            "医院项目必须明确 hospital_level（三级/二级及以下；"
            "平台 children_func 可用 C/B），不得默认为二级"
        )

    specialty = str(
        project.get("hospital_specialty")
        or project.get("specific_type")
        or ""
    ).strip()
    if "专科" in specialty:
        kind = "专科"
    elif "综合" in specialty:
        kind = "综合"
    else:
        raise ValueError(
            "医院项目必须明确 hospital_specialty=综合/专科，"
            "不得根据单位名称猜测"
        )
    return f"{level}{kind}"


def _hotel_star(project: dict[str, Any]) -> str:
    raw = str(project.get("star") or "").strip()
    aliases = {
        "3": "3", "三星": "3", "三星级": "3",
        "4": "4", "四星": "4", "四星级": "4",
        "5": "5", "五星": "5", "五星级": "5",
    }
    star = aliases.get(raw)
    if not star:
        raise ValueError(
            "宾馆酒店项目必须明确 star=3/4/5（或三星/四星/五星级），"
            "不得默认为三星级"
        )
    return star


def compute_project(
    project: dict[str, Any],
    quota: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    quota = quota or load_quota_values()
    subtype = str(project.get("subtype") or "").strip()
    if subtype not in ("business_office", "hotel", "hospital"):
        raise ValueError(
            "山东公共建筑 subtype 必须是 business_office / hotel / hospital；"
            "office 含义不明确，机关办公不进入 DB37/T 5078 包"
        )

    city = infer_city(project)
    coeff = quota["coefficients"]
    if subtype == "business_office":
        block = quota["db37_t_5078_2024"]
        row = block["rows"][city]
        standard_id = "DB37/T 5078-2024"
        table = block["table"]
    elif subtype == "hotel":
        block = quota["db37_t_5076_2024"]
        star = _hotel_star(project)
        row = block["rows"][star][city]
        standard_id = "DB37/T 5076-2024"
        table = block["tables"][star]
    else:
        block = quota["db37_t_5079_2024"]
        level = _hospital_level(project)
        if level == "一级":
            raise ValueError("DB37/T 5079-2024 不适用于一级医院")
        if level not in block["rows"]:
            raise ValueError(f"无法映射医院等级：{level}")
        row = block["rows"][level][city]
        standard_id = "DB37/T 5079-2024"
        table = block["tables"][level]

    base_area = _f(project.get("area_m2"))
    base_heat_area = _f(project.get("heating_area_m2"), base_area)
    base_beds = _f(project.get("beds"))
    results: list[dict[str, Any]] = []

    for year in project.get("years") or []:
        area = _f(year.get("area_m2"), base_area)
        heat_area = _f(year.get("heating_area_m2"), base_heat_area or area)
        beds = _f(year.get("beds"), base_beds)
        if area <= 0:
            raise ValueError(f"{year.get('year')} 年建筑面积必须大于 0")
        if heat_area <= 0:
            raise ValueError(f"{year.get('year')} 年供暖面积必须大于 0")
        if subtype == "hospital" and beds <= 0:
            raise ValueError(f"{year.get('year')} 年医院床位数必须大于 0")

        heating_electricity = _f(
            year.get("heating_electricity_kwh"),
            _f(year.get("heating_energy_kwh")),
        )
        heating_gas = _f(year.get("heating_gas_m3"))
        heating_coal = _f(year.get("heating_raw_coal_kg"))
        heat_gj = _f(year.get("heating_heat_gj"), _f(year.get("heat_gj")))
        explicit_heating_kgce = _f(year.get("heating_energy_kgce"))
        heating_coefficient = _f(
            year.get(
                "heating_electricity_kgce_per_kwh",
                project.get("heating_electricity_kgce_per_kwh"),
            )
        )
        warnings: list[str] = []
        if explicit_heating_kgce > 0:
            heating_kgce = explicit_heating_kgce
        else:
            if heating_electricity > 0 and heating_coefficient <= 0:
                # 标准要求按当年全国平均火力发电标准煤耗折算，不能把
                # 0.1229 当量值冒充各年度等价值。
                raise ValueError(
                    f"{year.get('year')} 年存在供暖电耗 "
                    f"{heating_electricity:g} kWh，但未提供 "
                    "heating_electricity_kgce_per_kwh；"
                    "按 DB37/T 5076/5078/5079 应使用当年全国平均"
                    "火力发电标准煤耗，不得回退到固定 0.1229"
                )
            heating_kgce = (
                heating_electricity * heating_coefficient
                + heating_gas * _f(coeff["natural_gas_kgce_per_m3"])
                + heat_gj * _f(coeff["heat_kgce_per_gj"])
                + heating_coal * _f(coeff["raw_coal_kgce_per_kg"])
            )

        electricity = _f(year.get("electricity_kwh"))
        gas = _f(year.get("gas_m3"))
        nonheat_electricity = _f(
            year.get("non_heating_electricity_kwh"),
            max(0.0, electricity - heating_electricity),
        )
        nonheat_gas = _f(
            year.get("non_heating_gas_m3"),
            max(0.0, gas - heating_gas),
        )
        equivalent = (
            nonheat_electricity * _f(coeff["electricity_equivalent_kwh_per_kwh"], 1.0)
            + nonheat_gas * _f(coeff["natural_gas_equivalent_kwh_per_m3"])
            + _f(year.get("gasoline_kg")) * _f(coeff["gasoline_equivalent_kwh_per_kg"])
            + _f(year.get("diesel_kg")) * _f(coeff["diesel_equivalent_kwh_per_kg"])
            + _f(year.get("raw_coal_kg")) * _f(coeff["raw_coal_equivalent_kwh_per_kg"])
            + _f(year.get("cleaned_coal_kg")) * _f(coeff["cleaned_coal_equivalent_kwh_per_kg"])
            + _f(year.get("other_equivalent_electricity_kwh"))
        )

        e_a = heating_kgce / heat_area
        # 5079-2024 第 6.0.4 条的 F 明写为“医院建筑供暖面积”；
        # 5076/5078 的对应 F 为建筑面积。
        e_b_area = heat_area if subtype == "hospital" else area
        e_b = equivalent / e_b_area
        values: dict[str, float] = {
            "unit_area_heating_energy": round(e_a, 2),
            "unit_area_non_heating_electricity": round(e_b, 2),
        }
        if subtype == "hospital":
            values["per_bed_non_heating_electricity"] = round(
                equivalent / beds / 1000.0, 2
            )

        factor, correction = _correction_factor(project, year, subtype)
        corrected_e_a = _multiply_tiers(row[0:2], factor)
        corrected_e_b = _multiply_tiers(row[2:4], factor)
        quota_values: dict[str, list[float]] = {
            "unit_area_heating_energy": corrected_e_a,
            "unit_area_non_heating_electricity": corrected_e_b,
        }
        grades: dict[str, str] = {
            "unit_area_heating_energy": _grade_two(e_a, corrected_e_a),
            "unit_area_non_heating_electricity": _grade_two(e_b, corrected_e_b),
        }
        if subtype == "hospital":
            corrected_e_c = _multiply_tiers(row[4:6], factor)
            quota_values["per_bed_non_heating_electricity"] = corrected_e_c
            grades["per_bed_non_heating_electricity"] = _grade_two(
                values["per_bed_non_heating_electricity"], corrected_e_c
            )

        if not heating_gas and not heat_gj and heating_electricity <= 0:
            warnings.append("未提供可分项识别的供暖能源，eA 可能为 0")
        if factor == 1.0 and not correction.get("applied", False):
            warnings.append("修正参数不完整，本次按未修正限额对标")

        results.append({
            "year": year.get("year"),
            "subtype": subtype,
            "city": city,
            "standard_id": standard_id,
            "standard_table": table,
            "values": values,
            "quota": {
                "columns": ["约束值", "先进值"],
                "unit_area_heating_energy": corrected_e_a,
                "unit_area_non_heating_electricity": corrected_e_b,
                **(
                    {"per_bed_non_heating_electricity": corrected_e_c}
                    if subtype == "hospital" else {}
                ),
            },
            "quota_raw": {
                "unit_area_heating_energy": row[0:2],
                "unit_area_non_heating_electricity": row[2:4],
                **(
                    {"per_bed_non_heating_electricity": row[4:6]}
                    if subtype == "hospital" else {}
                ),
            },
            "grade": grades,
            "correction": {
                **correction,
                "factor": round(factor, 6),
                "applied": factor != 1.0 or correction.get("applied", False),
            },
            "notes": {
                "heating_energy_kgce": round(heating_kgce, 4),
                "non_heating_equivalent_kwh": round(equivalent, 4),
                "area_m2": round(area, 2),
                "heating_area_m2": round(heat_area, 2),
                "non_heating_denominator_m2": round(e_b_area, 2),
                "beds": round(beds, 2) if beds else None,
                "eC_unit": "10^3 kWh/(bed·a)" if subtype == "hospital" else None,
                "warnings": warnings,
            },
        })
    if not results:
        raise ValueError("没有年度能耗数据")
    return results


def _self_test() -> int:
    quota = load_quota_values()
    project = {
        "subtype": "business_office",
        "city": "日照",
        "area_m2": 10000,
        "heating_area_m2": 10000,
        "correction": {"annual_use_hours": 2900, "area_per_person": 10},
        "years": [{
            "year": 2024,
            "electricity_kwh": 600000,
            "gas_m3": 10000,
            "heating_gas_m3": 5000,
        }],
    }
    result = compute_project(project, quota)[0]
    assert result["quota_raw"]["unit_area_non_heating_electricity"] == [67, 44]
    assert abs(
        result["values"]["unit_area_non_heating_electricity"] - 63.5655
    ) < 0.01
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="山东公共建筑指标计算")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    print("请调用 compute_project(project, quota)，或使用 --self-test。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
