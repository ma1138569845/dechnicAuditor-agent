"""被审计单位类型码与平台字典的代码侧镜像。

平台字段 ``customer_func`` / ``children_func`` 本身不区分报告族，同一个
字母在不同字典中含义不同。本模块先按 ``unit_type + province`` 选择命名
空间，再把平台码解析成计算侧可消费的规范字段。

取水口径记要（2026-09-29 用户定，决策 7 选项 C）：
  ``A 政务服务中心`` 的取水指标走机关人均口径（4452 表2“机关”行，行业代码
  S91～S96、T97；先进值 10 / 通用值 25 m³/(人·a)），不再使用面积口径。
  能源指标仍按 ``DB37/T 3781-2019``。平台改字典后必须运行
  ``python -m tools.energy_audit.dept_dict --check-db`` 复核。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


class DictionaryCodeError(ValueError):
    """平台码存在，但无法在选定字典中解释。"""


DEPT_TYPE: Dict[str, str] = {
    "A": "政务服务中心",
    "B": "场馆机构",
    "C": "医疗机构",
    "D": "党政机关",
    "E": "教育机构",
}

DEPT_TO_INSTITUTION_TYPE: Dict[str, str] = {
    "A": "service",
    "B": "venue",
    "C": "medical",
    "D": "government",
    "E": "education",
}

INSTITUTION_TYPE_TO_UNIT_FUNC: Dict[str, str] = {
    value: key for key, value in DEPT_TO_INSTITUTION_TYPE.items()
}

CATEGORY_TO_UNIT_FUNC: Dict[str, str] = {
    "政务服务中心": "A",
    "场馆机构": "B",
    "体育": "B",
    "医疗机构": "C",
    "医疗": "C",
    "党政机关": "D",
    "教育": "E",
    "教育机构": "E",
}

CHILDREN_FUNC: Dict[str, Dict[str, str]] = {
    "A": {"A": "市级及以上", "B": "市级以下"},
    "B": {
        "A": "图书馆",
        "B": "博物馆",
        "C": "剧院",
        "D": "体育馆",
        "E": "科技馆",
    },
    "C": {"A": "一级", "B": "二级", "C": "三级"},
    "D": {"A": "省级", "B": "市级", "C": "市级以下"},
    "E": {
        "A": "本科及以上",
        "B": "专科",
        "C": "普通非寄宿制",
        "D": "普通寄宿制",
        "E": "职业学校",
        "F": "初等教育",
        "G": "学前教育",
        "H": "其他教育",
    },
}


LIMIT_TYPE: Dict[str, str] = {
    "unit_area_non_heating": "A",
    "unit_area_heating": "B",
    "per_capita_energy": "C",
    "unit_area_elec": "D",
    "eue": "E",
    "water": "F",
    "water_per_person": "F",
    "water_per_bed_day": "F",
}

HEAT_TYPE: Dict[str, str] = {
    "市政集中供暖（按热计量）": "A",
    "市政集中供暖": "A",
    "燃煤自供暖": "A",
    "空调供暖": "B",
    "燃气（油）供暖": "C",
    "燃气供暖": "C",
}

AREA_GRADE: Dict[str, str] = {
    "省级": "A",
    "市级": "B",
    "区县级": "C",
    "区、县级": "C",
    "区县": "C",
}


DICTIONARIES: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("公共机构", "默认"): {
        "dictionary_type": "client_dept_type",
        "labels": DEPT_TYPE,
        "children": CHILDREN_FUNC,
        "family": "public_institution",
    },
    ("公共机构", "浙江"): {
        "dictionary_type": "zj_client_dept_type",
        "labels": {
            "zj_gov": "行政机关",
            "venue": "场馆",
            "zj_college": "普通高校",
            "zj_medical": "医疗机构",
        },
        "children": {
            "zj_gov": {
                "zj_gov_province": "省级",
                "zj_gov_city": "市级",
                "zj_gov_county": "县级及以下",
            },
            "venue": {
                "venue_science": "科技馆",
                "venue_culture": "文化馆",
                "venue_museum": "博物馆",
            },
            "zj_college": {},
            "zj_medical": {
                "zj_medical_3": "三级",
                "zj_medical_2": "二级",
            },
        },
        "child_dictionary_types": {
            "zj_gov": "zj_client_dept_type_zj_gov",
            "venue": "zj_client_dept_type_venue",
            "zj_medical": "zj_client_dept_type_zj_medical",
        },
        "family": "public_institution",
    },
    ("公共建筑", "浙江"): {
        "dictionary_type": "zj_public_build_type",
        "labels": {"zj_hotel": "旅游饭店"},
        "children": {
            "zj_hotel": {
                "zj_hotel_5": "五星级",
                "zj_hotel_4": "四星级",
                "zj_hotel_3": "三星级",
            }
        },
        "child_dictionary_types": {
            "zj_hotel": "zj_public_build_type_zj_hotel",
        },
        "family": "public_building",
    },
    ("公共建筑", "默认"): {
        "dictionary_type": "public_build_type",
        "labels": {
            "A": "宾馆酒店",
            "B": "机关办公",
            "C": "商务办公",
            "D": "医院",
        },
        "children": {
            "A": {"A1": "五星级", "A2": "四星级", "A3": "三星级"},
            "B": {},
            "C": {},
            "D": {
                "D1": "三级综合医院",
                "D2": "三级专科医院",
                "D3": "二级及以下综合医院",
                "D4": "二级及以下专科医院",
            },
        },
        "child_dictionary_types": {
            "A": "public_build_type_A",
            "D": "public_build_type_D",
        },
        "family": "public_building",
    },
}


def _code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("zj_", "venue_")):
        return lowered
    if lowered == "venue":
        return lowered
    return text.upper()


def _registry_key(unit_type: str, province: str) -> Tuple[str, str]:
    unit_type = str(unit_type or "").strip()
    province = str(province or "").strip()
    if unit_type == "公共建筑":
        if not province:
            raise DictionaryCodeError(
                "公共建筑缺少 province，无法选择省级公共建筑字典；请补采行政区划"
            )
        return ("公共建筑", "浙江" if "浙江" in province else "默认")
    if unit_type == "公共机构" and "浙江" in province:
        return ("公共机构", "浙江")
    return ("公共机构", "默认")


def expected_dictionary_rows() -> Dict[str, Dict[str, str]]:
    """返回需要与 system_dict_data 比对的主表及二级表。"""
    rows: Dict[str, Dict[str, str]] = {}
    for spec in DICTIONARIES.values():
        main_type = str(spec["dictionary_type"])
        rows[main_type] = dict(spec["labels"])
        for main_code, child_rows in spec["children"].items():
            child_type = spec.get("child_dictionary_types", {}).get(main_code)
            if child_type:
                rows[str(child_type)] = dict(child_rows)

    # 山东公共机构二级表的命名与其余默认表一致。
    for main_code, child_rows in CHILDREN_FUNC.items():
        rows[f"client_dept_type_{main_code}"] = dict(child_rows)
    return rows


def _base_result(
    *,
    unit_type: str,
    province: str,
    family: str,
    dictionary_type: str,
    customer_func: str,
    children_func: str,
) -> Dict[str, str]:
    return {
        "unit_type": unit_type,
        "region": province,
        "customer_func": customer_func,
        "children_func": children_func,
        "category_label": "",
        "children_label": "",
        "family": family,
        "public_building_subtype": "",
        "star": "",
        "agency_level": "",
        "venue_type": "",
        "hospital_level": "",
        "hospital_specialty": "",
        "dictionary_type": dictionary_type,
        "dictionary_label": dictionary_type,
    }


def _resolve_public_institution(
    customer_func: str,
    children_func: str,
    province: str,
    spec: Dict[str, Any],
) -> Dict[str, str]:
    labels = spec["labels"]
    error = DictionaryCodeError(
        f"平台单位类型码无法解释：customer_func={customer_func!r}, "
        f"children_func={children_func!r}, unit_type='公共机构', province={province!r}"
    )
    if not customer_func:
        return _base_result(
            unit_type="公共机构",
            province=province,
            family="public_institution",
            dictionary_type=str(spec["dictionary_type"]),
            customer_func="",
            children_func=children_func,
        )
    if customer_func not in labels:
        raise error

    child_rows = spec["children"].get(customer_func, {})
    if children_func and children_func not in child_rows:
        raise error

    result = _base_result(
        unit_type="公共机构",
        province=province,
        family="public_institution",
        dictionary_type=str(spec["dictionary_type"]),
        customer_func=customer_func,
        children_func=children_func,
    )
    result["category_label"] = labels[customer_func]
    result["children_label"] = child_rows.get(children_func, "")

    if customer_func == "zj_gov":
        result["agency_level"] = {
            "zj_gov_province": "province",
            "zj_gov_city": "city",
            "zj_gov_county": "county",
        }.get(children_func, "")
    elif customer_func == "venue":
        result["venue_type"] = {
            "venue_science": "science",
            "venue_culture": "culture",
            "venue_museum": "museum",
        }.get(children_func, "")
    elif customer_func == "zj_medical":
        result["hospital_level"] = {
            "zj_medical_3": "3",
            "zj_medical_2": "2",
        }.get(children_func, "")
    return result


def _resolve_public_building(
    customer_func: str,
    children_func: str,
    province: str,
    spec: Dict[str, Any],
) -> Dict[str, str]:
    labels = spec["labels"]
    dictionary_type = str(spec["dictionary_type"])
    if not customer_func:
        raise DictionaryCodeError(
            "公共建筑缺少 customer_func（一级类型码）；后续计算已停止，请补采平台类型"
        )
    if customer_func not in labels:
        raise DictionaryCodeError(
            f"平台公共建筑类型码无法解释：customer_func={customer_func!r}, "
            f"children_func={children_func!r}, province={province!r}, "
            f"dictionary_type={dictionary_type!r}"
        )

    child_rows = spec["children"].get(customer_func, {})
    if children_func and children_func not in child_rows:
        raise DictionaryCodeError(
            f"平台公共建筑二级码无法解释：customer_func={customer_func!r}, "
            f"children_func={children_func!r}, dictionary_type={dictionary_type!r}"
        )

    result = _base_result(
        unit_type="公共建筑",
        province=province,
        family="public_building",
        dictionary_type=dictionary_type,
        customer_func=customer_func,
        children_func=children_func,
    )
    result["category_label"] = labels[customer_func]
    result["children_label"] = child_rows.get(children_func, "")

    if dictionary_type == "zj_public_build_type":
        if customer_func != "zj_hotel":
            raise DictionaryCodeError(
                f"浙江公共建筑当前仅接入旅游饭店，收到 customer_func={customer_func!r}"
            )
        if not children_func:
            raise DictionaryCodeError(
                "浙江旅游饭店缺少星级码；必须提供 zj_hotel_3/4/5，禁止默认三星级"
            )
        result["public_building_subtype"] = "hotel"
        result["star"] = {
            "zj_hotel_5": "5",
            "zj_hotel_4": "4",
            "zj_hotel_3": "3",
        }[children_func]
        return result

    if customer_func == "A":
        if not children_func:
            raise DictionaryCodeError(
                "宾馆酒店缺少星级码；必须提供 A1/A2/A3，禁止默认三星级"
            )
        result["public_building_subtype"] = "hotel"
        result["star"] = {"A1": "5", "A2": "4", "A3": "3"}[children_func]
    elif customer_func == "B":
        if children_func:
            raise DictionaryCodeError("机关办公 B 不接受 children_func 二级码")
        result["public_building_subtype"] = "agency_office"
    elif customer_func == "C":
        if children_func:
            raise DictionaryCodeError("商务办公 C 不接受 children_func 二级码")
        result["public_building_subtype"] = "business_office"
    elif customer_func == "D":
        if not children_func:
            raise DictionaryCodeError(
                "医院缺少等级/专科类型码；必须提供 D1/D2/D3/D4"
            )
        result["public_building_subtype"] = "hospital"
        mapping = {
            "D1": ("3", "general"),
            "D2": ("3", "specialty"),
            "D3": ("<=2", "general"),
            "D4": ("<=2", "specialty"),
        }
        result["hospital_level"], result["hospital_specialty"] = mapping[children_func]
    return result


def resolve_unit_codes(
    customer_func: str,
    children_func: str,
    *,
    province: str = "",
    unit_type: str = "",
) -> Dict[str, str]:
    """按报告族选择字典并返回规范化类型结果。"""
    customer_code = _code(customer_func)
    child_code = _code(children_func)
    cleaned_province = str(province or "").strip()
    cleaned_unit_type = str(unit_type or "").strip()
    key = _registry_key(cleaned_unit_type, cleaned_province)
    spec = DICTIONARIES[key]
    if key[0] == "公共建筑":
        return _resolve_public_building(
            customer_code,
            child_code,
            cleaned_province,
            spec,
        )
    return _resolve_public_institution(
        customer_code,
        child_code,
        cleaned_province,
        spec,
    )


def children_label(unit_func: str, children_func: str) -> str:
    """旧公共机构二级码转中文标签。"""
    if not unit_func or not children_func:
        return ""
    return CHILDREN_FUNC.get(_code(unit_func), {}).get(_code(children_func), "")


def label_to_code(unit_func: str, label: str) -> str:
    want = str(label or "").strip()
    if not want:
        return ""
    for code, value in CHILDREN_FUNC.get(_code(unit_func), {}).items():
        if value == want:
            return code
    return ""


def institution_type_of(unit_func: str) -> str:
    return DEPT_TO_INSTITUTION_TYPE.get(_code(unit_func), "")


def category_of(unit_func: str) -> str:
    label = DEPT_TYPE.get(_code(unit_func), "")
    return "教育" if label == "教育机构" else label


def classify_from_codes(
    customer_func: str,
    children_func: str,
    *,
    province: str = "",
    unit_type: str = "",
) -> Tuple[str, str]:
    """兼容旧调用；显式报告族参数时启用严格命名空间校验。"""
    if not unit_type and not province:
        return category_of(customer_func), children_label(
            customer_func,
            children_func,
        )
    resolved = resolve_unit_codes(
        customer_func,
        children_func,
        province=province,
        unit_type=unit_type,
    )
    return resolved["category_label"], resolved["children_label"]


def limit_type_of(metric: str) -> str:
    return LIMIT_TYPE.get(str(metric or "").strip(), "")


def heat_type_of(heating_name: str) -> str:
    return HEAT_TYPE.get(str(heating_name or "").strip(), "")


def check_db(verbose: bool = True) -> int:
    """逐条比对全部已登记字典；返回不一致条数。"""
    import psycopg2

    from .db_config import get_pg_config

    expected = expected_dictionary_rows()
    mismatches = 0
    conn = psycopg2.connect(**get_pg_config())
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT dict_type, value, label FROM system_dict_data "
            "WHERE dict_type = ANY(%s) "
            "AND (deleted IS NULL OR deleted = 0) "
            "ORDER BY dict_type, sort",
            (list(expected),),
        )
        actual: Dict[str, Dict[str, str]] = {}
        for dict_type, value, label in cur.fetchall():
            actual.setdefault(str(dict_type), {})[str(value)] = str(label)

        for dict_type, rows in expected.items():
            got = actual.get(dict_type, {})
            for value, label in rows.items():
                if got.get(value) != label:
                    mismatches += 1
                    if verbose:
                        print(
                            f"  ✗ {dict_type} {value}: "
                            f"代码='{label}' DB='{got.get(value)}'"
                        )
            for value in got:
                if value not in rows:
                    mismatches += 1
                    if verbose:
                        print(f"  ✗ {dict_type} {value}: 代码缺，DB='{got[value]}'")
        if verbose:
            print(f"[dept_dict] 字典自检完成，不一致 {mismatches} 条")
    finally:
        cur.close()
        conn.close()
    return mismatches


if __name__ == "__main__":
    import sys

    if "--check-db" in sys.argv:
        raise SystemExit(1 if check_db() else 0)
    for (unit_type, region), spec in DICTIONARIES.items():
        print(f"{unit_type} / {region}: {spec['dictionary_type']}")
        for code, label in spec["labels"].items():
            children = "、".join(
                f"{child}={child_label}"
                for child, child_label in spec["children"].get(code, {}).items()
            ) or "—"
            print(f"  {code} {label}: {children}")
