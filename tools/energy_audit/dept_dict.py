"""
机构/单位类型字典（PG system_dict_data 的代码侧镜像，单点维护）

来源（dc_energy_audit2，2026-09-20 连库逐条比对，与平台字典完全一致）：
  client_dept_type    A 政务服务中心 / B 场馆机构 / C 医疗机构 / D 党政机关 / E 教育机构
  client_dept_type_A  A 市级及以上 / B 市级以下                （政务服务中心）
  client_dept_type_B  A 图书馆 / B 博物馆 / C 剧院 / D 体育馆 / E 科技馆
  client_dept_type_C  A 一级 / B 二级 / C 三级                  （医疗机构）
  client_dept_type_D  A 省级 / B 市级 / C 市级以下               （党政机关）
  client_dept_type_E  A 本科及以上 / B 专科 / C 普通非寄宿制 / D 普通寄宿制 /
                      E 职业学校 / F 初等教育 / G 学前教育 / H 其他教育

用途：把 ts_customer_info.customer_func + children_func 译成中文分档/等级，
交给 indicators.resolve_benchmark 作为 sub_type 选行；避免再用"单位名里有没有
大学/中学"这类猜测来定机构类型和档位。

⚠️ 平台改字典 → 跑 `python -m tools.energy_audit.dept_dict --check-db` 复核。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


# ============================================================
# 字典（与 system_dict_data 一一对应）
# ============================================================

DEPT_TYPE: Dict[str, str] = {
    'A': '政务服务中心',
    'B': '场馆机构',
    'C': '医疗机构',
    'D': '党政机关',
    'E': '教育机构',
}

# 一级码 → indicators / _DEFAULT_BENCHMARKS 用的英文机构族名
DEPT_TO_INSTITUTION_TYPE: Dict[str, str] = {
    'A': 'service',
    'B': 'venue',
    'C': 'medical',
    'D': 'government',
    'E': 'education',
}

# 中文机构类别 → 一级码（institution_classifier 的输出即这套中文名）
CATEGORY_TO_UNIT_FUNC: Dict[str, str] = {
    '政务服务中心': 'A',
    '场馆机构': 'B',
    '体育': 'B',
    '医疗机构': 'C',
    '医疗': 'C',
    '党政机关': 'D',
    '教育': 'E',
    '教育机构': 'E',
}

# 一级码 → {二级码: 中文标签}
CHILDREN_FUNC: Dict[str, Dict[str, str]] = {
    'A': {'A': '市级及以上', 'B': '市级以下'},
    'B': {'A': '图书馆', 'B': '博物馆', 'C': '剧院', 'D': '体育馆', 'E': '科技馆'},
    'C': {'A': '一级', 'B': '二级', 'C': '三级'},
    'D': {'A': '省级', 'B': '市级', 'C': '市级以下'},
    'E': {
        'A': '本科及以上',
        'B': '专科',
        'C': '普通非寄宿制',
        'D': '普通寄宿制',
        'E': '职业学校',
        'F': '初等教育',
        'G': '学前教育',
        'H': '其他教育',
    },
}


# ============================================================
# 指标 → ts_limit_config.limit_type（表号码）
# ============================================================
LIMIT_TYPE: Dict[str, str] = {
    'unit_area_non_heating': 'A',   # 表1 单位建筑面积非供暖能耗
    'unit_area_heating': 'B',       # 表2 单位采暖建筑面积供暖能耗（再按 heat_type 分）
    'per_capita_energy': 'C',       # 表3 人均综合能耗
    'unit_area_elec': 'D',          # 表4 常规用能系统单位建筑面积电耗
    'eue': 'E',                     # 表5 数据中心能量利用效率
    'water': 'F',                   # 用水定额
    'water_per_person': 'F',
    'water_per_bed_day': 'F',
}

# 表2 供暖类型 → heat_type 码（标准注1：按面积收费的市政集中供暖、燃煤自供暖，
# 均按"市政集中供暖（按热计量）"计算）
HEAT_TYPE: Dict[str, str] = {
    '市政集中供暖（按热计量）': 'A',
    '市政集中供暖': 'A',
    '燃煤自供暖': 'A',
    '空调供暖': 'B',
    '燃气（油）供暖': 'C',
    '燃气供暖': 'C',
}

# 场馆类专用：ts_limit_config 把"省级/市级/区县级"存在 area_code 列
AREA_GRADE: Dict[str, str] = {
    '省级': 'A',
    '市级': 'B',
    '区县级': 'C',
    '区、县级': 'C',
    '区县': 'C',
}


# ============================================================
# 便捷函数
# ============================================================

def children_label(unit_func: str, children_func: str) -> str:
    """二级码 → 中文标签。例 ('E','A') → '本科及以上'；未知返回 ''。"""
    if not unit_func or not children_func:
        return ''
    return CHILDREN_FUNC.get(str(unit_func).strip().upper(), {}).get(
        str(children_func).strip().upper(), '')


def institution_type_of(unit_func: str) -> str:
    """一级码 → 英文机构族名；未知返回 ''（由调用方回退到名称分类器）。"""
    return DEPT_TO_INSTITUTION_TYPE.get(str(unit_func or '').strip().upper(), '')


def category_of(unit_func: str) -> str:
    """一级码 → 中文机构类别（对齐 institution_classifier 的取值习惯）。"""
    cn = DEPT_TYPE.get(str(unit_func or '').strip().upper(), '')
    if cn == '教育机构':
        return '教育'
    return cn


def classify_from_codes(customer_func: str, children_func: str) -> Tuple[str, str]:
    """(customer_func, children_func) → (机构类别中文, 二级类型中文)。

    取不到时返回 ('', '')，调用方回退到单位名分类器。
    例：
      ('E','A') → ('教育', '本科及以上')
      ('D','C') → ('党政机关', '市级以下')
      ('C','B') → ('医疗机构', '二级')
    """
    return category_of(customer_func), children_label(customer_func, children_func)


def limit_type_of(metric: str) -> str:
    """指标名 → limit_type 表号码。未知返回 ''。"""
    return LIMIT_TYPE.get(str(metric or '').strip(), '')


def heat_type_of(heating_name: str) -> str:
    """供暖类型名 → heat_type 码。未知返回 ''。"""
    return HEAT_TYPE.get(str(heating_name or '').strip(), '')


# ============================================================
# 自检：连库比对字典（平台改字典后必须跑）
# ============================================================

def check_db(verbose: bool = True) -> int:
    """把本文件的字典与 PG system_dict_data 逐条比对。返回不一致条数（0 = 一致）。"""
    import psycopg2

    from .db_config import get_pg_config

    mismatches = 0
    conn = psycopg2.connect(**get_pg_config())
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT dict_type, value, label FROM system_dict_data "
            "WHERE dict_type LIKE 'client_dept_type%' "
            "AND (deleted IS NULL OR deleted = 0) ORDER BY dict_type, sort"
        )
        rows = cur.fetchall()
        seen = {}
        for dict_type, value, label in rows:
            key = dict_type.replace('client_dept_type', '').lstrip('_') or 'MAIN'
            seen.setdefault(key, {})[value] = label

        expect = {'MAIN': DEPT_TYPE}
        expect.update(CHILDREN_FUNC)
        for key, table in expect.items():
            db_table = seen.get(key, {})
            for code, label in table.items():
                got = db_table.get(code)
                if got != label:
                    mismatches += 1
                    if verbose:
                        print(f"  ✗ client_dept_type_{key} {code}: 代码='{label}' DB='{got}'")
            for code in db_table:
                if code not in table:
                    mismatches += 1
                    if verbose:
                        print(f"  ✗ client_dept_type_{key} {code}: 代码缺，DB='{db_table[code]}'")
        if verbose:
            print(f"[dept_dict] 字典自检完成，不一致 {mismatches} 条")
    finally:
        cur.close()
        conn.close()
    return mismatches


if __name__ == '__main__':
    import sys

    if '--check-db' in sys.argv:
        sys.exit(1 if check_db() else 0)
    print('机构类型字典：')
    for code, cn in DEPT_TYPE.items():
        subs = CHILDREN_FUNC.get(code, {})
        detail = '、'.join(f"{k}={v}" for k, v in subs.items()) or '—'
        print(f"  {code} {cn}: {detail}")
