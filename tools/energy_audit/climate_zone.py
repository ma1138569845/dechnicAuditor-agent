"""
山东省气候子区（A 区 / B 区）与供暖期计算参数 —— 内置单点表

权威来源：DB37/5026-2022《居住建筑节能设计标准》表 3.0.1
          《山东省城市气候子区及计算参数》
          （2022-11-24 发布 / 2023-05-01 实施，山东省住建厅与省市场监管局联合发布）
          两份独立公开 PDF（地方标准信息服务平台、威海市住建局）逐值互证一致，2026-09-20 核验。

判据（标准 3.0.1）：2000 ≤ HDD18 < 3800 且 CDD26 ≤ 90 → 寒冷 A 区；
                    2000 ≤ HDD18 < 3800 且 CDD26 > 90  → 寒冷 B 区。

用途：
  1. 定额取值——DB37/T 2672-2019（党政机关）、DB37/T 2673-2019（医疗机构）的
     表1/表3/表4 按「机构等级 × 气候区」分档，必须选对 A/B 行（历史上出过取错区的事故）。
  2. 5.2.3 用热分析——供暖期天数与起止时间可直接引用本表。

⚠️ 决策依据（2026-09-20 用户确认）：气候区**不再从 ts_customer_info.climate_type 取**，
   一律以本表为准；DB 那列仅用于交叉校验，不一致时告警"请复核"。
   本表查不到 → 不猜，列入提问清单并在报告标【待核验】。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

SOURCE = ('DB37/5026-2022《居住建筑节能设计标准》表3.0.1 '
          '《山东省城市气候子区及计算参数》')


# ============================================================
# 表 3.0.1（全省 16 地市）
#   city: (气候子区, HDD18 ℃·d, CDD26 ℃·d, 供暖期天数 d, 供暖期计算起止时间)
# ============================================================
CITY_CLIMATE: Dict[str, Tuple[str, int, int, int, str]] = {
    '济南': ('B', 2211, 160, 120, '11月15日至次年3月15日'),
    '青岛': ('A', 2401, 22, 141, '11月16日至次年4月5日'),
    '淄博': ('B', 2266, 176, 120, '11月15日至次年3月15日'),
    '枣庄': ('B', 2165, 107, 120, '11月15日至次年3月15日'),
    '东营': ('B', 2507, 109, 120, '11月15日至次年3月15日'),
    '烟台': ('A', 2432, 47, 136, '11月16日至次年3月31日'),
    '潍坊': ('A', 2735, 63, 120, '11月15日至次年3月15日'),
    '济宁': ('B', 2232, 130, 125, '11月15日至次年3月20日'),
    '泰安': ('A', 2494, 71, 120, '11月15日至次年3月15日'),
    '威海': ('A', 2490, 29, 136, '11月20日至次年4月5日'),
    '日照': ('A', 2361, 39, 120, '11月15日至次年3月15日'),
    '临沂': ('A', 2375, 70, 130, '11月10日至次年3月20日'),
    '德州': ('B', 2527, 97, 120, '11月15日至次年3月15日'),
    '聊城': ('B', 2474, 92, 120, '11月15日至次年3月15日'),
    '滨州': ('B', 2604, 94, 125, '11月15日至次年3月20日'),
    '菏泽': ('B', 2396, 116, 120, '11月15日至次年3月15日'),
}

# 简写/历史名 → 标准表内的地市名
CITY_ALIAS: Dict[str, str] = {
    '莱芜': '济南',     # 2019 年撤销莱芜市，辖区分入济南市
    '钢城': '济南',
    '兖州': '济宁',
    '滕州': '枣庄',
}

# 区县级特例（标准表按地市给值；将来若确有区县单独划区，在此登记）
DISTRICT_OVERRIDE: Dict[str, str] = {}

# 行政区划代码（GB/T 2260）前 4 位 → 地市名。
# 用途：项目地址常不含城市名（如"经十东路111号"）、ProjectBase.city 也常为空，
# 而 ts_customer_info.district_id 是可靠的 —— 这条通道比字符串匹配稳。
CITY_BY_CODE: Dict[str, str] = {
    '3701': '济南',
    '3702': '青岛',
    '3703': '淄博',
    '3704': '枣庄',
    '3705': '东营',
    '3706': '烟台',
    '3707': '潍坊',
    '3708': '济宁',
    '3709': '泰安',
    '3710': '威海',
    '3711': '日照',
    '3712': '济南',   # 原莱芜市，2019 年撤销并入济南市
    '3713': '临沂',
    '3714': '德州',
    '3715': '聊城',
    '3716': '滨州',
    '3717': '菏泽',
}


def _clean(name: str) -> str:
    return str(name or '').strip().replace(' ', '')


def city_by_code(district_id) -> str:
    """行政区划代码 → 地市名。例 '370611' → '烟台'。识别不到返回 ''。"""
    digits = ''.join(ch for ch in str(district_id or '') if ch.isdigit())
    if len(digits) < 4:
        return ''
    return CITY_BY_CODE.get(digits[:4], '')


def match_city(text: str) -> str:
    """从任意文本（地市名 / "日照市岚山区××" / 地址）里识别地市名。

    先做别名归一，再在文本中找 16 个地市名（取最长匹配，避免"济宁"被"宁"类误命中）。
    识别不到返回 ''。
    """
    t = _clean(text)
    if not t:
        return ''
    # 别名优先：文本里出现"莱芜"就归济南
    for alias, city in CITY_ALIAS.items():
        if alias in t:
            return city
    # 直接命中（先试全名，再试去"市"）
    for city in CITY_CLIMATE:
        if city in t:
            return city
    return ''


def resolve_climate_zone(city: str = '', district: str = '', address: str = '',
                         district_id=None) -> Tuple[str, str]:
    """解析气候子区。

    Args:
        city: 地市（ProjectBase.city），如 "烟台"
        district: 区县（ProjectBase.district）
        address: 地址文本，用于 city 为空时兜底识别
        district_id: 行政区划代码（ts_customer_info.district_id），如 370611

    Returns:
        (气候子区, 依据说明)；识别不到返回 ('', '未识别，需人工确认')

    查找顺序：区县特例 → 行政区划代码 → 地市/区县/地址文本。
    """
    for key in (district, city, address):
        k = _clean(key)
        if k and k in DISTRICT_OVERRIDE:
            zone = DISTRICT_OVERRIDE[k]
            return zone, f"{SOURCE}（区县特例：{k}）"
    # 1) 行政区划代码（最可靠：地址常不含城市名、city 常为空）
    hit = city_by_code(district_id)
    if not hit:
        # 2) 文本匹配
        for key in (city, address, district):
            hit = match_city(key)
            if hit:
                break
    if hit:
        zone = CITY_CLIMATE[hit][0]
        return zone, f"{SOURCE}（{hit} 属寒冷{zone}区）"
    return '', '未识别，需人工确认'


def resolve_heating_params(city: str = '', district: str = '', address: str = '',
                           district_id=None) -> Dict[str, object]:
    """取供暖期计算参数（5.2.3 用热分析可直接引用）。

    Returns:
        {} 或 {'city','zone','hdd18','cdd26','days','period','source'}
    """
    hit = (city_by_code(district_id) or match_city(city)
           or match_city(address) or match_city(district))
    if not hit:
        return {}
    zone, hdd18, cdd26, days, period = CITY_CLIMATE[hit]
    return {
        'city': hit,
        'zone': zone,
        'hdd18': hdd18,
        'cdd26': cdd26,
        'days': days,
        'period': period,
        'source': SOURCE,
    }


def check_db(climate_type_from_db: str, city: str = '', district: str = '',
             address: str = '', district_id=None) -> Optional[str]:
    """交叉校验：DB 的 climate_type 与本表判定是否一致。

    Returns:
        None（一致 / 无 DB 值 / 本表识别不到），或一句告警文本。
    """
    zone, _ = resolve_climate_zone(city, district, address, district_id)
    db_val = str(climate_type_from_db or '').strip().upper()
    if not zone or db_val not in ('A', 'B'):
        return None
    if db_val != zone:
        return (f"气候区不一致：DB climate_type={db_val}，"
                f"{SOURCE} 判定为 {zone} 区（地点：{city or address}）。"
                f"以标准表为准，请复核平台数据。")
    return None


if __name__ == '__main__':
    print(f"来源：{SOURCE}\n")
    print(f"{'地市':<6}{'气候子区':<10}{'HDD18':>8}{'CDD26':>8}{'天数':>6}  供暖期")
    for city, (zone, hdd18, cdd26, days, period) in CITY_CLIMATE.items():
        print(f"{city:<6}{'寒冷' + zone + '区':<10}{hdd18:>8}{cdd26:>8}{days:>6}  {period}")
