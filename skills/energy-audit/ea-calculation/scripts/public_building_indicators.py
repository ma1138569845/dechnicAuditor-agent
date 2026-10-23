#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""浙江公共建筑指标计算（经 caliber_agent 公共建筑分支接入）

口径依据：
- DB33/T 736-2021（办公/场馆）
- DB33/T 760-2023（饭店）
- 浙江省用（取）水定额（2019）

设计原则：
- 不修改现有 tools/energy_audit/indicators.py（山东公共机构线）；
- 输入用普通 dict，便于后续从 data.json 适配；
- 定额值从 quota-values.json 读取，不在代码里硬编码。

用法：
    python public_building_indicators.py --self-test
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve()
DEFAULT_QUOTA_PATH = (
    HERE.parents[2]
    / "energy-audit-core"
    / "references"
    / "standards"
    / "zhejiang"
    / "quota-values.json"
)


def load_quota_values(path: str | Path | None = None) -> dict[str, Any]:
    quota_path = Path(path) if path else DEFAULT_QUOTA_PATH
    with quota_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _grade_three(value: float, tiers: list[float]) -> str:
    """736：tiers = [约束值, 基准值, 引导值]，越低越好。"""
    constraint, base, guide = tiers
    if value <= guide:
        return "低于引导值"
    if value <= base:
        return "低于基准值"
    if value <= constraint:
        return "低于约束值"
    return "高于约束值"


def _grade_two(value: float, tiers: list[float]) -> str:
    """用水定额：tiers = [通用值, 先进值]，越低越好。"""
    general, advanced = tiers
    if value <= advanced:
        return "低于先进值"
    if value <= general:
        return "低于通用值"
    return "高于通用值"


def _grade_760(value: float, tiers: list[float]) -> str:
    """760：tiers = [3级限额, 2级约束, 1级先进]，越低越好。"""
    level3, level2, level1 = tiers
    if value <= level1:
        return "低于1级（先进值）"
    if value <= level2:
        return "低于2级（约束值）"
    if value <= level3:
        return "低于3级（限额值）"
    return "高于3级（限额值）"


def _energy_kgce(year: dict[str, Any], coeff: dict[str, Any], *,
                 include_water: bool) -> float:
    energy = (
        _f(year.get("electricity_kwh")) * _f(coeff["electricity_kgce_per_kwh"])
        + _f(year.get("gas_m3")) * _f(coeff["gas_kgce_per_m3"])
        + _f(year.get("heat_gj")) * _f(coeff["heat_kgce_per_gj"])
        + _f(year.get("other_kgce"))
    )
    if include_water:
        energy += _f(year.get("water_t")) * _f(coeff["water_kgce_per_t"])
    return energy


def compute_office_or_venue(project: dict[str, Any], quota: dict[str, Any]) -> list[dict[str, Any]]:
    subtype = project.get("subtype", "office")
    if subtype not in ("office", "venue"):
        raise ValueError("subtype 必须是 office 或 venue")

    area = _f(project.get("area_m2"))
    people = _f(project.get("people"))
    if area <= 0 or people <= 0:
        raise ValueError("area_m2 与 people 必须大于 0")

    coeff = quota["coefficients"]
    if subtype == "office":
        level = project.get("level", "city")
        tables = quota["db33_t_736_2021"]["administrative"]
        if level not in ("province", "city", "county"):
            raise ValueError("level 必须是 province/city/county")
        dimension = level
    else:
        venue_type = project.get("venue_type", "culture")
        tables = quota["db33_t_736_2021"]["venue"]
        if venue_type not in ("science", "culture", "museum"):
            raise ValueError("venue_type 必须是 science/culture/museum")
        dimension = venue_type

    water_tiers = quota["water_2019"]["national_org"][
        "with_canteen" if project.get("has_canteen") else "without_canteen"
    ]
    pre2005 = bool(project.get("pre2005_no_central_ac"))
    correction = 1.2 if pre2005 else 1.0

    results: list[dict[str, Any]] = []
    for year in project.get("years", []):
        year_area = _f(year.get("area_m2"), area)
        year_people = _f(year.get("people"), people)
        if year_area <= 0 or year_people <= 0:
            raise ValueError(f"{year.get('year')} 年 area_m2 / people 必须大于 0")
        electricity = _f(year.get("electricity_kwh")) * correction
        energy = _energy_kgce(year, coeff, include_water=False) * correction
        water = _f(year.get("water_t"))
        water_missing = water <= 0

        values = {
            "unit_area_energy": energy / year_area,
            "unit_area_electricity": electricity / year_area,
            "per_capita_energy": energy / year_people,
            "per_capita_electricity": electricity / year_people,
            "unit_water": water / year_people,
        }
        results.append({
            "year": year.get("year"),
            "subtype": subtype,
            "dimension": dimension,
            "values": {k: round(v, 2) for k, v in values.items()},
            "quota": {
                "unit_area_energy": tables["unit_area_energy"][dimension],
                "unit_area_electricity": tables["unit_area_electricity"][dimension],
                "per_capita_energy": tables["per_capita_energy"][dimension],
                "per_capita_electricity": tables["per_capita_electricity"][dimension],
                "unit_water": water_tiers,
            },
            "grade": {
                "unit_area_energy": _grade_three(values["unit_area_energy"], tables["unit_area_energy"][dimension]),
                "unit_area_electricity": _grade_three(values["unit_area_electricity"], tables["unit_area_electricity"][dimension]),
                "per_capita_energy": _grade_three(values["per_capita_energy"], tables["per_capita_energy"][dimension]),
                "per_capita_electricity": _grade_three(values["per_capita_electricity"], tables["per_capita_electricity"][dimension]),
                "unit_water": ("无数据，不评价" if water_missing
                               else _grade_two(values["unit_water"], water_tiers)),
            },
            "notes": {
                "pre2005_correction": correction if pre2005 else None,
                "water_missing": water_missing,
                "energy_scope": "736：特殊/食堂/浴室/健身按可分项计量剔除；未分项计量需说明",
            },
        })
    return results


def compute_hotel(project: dict[str, Any], quota: dict[str, Any]) -> list[dict[str, Any]]:
    star = str(project.get("star", "3"))
    if star not in ("5", "4", "3"):
        raise ValueError("star 必须是 5/4/3（三星级及以下用 3）")
    water_category = str(project.get("water_category") or star)
    if water_category not in quota["water_2019"]["hotel"]:
        raise ValueError("water_category 必须是 5/4/3/2/1/below")

    area = _f(project.get("area_m2"))
    parking = _f(project.get("underground_parking_spaces"))
    area_mm = area - 30.0 * parking
    beds = _f(project.get("beds"))
    occupancy = _f(project.get("occupancy"), 1.0)
    if area_mm <= 0 or beds <= 0:
        raise ValueError("area_mm 与 beds 必须大于 0")

    coeff = quota["coefficients"]
    tiers = quota["db33_t_760_2023"]["unit_comparable_energy"][star]
    water_tiers = quota["water_2019"]["hotel"][water_category]

    corrections = dict(project.get("hotel_corrections") or {})
    if occupancy > 0 and "occupancy" not in corrections:
        # 出租率修正按 760 表2；这里只处理常见分段，精确值由调用方传入
        q = occupancy * 100 if occupancy <= 1 else occupancy
        if q <= 35:
            corrections["occupancy"] = 0.91
        elif q <= 45:
            corrections["occupancy"] = 0.94
        elif q <= 55:
            corrections["occupancy"] = 0.97
        elif q <= 65:
            corrections["occupancy"] = 1.00
        elif q <= 75:
            corrections["occupancy"] = 1.03
        elif q <= 85:
            corrections["occupancy"] = 1.06
        else:
            corrections["occupancy"] = 1.10

    factor = math.prod(_f(v, 1.0) for v in corrections.values()) or 1.0

    results: list[dict[str, Any]] = []
    for year in project.get("years", []):
        year_area = _f(year.get("area_m2"), area)
        year_parking = _f(year.get("underground_parking_spaces"), parking)
        year_area_mm = year_area - 30.0 * year_parking
        year_beds = _f(year.get("beds"), beds)
        year_occupancy = _f(year.get("occupancy"), occupancy)
        if year_area_mm <= 0 or year_beds <= 0:
            raise ValueError(f"{year.get('year')} 年 area_mm / beds 必须大于 0")

        year_corrections = dict(corrections)
        year_corrections.update(year.get("hotel_corrections") or {})
        year_factor = math.prod(_f(v, 1.0) for v in year_corrections.values()) or 1.0

        energy = _energy_kgce(year, coeff, include_water=True)
        unit_energy = energy / year_area_mm
        unit_comparable = unit_energy / year_factor
        water = _f(year.get("water_t"))
        water_missing = water <= 0
        water_per_bed = water / year_beds
        water_normalized = (
            water / (year_beds * year_occupancy)
            if year_occupancy > 0 else water_per_bed
        )

        results.append({
            "year": year.get("year"),
            "subtype": "hotel",
            "star": star,
            "values": {
                "unit_energy": round(unit_energy, 2),
                "unit_comparable_energy": round(unit_comparable, 2),
                "water_per_bed": round(water_per_bed, 2),
                "water_per_bed_normalized": round(water_normalized, 2),
            },
            "quota": {
                "unit_comparable_energy": tiers,
                "water": water_tiers,
            },
            "grade": {
                "unit_energy": "参考指标",
                "unit_comparable_energy": _grade_760(unit_comparable, tiers),
                "water": ("无数据，不评价" if water_missing
                          else _grade_two(water_normalized, water_tiers)),
            },
            "notes": {
                "area_mm": round(year_area_mm, 2),
                "correction_factors": year_corrections,
                "correction_product": round(year_factor, 4),
                "includes_new_water": True,
                "water_category": water_category,
                "water_missing": water_missing,
                "water_quota_basis": "定额×床位数×入住率；water_per_bed_normalized 用于对标",
            },
        })
    return results


def compute_project(project: dict[str, Any], quota: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    quota = quota or load_quota_values()
    subtype = project.get("subtype", "office")
    if subtype in ("office", "venue"):
        return compute_office_or_venue(project, quota)
    if subtype == "hotel":
        return compute_hotel(project, quota)
    raise ValueError("subtype 必须是 office/venue/hotel")


def _self_test() -> int:
    quota = load_quota_values()

    ab = {
        "subtype": "office",
        "level": "city",
        "area_m2": 95000,
        "people": 1238,
        "has_canteen": False,
        "pre2005_no_central_ac": False,
        "years": [
            {"year": 2022, "electricity_kwh": 3744994, "water_t": 6151},
        ],
    }
    ab_result = compute_project(ab, quota)[0]
    expected = {
        "unit_area_energy": 4.84,
        "unit_area_electricity": 39.42,
        "per_capita_energy": 371.78,
        "per_capita_electricity": 3025.04,
        "unit_water": 4.97,
    }
    for key, value in expected.items():
        got = ab_result["values"][key]
        assert abs(got - value) <= 0.011, f"AB {key}: {got} != {value}"

    hotel = {
        "subtype": "hotel",
        "star": "3",
        "area_m2": 19418.41,
        "beds": 119,
        "occupancy": 0.90,
        "hotel_corrections": {"occupancy": 1.10},
        "years": [
            {"year": 2023, "electricity_kwh": 899337, "water_t": 0},
            {"year": 2024, "electricity_kwh": 921039, "water_t": 7223},
        ],
    }
    hotel_results = compute_project(hotel, quota)
    assert abs(hotel_results[0]["values"]["unit_comparable_energy"] - 5.17) <= 0.011
    assert abs(hotel_results[1]["values"]["unit_comparable_energy"] - 5.39) <= 0.02
    assert abs(hotel_results[1]["values"]["water_per_bed"] - 60.70) <= 0.011

    print("self-test passed")
    print("AB 2022:", ab_result["values"], ab_result["grade"])
    print("Hotel 2023:", hotel_results[0]["values"], hotel_results[0]["grade"])
    print("Hotel 2024:", hotel_results[1]["values"], hotel_results[1]["grade"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="浙江公共建筑指标计算（独立模块）")
    parser.add_argument("--self-test", action="store_true", help="用样本数据自检")
    parser.add_argument("--quota", default="", help="quota-values.json 路径")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    print("请使用 --self-test，或从代码中调用 compute_project(project, quota)。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
