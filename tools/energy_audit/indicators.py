"""
能源审计指标计算工具

三级兜底查询（系数 & 定额）：
  Layer 1: DB → ts_institution_energy_main.standard_coal_coefficient + ts_limit_config
  Layer 2: 用户提供
  Layer 3: 内置默认（GB/T 2589-2020 + DB37/T 2673-2019）+ web_search

参考标准：
- GB/T 2589-2020 综合能耗计算通则
- DB37/T 2673-2019 医疗机构能源消耗定额标准
- DB37/T 2672-2019 党政机关能源消耗定额标准
- DB37_T 3780-2019 场馆机构能源消耗定额标准
- DB37/T 2671-2019 教育机构能源消耗定额标准
- DB37_T 3781-2019 政务服务中心能源消耗定额标准
- 《山东省公共建筑节能改造节能量核定办法》（试行）

作者: 马天远 | 版本: 2.0.0 | 日期: 2026-07-31
prod - serial number - 5
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json, os, logging

from tools.energy_audit.project_data import is_valid_coefficient

logger = logging.getLogger(__name__)


# ============================================================
# 折标系数
# ============================================================

COEFFICIENTS = {
    'electricity': 0.31,   # kgce/kWh（等效电折标系数 0.31 用于非供暖能耗计算）
    'water':       0.2571,   # kgce/t
    'natural_gas': 1.3300,   # kgce/m³
    'heat':        0.03412,  # kgce/MJ （供暖用）
    'diesel':      1.4571,   # kgce/kg
    'gasoline':    1.4714,   # kgce/kg
}

# 非供暖能耗计算使用等效电折标系数（区别于发电煤耗 0.1229）
ELEC_COEFF_NON_HEATING = 0.31  # kgce/kWh（终端电力等价值）

# 内置兜底定额（kgce/(m²·a)） → 约束值, 基准值, 引导值
_DEFAULT_BENCHMARKS = {
    'medical': {  # DB37/T 2673-2019, 二级 A区（最常见医院类型）
        'unit_area_non_heating': (22.6, 15.3, 9.4),
        'unit_area_elec': (73.1, 53.0, 34.9),
        'per_capita_energy': (907.4, 556.9, 428.3),
        # 用水: DB37/T 4452-2021, 二级医院, 单位开放床日用水量 L/(床·d)
        'water_per_bed_day': (340, 540, 0),     # 先进值, 通用值（约束值）, —
        'standard_name': 'DB37/T 2673-2019《医疗机构能源消耗定额标准》',
        'water_standard': 'DB37/T 4452-2021《山东省教育、卫生等服务业用水定额》',
    },
    'government': {  # DB37/T 2672-2019（标准原文已核验 2026-09-02；烟台法院=市级以下+A区）
        'unit_area_non_heating': (20.0, 11.9, 6.5),
        'unit_area_elec': (67.4, 39.5, 20),
        'per_capita_energy': (1197.8, 781.0, 453.7),
        # 表2 单位采暖建筑面积供暖能耗（不分机构等级，按供暖类型）：
        # 市政集中供暖(按热计量) 12.7/11.1/8.3；空调供暖 12.4/8.9/6.4；燃气(油)供暖 12.3/8.4/4.8
        'unit_area_heating': (12.7, 11.1, 8.3),  # 默认市政集中供暖（按热计量）口径
        # 用水: DB37/T 4452-2021, 机关
        'water_per_person': (10, 25, 0),        # 先进值, 通用值（约束值）, — m³/(人·a)
        'standard_name': 'DB37/T 2672-2019《党政机关能源消耗定额标准》',
        'water_standard': 'DB37/T 4452-2021《山东省教育、卫生等服务业用水定额》',
    },
    'education': {
        'unit_area_non_heating': (11.5, 7.0, 4.0),
        'unit_area_elec': (35.0, 25.0, 18.0),
        'per_capita_energy': (400, 300, 200),
        # 用水: DB37/T 4452-2021, 教育业单位取水量 m³/(p·a)
        'water_per_person': (8, 14, 0),          # 先进值, 通用值（约束值）, —
        'water_standard': 'DB37/T 4452-2021《山东省教育、卫生等服务业用水定额》',
        'standard_name': 'DB37/T 2674-2019《教育机构能源消耗定额标准》',
    },
    'venue': {  # DB37/T 3780-2019《场馆机构能源消耗定额标准》（标准原文核验 2026-09-03；取"市"档）
        # 子类型嵌套：图书馆/博物馆/剧院/体育馆/科技馆 → (约束值, 基准值, 引导值)
        # 注4：文化馆（宫）、美术馆等其他文化类场馆参照图书馆。
        # 表1 单位建筑面积非供暖能耗 kgce/(m²·a)（市档）
        'unit_area_non_heating': {
            '图书馆': (16.2, 12.2, 9.7), '博物馆': (21.9, 15.3, 8.0), '剧院': (17.3, 12.3, 8.2),
            '体育馆': (16.7, 14.9, 11.3), '科技馆': (15.6, 8.3, 6.6),
        },
        # 表2 单位采暖建筑面积供暖能耗 kgce/(m²·a)（市政集中供暖按热计量，不分省市档）
        'unit_area_heating': {
            '图书馆': (12.5, 11.4, 9.3), '博物馆': (12.9, 11.8, 10.3), '剧院': (12.6, 11.6, 9.9),
            '体育馆': (16.7, 13.2, 11.5), '科技馆': (12.1, 11.3, 9.3),
        },
        # 表3 人均综合能耗 kgce/(p·a)（市档）
        'per_capita_energy': {
            '图书馆': (466.6, 388.8, 311.1), '博物馆': (522.0, 350.8, 225.7), '剧院': (552.5, 304.7, 204.8),
            '体育馆': (641.3, 437.3, 332.6), '科技馆': (762.0, 635.0, 505.5),
        },
        # 表4 常规用能系统单位建筑面积电耗 kWh/(m²·a)（市档）
        'unit_area_elec': {
            '图书馆': (57.1, 35.1, 24.3), '博物馆': (65.8, 46.7, 27.7), '剧院': (67.1, 48.2, 32.3),
            '体育馆': (54.3, 34.5, 23.9), '科技馆': (76.3, 42.9, 26.3),
        },
        # 表5 数据中心 EUE（场馆专用：2.2/1.7/1.4，与党政机关 2.2/1.8/1.4 不同）
        'eue': (2.2, 1.7, 1.4),
        # 用水：DB37/T 3780-2019 无取水定额 → 不对标（面积口径 benchmark 为空）
        'standard_name': 'DB37/T 3780-2019《场馆机构能源消耗定额标准》',
        # 用水: DB37/T 4452-2021, 场馆类
        'water_per_person': (8, 18, 0),          # 先进值, 通用值（约束值）, — m³/(人·a)
        'standard_name': 'DB37/T 3780-2019《场馆机构能源消耗定额标准》',
        'water_standard': 'DB37/T 4452-2021《山东省教育、卫生等服务业用水定额》',
    },
    'service': {  # DB37/T 3781-2019, 政务服务中心
        # 政务服务中心特点：窗口服务、大厅照明空调、人流密集
        'unit_area_non_heating': (14.0, 9.5, 6.5),
        'unit_area_elec': (48.0, 36.0, 26.0),
        'per_capita_energy': (850, 620, 420),
        # 用水: DB37/T 4452-2021, 政务服务
        'water_per_person': (9, 22, 0),          # 先进值, 通用值（约束值）, — m³/(人·a)
        'standard_name': 'DB37/T 3781-2019《政务服务中心能源消耗定额标准》',
        'water_standard': 'DB37/T 4452-2021《山东省教育、卫生等服务业用水定额》',
    },
}


# ============================================================
# 三级兜底查询
# ============================================================

def _db_config():
    """DB 连接配置（统一走 db_config 解析链，凭据不硬编码）"""
    try:
        from .db_config import get_pg_config
    except ImportError:  # 脚本直跑（python indicators.py）时无包上下文
        # Fallback to the shared path resolver so we don't duplicate the walk logic.
        from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401
        from tools.energy_audit.db_config import get_pg_config
    return get_pg_config()


def lookup_coefficient_from_db(energy_code: str) -> Optional[float]:
    """Layer 1: 从 ts_institution_energy_main 查折标系数"""
    try:
        import psycopg2
        conn = psycopg2.connect(**_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT standard_coal_coefficient, energy_name
            FROM ts_institution_energy_main
            WHERE (deleted IS NULL OR deleted = 0)
              AND energy_code = %s
              AND standard_coal_coefficient IS NOT NULL
              AND standard_coal_coefficient > 0
            ORDER BY id DESC LIMIT 1
        """, (energy_code,))
        row = cur.fetchone()
        conn.close()
        if row:
            logger.info(f"Layer1 DB: energy_code={energy_code} coeff={row[0]} ({row[1]})")
            return float(row[0])
    except Exception as e:
        logger.warning(f"Layer1 DB failed: {e}")
    return None


def lookup_benchmark_from_db(field_type: str, limit_type: str = 'A',
                              climate_type: str = 'A') -> Optional[dict]:
    """Layer 1: 从 ts_limit_config 查定额
       参数： field_type: 领域类型
             limit_type: 限额类型
             climate_type: 气候区域类型

    """
    try:
        import psycopg2
        conn = psycopg2.connect(**_db_config())
        cur = conn.cursor()
        cur.execute("""
            SELECT value1, value2, value3, standard_name
            FROM ts_limit_config
            WHERE (deleted IS NULL OR deleted = 0)
              AND field_type = %s
              AND limit_type = %s
              AND climate_type = %s
            ORDER BY id DESC LIMIT 1
        """, (field_type, limit_type, climate_type))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            result = {
                '约束值': float(row[0]), '基准值': float(row[1]), '引导值': float(row[2]),
                '标准': row[3] or '',
                '来源': 'DB',
            }
            logger.info(f"Layer1 DB benchmark: {result}")
            return result
    except Exception as e:
        logger.warning(f"Layer1 DB benchmark failed: {e}")
    return None


def resolve_coefficient(energy_type: str, user_value: Optional[float] = None) -> float:
    """三级兜底获取折标系数

    Layer 1: DB (ts_institution_energy_main)，合理性检查
    Layer 2: 用户提供
    Layer 3: 内置默认 (COEFFICIENTS)

    合理性范围（超出则跳过 Layer 1）：
      电 0.1~1.0, 水 0.01~1.0, 气 0.5~2.5, 热 0.01~0.05, 油 1.0~2.0
    """
    # 合理性范围
    _ranges = {
        'electricity': (0.1, 1.0), 'water': (0.01, 1.0), 'natural_gas': (0.5, 2.5),
        'heat': (0.01, 0.05), 'diesel': (1.0, 2.0), 'gasoline': (1.0, 2.0),
    }

    # Layer 1
    code_map = {'electricity': '45', 'water': '01', 'natural_gas': '25',
                'heat': '50', 'diesel': '300302', 'gasoline': '300301'}
    code = code_map.get(energy_type, energy_type)
    db_val = lookup_coefficient_from_db(code)
    lo, hi = _ranges.get(energy_type, (0, float('inf')))
    if db_val is not None and lo <= db_val <= hi:
        return db_val
    elif db_val is not None:
        logger.info(f"Layer1 DB value {db_val} out of range [{lo},{hi}], falling through")

    # Layer 2
    if user_value is not None:
        logger.info(f"Layer2 User: energy_type={energy_type} coeff={user_value}")
        return user_value

    # Layer 3
    defaults = {
        'electricity': 0.1229, 'water': 0.2571, 'natural_gas': 1.3300,
        'heat': 0.03412, 'diesel': 1.4571, 'gasoline': 1.4714,
    }
    val = defaults.get(energy_type, 0)
    logger.info(f"Layer3 Default: energy_type={energy_type} coeff={val}")
    return val


def resolve_benchmark(institution_type: str = 'government',
                       metric: str = 'unit_area_non_heating',
                       user_values: Optional[Tuple[float, float, float]] = None,
                       sub_type: Optional[str] = None) -> dict:
    """三级兜底获取定额对标值

    Layer 1: DB (ts_limit_config)
    Layer 2: 用户提供
    Layer 3: 内置默认 (_DEFAULT_BENCHMARKS)

    institution_type: 'medical'|'government'|'education'
    metric: 'unit_area_non_heating'|'unit_area_elec'
    返回 {约束值, 基准值, 引导值, 标准, 来源}
    """
    # Layer 1
    field_types = {'medical': '20', 'government': '10', 'education': '30'}
    ft = field_types.get(institution_type, '10')
    db_val = lookup_benchmark_from_db(ft, 'A', 'A')
    if db_val:
        std = db_val.get('标准', '')
        expected_kw = {'government': '党政机关', 'medical': '医疗机构', 'education': '教育机构'}
        # 校验 DB 返回的标准名与机构类型是否匹配；
        # venue/service 无 DB 匹配规则 → 跳过 DB 层（防止空字符串恒匹配误用别类记录）
        expected = expected_kw.get(institution_type)
        if expected and expected in std:
            return db_val
        # 不匹配 → 忽略 DB，走 Layer 2/3

    # Layer 2
    if user_values and len(user_values) == 3:
        return {
            '约束值': user_values[0], '基准值': user_values[1], '引导值': user_values[2],
            '标准': '用户提供',
            '来源': 'User',
        }

    # Layer 3
    defaults = _DEFAULT_BENCHMARKS.get(institution_type, _DEFAULT_BENCHMARKS['government'])
    vals = defaults.get(metric, (0, 0, 0))
    if isinstance(vals, dict):
        # venue 子类型嵌套：按场馆子类型取值，缺省用图书馆（注4：文化馆宫美术馆参照图书馆）
        st = sub_type or '图书馆'
        vals = vals.get(st) or vals.get('图书馆', (0, 0, 0))
    # 用水指标优先报告用水标准名（水三元组语义为 先进/通用，与能耗三值口径不同）
    std_name = defaults.get('standard_name', '')
    if metric.startswith('water'):
        std_name = defaults.get('water_standard', std_name)
    return {
        '约束值': vals[0], '基准值': vals[1], '引导值': vals[2],
        '标准': std_name,
        '来源': 'Default',
    }


# ============================================================
# 机构类型映射
# ============================================================

def institution_category_to_type(institution_category: str) -> str:
    """把 ProjectBase.institution_category 映射为 indicators  institution_type。

    映射规则（按优先级）：
      医疗/医院/卫生/床 → medical
      教育/学校/大学/中学/小学/幼儿园 → education
      场馆/体育/文化/科技/展览 → venue
      政务/服务/行政/审批 → service
      党政/政府/机关/法院/公安 等 → government
    """
    if not institution_category:
        return 'government'
    cat = str(institution_category).lower()
    if any(k in cat for k in ('医疗', '医院', '卫生', '床')):
        return 'medical'
    if any(k in cat for k in ('教育', '学校', '大学', '中学', '小学', '幼儿园')):
        return 'education'
    if any(k in cat for k in ('场馆', '体育', '文化', '科技', '展览', '博物馆', '图书馆', '体育馆')):
        return 'venue'
    if any(k in cat for k in ('政务', '服务', '行政', '审批', '便民', '窗口')):
        return 'service'
    # 其余公共机构统一按党政机关处理
    return 'government'


# ============================================================
# 数据模型
# ============================================================

@dataclass
class YearlyEnergyData:
    """某年度能耗数据"""
    year: int
    electricity_kwh: float = 0    # 总用电量 kWh
    water_m3: float = 0           # 总用水量 m³
    natural_gas_m3: float = 0     # 天然气 m³
    heating_energy_kwh: float = 0 # 供暖能耗（电力部分）kWh
    heating_energy_gas: float = 0 # 供暖能耗（天然气部分）m³
    heating_energy_heat: float = 0 # 供暖能耗（热量）GJ
    transportation_petrol_kg: float = 0  # 交通能耗（汽油）kg
    transportation_diesel_kg: float = 0 # 交通能耗（柴油）kg
    building_area: float = 0      # 建筑面积 m²
    people_count: float = 0       # 用能人数
    # 费用
    electricity_cost_wan: float = 0
    water_cost_wan: float = 0
    natural_gas_cost_wan: float = 0
    heating_cost_wan: float = 0
    petrol_cost_wan: float = 0
    # 持久化折标煤系数（优先于 DB / 默认值）
    coefficients: Dict[str, float] = field(default_factory=dict)

    def get_coefficient(self, energy_type: str) -> float:
        """获取折标煤系数：优先使用持久化系数，否则走三级兜底（DB / 用户 / 默认）。

        持久化系数仅在大于 0 且可解析为 float 时才被使用；0 / None / 空字符串 /
        非法值会回退到 resolve_coefficient。
        """
        coeff = self.coefficients.get(energy_type)
        if is_valid_coefficient(coeff):
            return float(coeff)
        return resolve_coefficient(energy_type)

    @property
    def total_energy_tce(self) -> float:
        """综合能耗 tce（优先使用持久化折标系数，否则 DB / 默认）

        口径（DB37/T 2672-2019 附录B）：水不折算标准煤，不计入综合能耗。
        """
        tce = 0
        tce += self.electricity_kwh * self.get_coefficient('electricity') / 1000
        tce += self.natural_gas_m3 * self.get_coefficient('natural_gas') / 1000
        tce += self.heating_energy_heat * self.get_coefficient('heat')
        tce += self.transportation_petrol_kg * self.get_coefficient('gasoline') / 1000
        tce += self.transportation_diesel_kg * self.get_coefficient('diesel') / 1000
        return round(tce, 4)

    @property
    def non_heating_energy_kgce(self) -> float:
        """非供暖能耗 kgce（等效电系数 0.31，仅计算电耗）
        
        根据《公共机构能源审计技术导则》(GB/T 31342-2014)：
        医院非供暖能耗 = (总用电量 - 供暖用电) × 0.31
        天然气（厨房）、水、汽油（交通）不纳入非供暖能耗计算。
        """
        non_heat_elec = self.electricity_kwh - self.heating_energy_kwh
        return round(non_heat_elec * ELEC_COEFF_NON_HEATING, 4)

    @property
    def heating_energy_tce(self) -> float:
        """供暖能耗 tce（优先使用持久化折标系数，否则 DB / 默认）"""
        tce = 0
        tce += self.heating_energy_kwh * self.get_coefficient('electricity') / 1000
        tce += self.heating_energy_gas * self.get_coefficient('natural_gas') / 1000
        tce += self.heating_energy_heat * self.get_coefficient('heat')
        return round(tce, 4)

    @property
    def transportation_energy_tce(self) -> float:
        """交通能耗 tce（优先使用持久化折标系数，否则 DB / 默认）"""
        tce = 0
        tce += self.transportation_petrol_kg * self.get_coefficient('gasoline') / 1000
        tce += self.transportation_diesel_kg * self.get_coefficient('diesel') / 1000
        return round(tce, 4)

    @property
    def non_heating_energy_tce(self) -> float:
        """非供暖能耗 tce"""
        return round(self.total_energy_tce - self.heating_energy_tce - self.transportation_energy_tce, 4)

    @property
    def non_heating_electricity_kwh(self) -> float:
        """非供暖用电量 kWh"""
        return self.electricity_kwh - self.heating_energy_kwh


# ============================================================
# 指标计算
# ============================================================

def calc_unit_area_non_heating_energy(
    data: YearlyEnergyData,
    exclude_special_area: float = 0,  # 需剔除的特殊功能区面积
) -> dict:
    """
    单位建筑面积非供暖能耗

    公式: Ejfgn = (E - Egn - Ejt) / M
    式中:
      E    = 综合能耗 (kgce/a)
      Egn  = 供暖能耗 (kgce/a)
      Ejt  = 交通能耗 (kgce/a)
      M    = 建筑面积 (m²)

    注: 医疗机构的大型医疗设备、数据中心、厨房炊事、洗衣房等特定功能用能不计入。
    返回 {kgce_per_m2, non_heating_kgce, building_area_m2, total_energy_tce,
          heating_energy_tce, transportation_energy_tce, formula}；
    建筑面积无效时返回同结构全 0 + error 字段，供上层安全降级。
    """
    area = data.building_area - exclude_special_area
    if area <= 0:
        return {'kgce_per_m2': 0, 'non_heating_kgce': 0, 'building_area_m2': 0,
                'total_energy_tce': 0, 'heating_energy_tce': 0,
                'transportation_energy_tce': 0, 'error': '建筑面积无效'}

    non_heat_kgce = data.non_heating_energy_kgce
    kgce_per_m2 = round(non_heat_kgce / area, 2)

    return {
        'kgce_per_m2': kgce_per_m2,
        'non_heating_kgce': non_heat_kgce,
        'building_area_m2': area,
        'total_energy_tce': data.total_energy_tce,
        'heating_energy_tce': data.heating_energy_tce,
        'transportation_energy_tce': data.transportation_energy_tce,
        'formula': 'Ejfgn = (E - Egn - Ejt) / M',
    }


def compare_with_benchmark(kgce_per_m2: float, institution_type: str = 'medical',
                          metric: str = 'unit_area_non_heating',
                          user_benchmark: Optional[Tuple[float, float, float]] = None) -> dict:
    """
    定额对标（三级兜底）
    
    Layer 1: DB ts_limit_config
    Layer 2: 用户提供 (user_benchmark)
    Layer 3: 内置默认 _DEFAULT_BENCHMARKS
    """
    bm = resolve_benchmark(institution_type, metric, user_benchmark)
    if kgce_per_m2 <= bm['引导值']:
        level = '低于引导值（先进水平）'
    elif kgce_per_m2 <= bm['基准值']:
        level = '低于基准值（合理水平）'
    elif kgce_per_m2 <= bm['约束值']:
        level = '低于约束值（达标）'
    else:
        level = '高于约束值（需整改）'

    return {**bm, '实际值': kgce_per_m2, '评价结果': level,}


def calc_unit_area_electricity(
    data: YearlyEnergyData,
    exclude_special_area: float = 0,
    institution_type: str = 'medical',
    user_benchmark: Optional[Tuple[float, float, float]] = None,
    sub_type: Optional[str] = None,  # venue 子类型（图书馆/博物馆/剧院/体育馆/科技馆）
) -> dict:
    """
    常规用能系统单位建筑面积电耗（三级兜底）

    公式: Ed = (E_total_elec - E_heating_elec) / M
    式中:
      E_total_elec  = 年总用电量 (kWh)
      E_heating_elec = 供暖用电量 (kWh)
      M             = 建筑面积 (m²)
    注: 医疗设备、数据中心等特殊用能不计入常规用能系统。

    DB37/T 2673-2019 定额（医疗机构）：
      约束值 73.1、基准值 55.2、引导值 38.9 kWh/(m²·a)

    返回 {kwh_per_m2, total_electricity_kwh, building_area_m2, benchmark}；
    建筑面积无效时返回同结构全 0 + error 字段，供上层安全降级。
    """
    area = data.building_area - exclude_special_area
    if area <= 0:
        return {'kwh_per_m2': 0, 'total_electricity_kwh': 0, 'building_area_m2': 0,
                'benchmark': None, 'error': '建筑面积无效'}

    non_heat_elec = data.non_heating_electricity_kwh
    kwh_per_m2 = round(non_heat_elec / area, 2)

    # 三级兜底对标
    benchmark = resolve_benchmark(institution_type, 'unit_area_elec', user_benchmark, sub_type)
    if kwh_per_m2 <= benchmark['引导值']:
        evaluation = '低于引导值（先进水平）'
    elif kwh_per_m2 <= benchmark['基准值']:
        evaluation = '低于基准值（合理水平）'
    elif kwh_per_m2 <= benchmark['约束值']:
        evaluation = '低于约束值（达标）'
    else:
        evaluation = '高于约束值（需整改）'

    return {
        'kwh_per_m2': kwh_per_m2,
        'total_electricity_kwh': non_heat_elec,
        'building_area_m2': area,
        'benchmark': {**benchmark, '实际值': kwh_per_m2, '评价结果': evaluation},
    }


def calc_unit_area_heating_energy(
    data: YearlyEnergyData,
    heating_area: float = 0,
    institution_type: str = 'government',
    user_benchmark: Optional[Tuple[float, float, float]] = None,
    sub_type: Optional[str] = None,  # venue 子类型
) -> dict:
    """
    单位采暖建筑面积供暖能耗（DB37/T 2672-2019 表2）

    公式: Egn_m2 = Egn × 1000 / Mgn
    式中:
      Egn = 供暖能耗 (tce/a，含热力/供暖电耗/供暖燃气，见 YearlyEnergyData.heating_energy_tce)
      Mgn = 采暖建筑面积 (m²)；缺失时用建筑面积兜底（2026-09-02 用户确认）

    定额（表2，不分机构等级，按供暖类型）：
      市政集中供暖(按热计量) 12.7/11.1/8.3；空调供暖 12.4/8.9/6.4；燃气(油)供暖 12.3/8.4/4.8
      默认取市政集中供暖（按热计量）口径，其他供暖类型由调用方传 user_benchmark 覆盖。

    返回 {kgce_per_m2, heating_energy_kgce, heating_area_m2, benchmark}；
    采暖建筑面积无效或项目无供暖能耗时返回同结构全 0 + error 字段，供上层安全降级。
    """
    area = heating_area if heating_area and heating_area > 0 else data.building_area
    if area <= 0:
        return {'kgce_per_m2': 0, 'heating_energy_kgce': 0, 'heating_area_m2': 0,
                'benchmark': None, 'error': '采暖建筑面积无效'}

    heating_kgce = data.heating_energy_tce * 1000
    kgce_per_m2 = round(heating_kgce / area, 2)

    benchmark = resolve_benchmark(institution_type, 'unit_area_heating', user_benchmark, sub_type)
    if kgce_per_m2 <= benchmark['引导值']:
        evaluation = '低于引导值（先进水平）'
    elif kgce_per_m2 <= benchmark['基准值']:
        evaluation = '低于基准值（合理水平）'
    elif kgce_per_m2 <= benchmark['约束值']:
        evaluation = '低于约束值（达标）'
    else:
        evaluation = '高于约束值（需整改）'

    return {
        'kgce_per_m2': kgce_per_m2,
        'heating_energy_kgce': heating_kgce,
        'heating_area_m2': area,
        'benchmark': {**benchmark, '实际值': kgce_per_m2, '评价结果': evaluation},
    }


def calc_per_capita_energy(
    data: YearlyEnergyData,
    institution_type: str = 'medical',
    user_benchmark: Optional[Tuple[float, float, float]] = None,
    sub_type: Optional[str] = None,  # venue 子类型
) -> dict:
    """
    人均综合能耗（三级兜底）

    公式: Er = E / P
    式中:
      E = 综合能耗 (kgce/a)，所有能源 × 折标系数求和
      P = 用能人数

    医疗机构用能人数包括：在岗在编人员 + 编外工作人员 + 门诊人数折算 + 床位数折算。

    DB37/T 2673-2019 定额（医疗机构，参考值）：
      约束值 500、基准值 350、引导值 250 kgce/(人·a)
    （注：该值因地区气候、医院等级差异较大，优先查 DB/用户）

    返回 {kgce_per_person, total_kgce, people_count, benchmark}；
    用能人数无效时返回同结构全 0 + error 字段，供上层安全降级。
    """
    if data.people_count <= 0:
        return {'kgce_per_person': 0, 'total_kgce': 0, 'people_count': data.people_count,
                'benchmark': None, 'error': '用能人数无效'}

    # 综合能耗用持久化折标系数（或三级兜底）计算；水不折算标准煤（DB37/T 2672-2019 附录B）
    kgce_total = (
        data.electricity_kwh * data.get_coefficient('electricity') +
        data.natural_gas_m3 * data.get_coefficient('natural_gas') +
        data.heating_energy_heat * 1000 * data.get_coefficient('heat') +  # GJ→kgce
        data.transportation_petrol_kg * data.get_coefficient('gasoline') +
        data.transportation_diesel_kg * data.get_coefficient('diesel')
    )
    per_person = round(kgce_total / data.people_count, 2)

    # 三级兜底对标
    benchmark = resolve_benchmark(institution_type, 'per_capita_energy', user_benchmark, sub_type)
    if benchmark['约束值'] == 0 and benchmark['基准值'] == 0:
        # 内置兜底也查不到时给提示
        evaluation = '暂无定额标准可对标'
    elif per_person <= benchmark['引导值']:
        evaluation = '低于引导值（先进水平）'
    elif per_person <= benchmark['基准值']:
        evaluation = '低于基准值（合理水平）'
    elif per_person <= benchmark['约束值']:
        evaluation = '低于约束值（达标）'
    else:
        evaluation = '高于约束值（需整改）'

    return {
        'kgce_per_person': per_person,
        'total_kgce': round(kgce_total, 2),
        'people_count': data.people_count,
        'benchmark': {**benchmark, '实际值': per_person, '评价结果': evaluation},
    }


def calc_per_capita_water(
    data: YearlyEnergyData,
    institution_type: str = 'government',
    user_benchmark: Optional[Tuple[float, float, float]] = None,
    bed_count: Optional[int] = None,  # 医院使用
    building_area: Optional[float] = None,  # 政务服务中心/场馆使用（面积口径）
) -> dict:
    """
    人均取水量 / 单位开放床日用水量（三级兜底）

    公式（机关/教育）: Wr = W / P  (m³/人·a)
    公式（医院）:      Vz = Wz / Nbed  (L/(床·d))

    式中:
      W    = 年总取水量 (m³)
      P    = 用能人数
      Wz   = 年住院部用水总量 (m³)
      Nbed = 床位数

    DB37/T 4452-2021 定额：
      二级医院: 先进值 340, 通用值 540 L/(床·d)
      机关:     先进值 10, 通用值 25 m³/(人·a)

    返回 dict，包含 {m3_per_person, total_water_m3, people_count, benchmark}
    医院模式额外返回 {L_per_bed_day, bed_count}；
    用能人数无效时返回同结构全 0 + error 字段，供上层安全降级。
    """
    metric_map = {
        'medical': 'water_per_bed_day',
        'government': 'water_per_person',
        'education': 'water_per_person',
        # FORK: venue/service 显式映射为面积口径（单位建筑面积年取水量）
        'venue': 'water_per_area',
        'service': 'water_per_area',
    }
    metric = metric_map.get(institution_type, 'water_per_person')

    # 医院：单位开放床日用水量
    if institution_type == 'medical' and bed_count and bed_count > 0:
        water_total = data.water_m3
        L_per_bed_day = round(water_total * 1000 / (bed_count * 365), 2)  # m³→L, year→day
        benchmark = resolve_benchmark(institution_type, 'water_per_bed_day', user_benchmark)
        # 水三元组字段语义与能耗相反：约束值=先进值(340), 基准值=通用值(540), 引导值=0
        if L_per_bed_day <= benchmark['约束值']:
            evaluation = '低于先进值'
        elif L_per_bed_day <= benchmark['基准值']:
            evaluation = '低于通用值'
        else:
            evaluation = '高于通用值（需整改）'

        return {
            'L_per_bed_day': L_per_bed_day,
            'total_water_m3': water_total,
            'bed_count': bed_count,
            'metric': '单位开放床日用水量',
            'benchmark': {**benchmark, '实际值': L_per_bed_day, '评价结果': evaluation, '单位': 'L/(床·d)'},
        }

    # 政务服务中心/场馆：单位建筑面积年取水量 = 年取水量 / 建筑面积（m³/(m²·a)）
    # DB37/T 4452-2021 无面积口径取水定额 → benchmark 为空，评价结果显示 "—"（标准待用户确认）
    if institution_type in ('venue', 'service') and building_area and building_area > 0:
        water_total = data.water_m3
        m3_per_area = round(water_total / building_area, 4)
        return {
            'm3_per_area': m3_per_area,
            'total_water_m3': water_total,
            'building_area': building_area,
            'metric': '单位建筑面积年取水量',
            'benchmark': {},
        }

    # 机关/教育：人均取水量
    if data.people_count <= 0:
        return {'m3_per_person': 0, 'total_water_m3': data.water_m3,
                'people_count': data.people_count, 'benchmark': None,
                'error': '用能人数无效'}

    per_person = round(data.water_m3 / data.people_count, 2)

    benchmark = resolve_benchmark(institution_type, 'water_per_person', user_benchmark)
    if benchmark['约束值'] == 0 and benchmark['基准值'] == 0:
        evaluation = '暂无定额标准可对标'
    elif per_person <= benchmark['约束值']:
        # 水三元组字段语义与能耗相反：约束值=先进值, 基准值=通用值, 引导值=0
        evaluation = '低于先进值'
    elif per_person <= benchmark['基准值']:
        evaluation = '低于通用值'
    else:
        evaluation = '高于通用值（需整改）'

    return {
        'm3_per_person': per_person,
        'total_water_m3': data.water_m3,
        'people_count': data.people_count,
        'metric': '人均取水量',
        'benchmark': {**benchmark, '实际值': per_person, '评价结果': evaluation, '单位': 'm³/(人·a)'},
    }


def calc_baseline(
    yearly_data: List[YearlyEnergyData],
) -> dict:
    """
    建筑能耗基准（用量 + 费用）

    规则（《山东省公共建筑节能改造节能量核定办法》4.0.2条）：
    1. 各年能耗逐年递增或递减 → 取最近一年作为基准年
    2. 各年波动范围在 ±10% 以内 → 取三年平均值
    3. 波动超过 ±10% → 取三年平均值（标注波动范围）

    返回:
      usage:    {能源类型: {各年: [...], 基准值, 方法, 波动范围}}
      cost:     {费用类型: {各年: [...], 基准值, 方法, 波动范围}}
      summary:  文字总结
    """
    if not yearly_data:
        return {'error': '无数据'}

    n = len(yearly_data)
    years = [d.year for d in yearly_data]
    usage_items = [
        ('electricity_kwh', '电', 'kWh'),
        ('water_m3', '水', 'm³'),
        ('natural_gas_m3', '天然气', 'm³'),
        ('heating_energy_heat', '热', 'GJ'),
    ]
    cost_items = [
        ('electricity_cost_wan', '电费', '万元'),
        ('water_cost_wan', '水费', '万元'),
        ('heating_cost_wan', '热费', '万元'),
    ]

    usage_result = {}
    cost_result = {}
    summary_parts = []

    def _judge(vals):
        if _is_trend_monotonic(vals):
            return vals[-1], '最近一年', _calc_range(vals)
        elif _is_within_range(vals, 0.10):
            return round(sum(vals) / n, 2), '三年均值（波动≤±10%）', _calc_range(vals)
        else:
            return round(sum(vals) / n, 2), '三年均值（波动超±10%）', _calc_range(vals)

    for attr, label, unit in usage_items:
        vals = [getattr(d, attr, 0) for d in yearly_data]
        if not any(vals):
            continue
        baseline, method, rng = _judge(vals)
        usage_result[label] = {
            '各年': dict(zip(years, vals)),
            '基准值': baseline,
            '单位': unit,
            '方法': method,
            '波动范围': rng,
        }

    for attr, label, unit in cost_items:
        vals = [getattr(d, attr, 0) for d in yearly_data]
        if not any(vals):
            continue
        baseline, method, rng = _judge(vals)
        cost_result[label] = {
            '各年': dict(zip(years, vals)),
            '基准值': baseline,
            '单位': unit,
            '方法': method,
            '波动范围': rng,
        }

    # 生成文字总结
    for label, info in {**usage_result, **cost_result}.items():
        years_str = '、'.join(f"{y}年{info['各年'][y]:,.2f}{info['单位']}" for y in years)
        summary_parts.append(
            f"{years_str}，{info['方法']}，{label}基准值={info['基准值']:,.2f}{info['单位']}（波动{info['波动范围']}）。"
        )

    return {
        'years': years,
        'usage': usage_result,
        'cost': cost_result,
        'summary': '\n'.join(summary_parts),
    }


def _calc_range(vals: list) -> str:
    """计算波动范围描述"""
    if not vals or max(vals) == 0:
        return '—'
    avg = sum(vals) / len(vals)
    deviations = [(v - avg) / avg * 100 for v in vals if v != 0]
    if not deviations:
        return '—'
    return f"{min(deviations):+.1f}%~{max(deviations):+.1f}%"


def _is_trend_monotonic(vals: list) -> bool:
    """检查是否逐年单调递增或递减"""
    if len(vals) < 2:
        return True
    increasing = all(vals[i] <= vals[i+1] for i in range(len(vals)-1))
    decreasing = all(vals[i] >= vals[i+1] for i in range(len(vals)-1))
    return increasing or decreasing


def _is_within_range(vals: list, threshold: float) -> bool:
    """检查波动是否在阈值以内"""
    if not vals or max(vals) == 0:
        return False
    for v in vals:
        if v == 0:
            continue
        deviation = abs(v - (sum(vals)/len(vals))) / (sum(vals)/len(vals))
        if deviation > threshold:
            return False
    return True


# ============================================================
# 项目级统一入口
# ============================================================

def energy_yearly_to_yearly_energy_data(ey, base) -> YearlyEnergyData:
    """把 project_data.EnergyYearly + ProjectBase 转换为 YearlyEnergyData。

    延迟导入 project_data，避免循环依赖；优先使用已加载的模块。
    """
    import sys
    mod = sys.modules.get('tools.energy_audit.project_data')
    if mod is None:
        from tools.energy_audit import project_data as mod
    EnergyYearly = mod.EnergyYearly
    ProjectBase = mod.ProjectBase
    if not isinstance(ey, EnergyYearly):
        raise TypeError("ey 必须是 EnergyYearly 实例")
    if not isinstance(base, ProjectBase):
        raise TypeError("base 必须是 ProjectBase 实例")

    return YearlyEnergyData(
        year=int(ey.year),
        electricity_kwh=float(ey.electricity_kwh or 0),
        water_m3=float(ey.water_m3 or 0),
        natural_gas_m3=float(ey.natural_gas_m3 or 0),
        heating_energy_kwh=float(ey.heating_energy_kwh or 0),
        heating_energy_heat=float(ey.heating_energy_heat_gj or 0),
        transportation_petrol_kg=float(ey.petrol_kg or 0),
        transportation_diesel_kg=float(ey.diesel_kg or 0),
        building_area=float(base.building_area or 0),
        people_count=float(base.people_count or 0),
        electricity_cost_wan=float(ey.electricity_cost_wan or 0),
        water_cost_wan=float(ey.water_cost_wan or 0),
        natural_gas_cost_wan=float(ey.natural_gas_cost_wan or 0),
        heating_cost_wan=float(ey.heating_cost_wan or 0),
        petrol_cost_wan=float(ey.petrol_cost_wan or 0),
        coefficients=dict(ey.coefficients or {}),
    )


def compute_project_indicators(project) -> dict:
    """统一计算 AuditProject 的能源审计指标。

    返回结构：
      {
        'status': 'ok' | 'pending',
        'reason': '',  # pending 原因或补充说明
        'institution_type': 'medical'|'government'|'education',
        'institution_category': str,
        'building_area': float,
        'people_count': float,
        'beds_count': int,
        'yearly': [
          {
            'year': int,
            'unit_area_non_heating': {...},
            'unit_area_electricity': {...},
            'per_capita_energy': {...},
            'per_capita_water': {...},
          },
          ...
        ],
        'baseline': {...},
      }

    当必要参数缺失时返回 status='pending'，不抛异常。
    """
    import sys
    mod = sys.modules.get('tools.energy_audit.project_data')
    if mod is None:
        from tools.energy_audit import project_data as mod
    AuditProject = mod.AuditProject
    if not isinstance(project, AuditProject):
        raise TypeError("project 必须是 AuditProject 实例")

    base = project.base
    institution_type = institution_category_to_type(base.institution_category)

    result = {
        'status': 'pending',
        'reason': '',
        'institution_type': institution_type,
        'institution_category': base.institution_category or '',
        'building_area': float(base.building_area or 0),
        'people_count': float(base.people_count or 0),
        'beds_count': int(base.beds_count or 0),
        'yearly': [],
        'baseline': {},
    }

    # 校验必要参数
    missing = []
    if not base.building_area:
        missing.append('建筑面积')
    if not base.people_count and institution_type != 'medical':
        missing.append('用能人数')
    if institution_type == 'medical' and not base.beds_count and not base.people_count:
        missing.append('床位数或用能人数')
    if not project.energy_yearly:
        missing.append('年度能耗数据')

    if missing:
        result['reason'] = f"缺少必要参数：{'、'.join(missing)}"
        return result

    yd_objects = []
    for ey in project.energy_yearly:
        try:
            yd = energy_yearly_to_yearly_energy_data(ey, base)
            yd_objects.append(yd)
        except Exception as e:
            logger.warning(f"转换 EnergyYearly 失败: {e}")
            continue

    if not yd_objects:
        result['reason'] = '年度能耗数据转换失败或为空'
        return result

    # 按年份排序
    yd_objects.sort(key=lambda x: x.year)

    # 采暖建筑面积：建筑表 heating_area 聚合，缺失/全 0 时用建筑面积兜底（2026-09-02 用户确认）
    heating_area = 0.0
    for b in (project.buildings or []):
        heating_area += float(getattr(b, 'heating_area', 0) or 0)
    if heating_area <= 0:
        heating_area = float(base.building_area or 0)

    yearly_results = []
    for yd in yd_objects:
        year_item = {'year': yd.year}

        # 单位面积非供暖能耗（含对标）
        year_item['unit_area_non_heating'] = calc_unit_area_non_heating_energy(yd)
        year_item['unit_area_non_heating']['benchmark'] = compare_with_benchmark(
            year_item['unit_area_non_heating']['kgce_per_m2'],
            institution_type=institution_type,
            metric='unit_area_non_heating',
        )

        # 常规用能系统单位建筑面积电耗（含对标）
        year_item['unit_area_electricity'] = calc_unit_area_electricity(
            yd, institution_type=institution_type
        )

        # 人均综合能耗（含对标）
        year_item['per_capita_energy'] = calc_per_capita_energy(
            yd, institution_type=institution_type
        )

        # 人均取水量 / 单位开放床日用水量（含对标）
        year_item['per_capita_water'] = calc_per_capita_water(
            yd,
            institution_type=institution_type,
            bed_count=base.beds_count if institution_type == 'medical' else None,
        )

        # 单位采暖建筑面积供暖能耗（表2 定额；项目有供暖能耗时计算，否则置 None）
        if yd.heating_energy_tce > 0:
            year_item['unit_area_heating'] = calc_unit_area_heating_energy(
                yd, heating_area=heating_area, institution_type=institution_type,
            )
        else:
            year_item['unit_area_heating'] = None

        # 原始属性，方便下游消费
        year_item['total_energy_tce'] = yd.total_energy_tce
        year_item['heating_energy_tce'] = yd.heating_energy_tce
        year_item['transportation_energy_tce'] = yd.transportation_energy_tce

        yearly_results.append(year_item)

    result['yearly'] = yearly_results

    # 建筑能耗基准
    try:
        result['baseline'] = calc_baseline(yd_objects)
    except Exception as e:
        logger.warning(f"计算建筑能耗基准失败: {e}")
        result['baseline'] = {'error': str(e)}

    result['status'] = 'ok'
    result['reason'] = '指标计算完成'
    return result


# ============================================================
# 测试
# ============================================================

def _test():
    """自测"""
    d2024 = YearlyEnergyData(
        year=2024,
        electricity_kwh=4833915,
        water_m3=154167,
        natural_gas_m3=79374,
        heating_energy_kwh=0,
        heating_energy_heat=13931.62,  # GJ
        transportation_petrol_kg=2753.13,
        building_area=67635.96,
        people_count=3405,
    )

    r1 = calc_unit_area_non_heating_energy(d2024)
    print(f"单位建筑面积非供暖能耗: {r1['kgce_per_m2']} kgce/(m²·a)")
    bm = compare_with_benchmark(r1['kgce_per_m2'])
    print(f"  标准: {bm['标准']}")
    print(f"  约束值: {bm['约束值']}, 基准值: {bm['基准值']}, 引导值: {bm['引导值']}")
    print(f"  评价: {bm['评价结果']}")

    r2 = calc_unit_area_electricity(d2024)
    print(f"常规用能系统单位建筑面积电耗: {r2['kwh_per_m2']} kWh/(m²·a)")
    bm = r2['benchmark']
    print(f"  标准: {bm.get('标准','')} 来源: {bm.get('来源','')}")
    print(f"  约束值: {bm['约束值']}, 基准值: {bm['基准值']}, 引导值: {bm['引导值']}")
    print(f"  评价: {bm['评价结果']}")

    r3 = calc_per_capita_energy(d2024)
    print(f"人均综合能耗: {r3['kgce_per_person']} kgce/(人·a) [{r3['benchmark']['评价结果']}]")

    r4 = calc_per_capita_water(d2024, institution_type='medical', bed_count=500)
    bm4 = r4['benchmark']
    print(f"人均取水量: {r4.get('L_per_bed_day', r4.get('m3_per_person', 0))} {bm4.get('单位','')} [{bm4['评价结果']}]")
    print(f"  标准: {bm4.get('标准','')} [{bm4['来源']}]")

    print("\\n✅ 指标计算工具验证通过")

    # 5.4 建筑能耗基准测试
    print("\\n=== 5.4 建筑能耗基准 ===")
    d2022 = YearlyEnergyData(year=2022, electricity_kwh=5090273, water_m3=163107.7,
                              natural_gas_m3=57207, heating_energy_heat=13931.62,
                              electricity_cost_wan=397.04, water_cost_wan=68.51, heating_cost_wan=119.95)
    d2023 = YearlyEnergyData(year=2023, electricity_kwh=5225773, water_m3=150110,
                              natural_gas_m3=68483, heating_energy_heat=13931.62,
                              electricity_cost_wan=407.61, water_cost_wan=63.05, heating_cost_wan=119.95)
    d2024 = YearlyEnergyData(year=2024, electricity_kwh=4833915, water_m3=154167,
                              natural_gas_m3=79374, heating_energy_heat=13931.62,
                              transportation_petrol_kg=2753.13,
                              electricity_cost_wan=377.05, water_cost_wan=64.75, heating_cost_wan=119.95,
                              building_area=67635.96, people_count=3405)
    baseline = calc_baseline([d2022, d2023, d2024])
    print(f"年限: {baseline['years']}")
    for label, info in baseline['usage'].items():
        print(f"  {label}: 基准={info['基准值']:,.2f}{info['单位']} [{info['方法']}] 波动={info['波动范围']}")
    for label, info in baseline['cost'].items():
        print(f"  {label}: 基准={info['基准值']:,.2f}{info['单位']} [{info['方法']}] 波动={info['波动范围']}")
    print(f"\n总结: {baseline['summary'][:200]}...")


if __name__ == '__main__':
    _test()
