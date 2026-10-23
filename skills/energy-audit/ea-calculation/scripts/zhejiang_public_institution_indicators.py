#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""浙江公共机构能耗定额指标计算。

适用范围：
- DB33/T 736-2021：行政机关、场馆；
- DB33/T 737-2021：普通高等院校；
- DB33/T 738-2021：二级及以上医疗机构。

736 的数值只从浙江公共建筑共享包读取，避免同一标准出现两份定额表。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve()
STANDARDS_DIR = (
    HERE.parents[2]
    / "energy-audit-core"
    / "references"
    / "standards"
    / "zhejiang"
)
DEFAULT_QUOTA_PATH = STANDARDS_DIR / "public_institution" / "quota-values.json"
SHARED_736_PATH = STANDARDS_DIR / "quota-values.json"


def load_quota_values(path: str | Path | None = None) -> dict[str, Any]:
    quota_path = Path(path) if path else DEFAULT_QUOTA_PATH
    with quota_path.open(encoding="utf-8") as fh:
        institution = json.load(fh)
    with SHARED_736_PATH.open(encoding="utf-8") as fh:
        shared = json.load(fh)
    institution["db33_t_736_2021"] = shared["db33_t_736_2021"]
    institution["_shared_736_meta"] = shared.get("meta") or {}
    return institution


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _grade(value: float, tiers: list[float]) -> str:
    constraint, base, guide = tiers
    if value <= guide:
        return "低于引导值"
    if value <= base:
        return "低于基准值"
    if value <= constraint:
        return "低于约束值"
    return "高于约束值"


def _energy_kgce(year: dict[str, Any], coeff: dict[str, Any]) -> float:
    return (
        _f(year.get("electricity_kwh")) * _f(coeff["electricity_kgce_per_kwh"])
        + _f(year.get("gas_m3")) * _f(coeff["natural_gas_kgce_per_m3"])
        + _f(year.get("heat_gj")) * _f(coeff["heat_kgce_per_gj"])
        + _f(year.get("lpg_kg")) * _f(coeff["lpg_kgce_per_kg"])
        + _f(year.get("gasoline_kg")) * _f(coeff["gasoline_kgce_per_kg"])
        + _f(year.get("diesel_kg")) * _f(coeff["diesel_kgce_per_kg"])
        + _f(year.get("fuel_oil_kg")) * _f(coeff["fuel_oil_kgce_per_kg"])
        + _f(year.get("raw_coal_kg")) * _f(coeff["raw_coal_kgce_per_kg"])
        + _f(year.get("other_kgce"))
    )


def _medical_level(project: dict[str, Any]) -> str:
    raw = str(
        project.get("hospital_level")
        or project.get("children_func")
        or ""
    ).strip().upper()
    if raw in ("A", "一级", "1", "ONE"):
        raise ValueError("DB33/T 738-2021 仅适用于二级及以上医疗机构")
    if raw in ("C", "三级", "3", "THREE"):
        return "三级"
    if raw in ("B", "二级", "2", "TWO"):
        return "二级"
    raise ValueError(
        "医疗机构必须通过 hospital_level 或平台 children_func 明确二级/三级；"
        "不得根据单位名称猜测"
    )


def _require_regular_university(project: dict[str, Any]) -> None:
    """DB33/T 737 只覆盖普通高等院校，拒绝成人高校和自考高校。"""
    kind = str(
        project.get("university_type")
        or project.get("higher_education_type")
        or project.get("specific_type")
        or ""
    ).strip()
    if bool(project.get("is_adult_education")) or any(
        token in kind for token in ("成人", "自考")
    ):
        raise ValueError(
            "DB33/T 737-2021 仅适用于普通高等院校；"
            "成人高校、自考高校不得套用"
        )


def _subject(project: dict[str, Any]) -> tuple[str, str, str]:
    subtype = str(project.get("subtype") or "").strip().lower()
    if subtype in ("agency", "government", "administrative"):
        return "agency", "DB33/T 736-2021", "表1、表3"
    if subtype == "venue":
        return "venue", "DB33/T 736-2021", "表2、表4"
    if subtype in ("university", "higher_education", "college"):
        return "university", "DB33/T 737-2021", "表1、表2"
    if subtype in ("hospital", "medical"):
        return "hospital", "DB33/T 738-2021", "表1、表2"
    raise ValueError(
        "浙江公共机构 subtype 仅支持 agency / venue / university / hospital"
    )


def _quota_set(
    kind: str,
    project: dict[str, Any],
    quota: dict[str, Any],
) -> tuple[dict[str, list[float]], str]:
    if kind == "agency":
        level = str(project.get("agency_level") or project.get("level") or "").strip()
        if level not in ("province", "city", "county"):
            raise ValueError("行政机关必须明确 agency_level=province/city/county")
        table = quota["db33_t_736_2021"]["administrative"]
        return {
            "unit_area_energy": table["unit_area_energy"][level],
            "per_capita_energy": table["per_capita_energy"][level],
            "unit_area_electricity": table["unit_area_electricity"][level],
            "per_capita_electricity": table["per_capita_electricity"][level],
            "eeue": table["eeue"],
        }, level
    if kind == "venue":
        venue_type = str(project.get("venue_type") or "").strip()
        if venue_type not in ("science", "culture", "museum"):
            raise ValueError("场馆必须明确 venue_type=science/culture/museum")
        table = quota["db33_t_736_2021"]["venue"]
        return {
            "unit_area_energy": table["unit_area_energy"][venue_type],
            "per_capita_energy": table["per_capita_energy"][venue_type],
            "unit_area_electricity": table["unit_area_electricity"][venue_type],
            "per_capita_electricity": table["per_capita_electricity"][venue_type],
            "eeue": table["eeue"],
        }, venue_type
    if kind == "university":
        _require_regular_university(project)
        table = quota["db33_t_737_2021"]
        return {
            "unit_area_energy": table["primary"]["unit_area_energy"],
            "per_capita_energy": table["primary"]["per_capita_energy"],
            "unit_area_electricity": table["reference"]["unit_area_electricity"],
            "per_capita_electricity": table["reference"]["per_capita_electricity"],
            "eeue": table["reference"]["eeue"],
        }, "普通高等院校"
    level = _medical_level(project)
    table = quota["db33_t_738_2021"]
    return {
        "unit_area_energy": table["primary"]["unit_area_energy"][level],
        "per_capita_energy": table["primary"]["per_capita_energy"][level],
        "unit_area_electricity": table["reference"]["unit_area_electricity"][level],
        "eeue": table["reference"]["eeue"],
    }, level


def _medical_correction(project: dict[str, Any], year: dict[str, Any]) -> dict[str, Any]:
    visits = _f(year.get("outpatient_visits"), _f(project.get("outpatient_visits")))
    open_beds = _f(year.get("open_beds"), _f(year.get("beds"), _f(project.get("open_beds"), _f(project.get("beds")))))
    alpha1 = 1.0
    alpha2 = 1.0
    if visits > 3_000_000:
        alpha1 = 1.2
    elif visits > 2_000_000:
        alpha1 = 1.15
    if open_beds > 1000:
        alpha2 = 1.2
    elif open_beds > 800:
        alpha2 = 1.15
    return {
        "outpatient_visits": visits or None,
        "open_beds": open_beds or None,
        "alpha1_outpatient": alpha1,
        "alpha2_beds": alpha2,
        "product": round(alpha1 * alpha2, 6),
    }


def compute_project(
    project: dict[str, Any],
    quota: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    quota = quota or load_quota_values()
    kind, standard_id, standard_table = _subject(project)
    tiers, dimension = _quota_set(kind, project, quota)
    coeff = quota["coefficients"]
    area = _f(project.get("area_m2"))
    people = _f(project.get("people"))
    if area <= 0 or people <= 0:
        raise ValueError("area_m2 与 people 必须大于 0")

    results: list[dict[str, Any]] = []
    for year in project.get("years") or []:
        year_area = _f(year.get("area_m2"), area)
        year_people = _f(year.get("people"), people)
        if year_area <= 0 or year_people <= 0:
            raise ValueError(f"{year.get('year')} 年面积和用能人数必须大于 0")
        correction = 1.0
        if kind in ("agency", "venue") and bool(
            year.get("pre2005_no_central_ac", project.get("pre2005_no_central_ac"))
        ):
            correction = 1.2

        energy = _energy_kgce(year, coeff) * correction
        electricity = _f(year.get("electricity_kwh")) * correction
        unit_area_energy = energy / year_area
        values: dict[str, float] = {
            "unit_area_energy": round(unit_area_energy, 2),
            "per_capita_energy": round(energy / year_people, 2),
            "unit_area_electricity": round(electricity / year_area, 2),
        }
        quota_out: dict[str, list[float]] = {
            "unit_area_energy": tiers["unit_area_energy"],
            "per_capita_energy": tiers["per_capita_energy"],
            "unit_area_electricity": tiers["unit_area_electricity"],
        }
        grades: dict[str, str] = {
            key: _grade(values[key], quota_out[key])
            for key in ("unit_area_energy", "per_capita_energy", "unit_area_electricity")
        }
        notes: dict[str, Any] = {
            "pre2005_correction": correction if correction != 1.0 else None,
            "kind": kind,
            "dimension": dimension,
        }

        if "per_capita_electricity" in tiers:
            values["per_capita_electricity"] = round(electricity / year_people, 2)
            quota_out["per_capita_electricity"] = tiers["per_capita_electricity"]
            grades["per_capita_electricity"] = _grade(
                values["per_capita_electricity"],
                tiers["per_capita_electricity"],
            )

        if kind == "hospital":
            medical_correction = _medical_correction(project, year)
            divisor = medical_correction["product"] or 1.0
            comparable = unit_area_energy / divisor
            values["comparable_unit_area_energy"] = round(comparable, 2)
            grades["comparable_unit_area_energy"] = _grade(
                comparable, tiers["unit_area_energy"]
            )
            notes["medical_correction"] = medical_correction

        data_center_kwh = _f(year.get("data_center_electricity_kwh"))
        it_equipment_kwh = _f(year.get("it_equipment_electricity_kwh"))
        if data_center_kwh > 0 and it_equipment_kwh > 0:
            eeue = data_center_kwh / it_equipment_kwh
            values["eeue"] = round(eeue, 2)
            quota_out["eeue"] = tiers["eeue"]
            grades["eeue"] = _grade(eeue, tiers["eeue"])
        else:
            notes["eeue"] = "无数据中心总电量与 IT 设备电量分项，不评价"

        water = _f(year.get("water_t"))
        if water > 0:
            values["unit_water"] = round(water / year_people, 2)
            water_key = "with_canteen" if project.get("has_canteen") else "without_canteen"
            water_tiers = quota["water_2019"]["national_org"][water_key]
            quota_out["unit_water"] = water_tiers
            grades["unit_water"] = (
                "低于先进值"
                if values["unit_water"] <= water_tiers[1]
                else "低于通用值"
                if values["unit_water"] <= water_tiers[0]
                else "高于通用值"
            )

        results.append({
            "year": year.get("year"),
            "subtype": kind,
            "standard_id": standard_id,
            "standard_table": standard_table,
            "values": values,
            "quota": quota_out,
            "grade": grades,
            "notes": notes,
        })
    if not results:
        raise ValueError("没有年度能耗数据")
    return results


def _self_test() -> int:
    quota = load_quota_values()
    project = {
        "subtype": "university",
        "area_m2": 100000,
        "people": 20000,
        "years": [{
            "year": 2024,
            "electricity_kwh": 3_000_000,
            "gas_m3": 100_000,
        }],
    }
    result = compute_project(project, quota)[0]
    assert result["quota"]["unit_area_energy"] == [7.0, 4.5, 2.5]
    assert abs(result["values"]["unit_area_energy"] - 4.9013) < 0.01
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="浙江公共机构指标计算")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    print("请调用 compute_project(project, quota)，或使用 --self-test。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
