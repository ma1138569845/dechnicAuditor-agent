"""
能源审计项目数据模型 —— dataCollection agent 输出规范

位置: ~/projects/energy-audit/<project_name>/data.json
追溯: 每个字段记录 source (DB/Excel/用户) + timestamp

作者: 马天远 | 版本: 2.0.0 | 日期: 2026-07-31

prod - serial number - 1
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
import json, os, shutil, uuid
from pathlib import Path


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ProjectBase:
    """项目基本信息"""
    name: str                          # 项目名称 ex: "莘县县政府能源审计"
    unit_name: str                     # 被审计单位全称
    unit_short: str = ""               # 被审计单位简称
    address: str = ""                  # 地址
    unit_type: str = "公共机构"          # 审计类型: 公共机构/公共建筑/工业企业
    institution_category: str = ""     # 机构类别: 医疗/教育/党政机关/场馆/体育/政务服务中心
    specific_type: str = ""            # 具体类型: 医院/大学/法院/机关...
    contact_person: str = ""           # 联系人
    contact_phone: str = ""            # 联系电话
    audit_start: str = ""              # 审计起始时间 ex: "2025年6月"
    audit_end: str = ""                # 审计结束时间 ex: "2025年7月"
    data_start: str = ""               # 数据起始年份 ex: "2022-01-01"
    data_end: str = ""                 # 数据结束年份 ex: "2024-12-31"
    building_area: float = 0           # 总建筑面积 m²
    people_count: int = 0              # 用能人数/职工数
    beds_count: int = 0                # 床位数（医院用）
    admin_affiliation: str = ""        # 行政归属 ex: "山东省卫生健康委员会"
    department_count: str = ""         # 内设机构/科室 ex: "23个临床科室、7个医技科室"
    project_manager: str = ""          # 审计项目负责人
    auditor: str = ""                  # 审计机构名称
    report_date: str = ""              # 报告日期 ex: "2026年6月"
    province: str = "山东"             # 所在省份（用于规章检索）


@dataclass
class BuildingInfo:
    """建筑信息 —— 对应 PG 表 ts_institution_build

    所有字段都对齐 ts_institution_build 表结构，新增字段均带默认值，
    保证对已有项目数据（缺少新字段）的向后兼容。
    """
    # ---- 基本信息 ----
    name: str                          # 建筑名称 — build_name
    address: str = ""                  # 地址 — address
    year: int = 0                      # 竣工年份 — build_year (int，保留兼容性)
    function: str = ""                 # 建筑功能 — build_func
    function_zoning: str = ""          # 建筑功能分区 — build_func_region
    other_function_zoning: str = ""    # 其他建筑功能分区 — other_build_func_region
    floors: str = ""                   # 层数描述 (合成字段：地上X层地下Y层)
    up_floor: int = 0                  # 地上层数 — up_floor
    down_floor: int = 0                # 地下层数 — down_floor
    height: str = ""                   # 建筑高度 — build_height (numeric 保留原字符串便于精度显示)
    orientation: str = ""              # 建筑朝向 — build_face
    area: float = 0                    # 建筑面积 m² — build_area
    use_area: float = 0                # 使用面积 m² — use_area
    cooling_area: float = 0            # 供冷面积 m² — cold_area
    heating_area: float = 0           # 供热面积 m² — heat_area
    cold_terminal_area: float = 0      # 供冷末端面积 m² — cold_terminal_area
    heat_terminal_area: float = 0      # 供热末端面积 m² — heat_terminal_area

    # ---- 建筑结构 ----
    structure: str = ""                # 结构形式 — stru_type
    other_structure: str = ""          # 其他结构形式 — other_stru_type
    wall_body_material: str = ""       # 外墙主体材料 — wallbody_thickness
    other_wall_body_material: str = "" # 其他外墙主体材料 — other_wallbody_thickness

    # ---- 围护结构（透明/不透明） ----
    window_type: str = ""              # 建筑透明维护结构 — wallwin_type
    other_window_type: str = ""        # 其他透明维护结构 — other_wallwin_type
    insulation: str = ""               # 外墙保温形式 — wallwarm_type
    other_insulation: str = ""         # 其他外墙保温形式 — other_wallwarm_type
    wall_material: str = ""            # 外墙保温材料 — warm_material
    other_warm: str = ""               # 其他保温材料 — other_warm
    warm_thickness: str = ""          # 外墙保温材料厚度 — warm_thickness
    warm_state: str = ""               # 外墙保温材料现状 — warm_state
    wall_insulation_change: int = 0    # 外墙保温审计周期内变化 — wallwarm_change (0:无 1:有)

    # ---- 屋面保温 ----
    roof_insulation: str = ""          # 有无屋面保温 — is_roomwarm ('有'/'无')
    roof_insulation_material: str = "" # 屋面保温材料 — roomwarm_material
    roof_insulation_thickness: str = "" # 屋面保温材料厚度 — roomwarm_thickness
    roof_insulation_state: str = ""    # 屋面保温材料现状 — roomwarm_state
    roof_insulation_change: int = 0    # 屋面保温审计周期内变化 — roomwarm_change (0:无 1:有)

    # ---- 遮阳 ----
    sunshade_type: str = ""            # 建筑遮阳形式 — build_sunshade ('外'/'中'/'内')
    sunshade_material: str = ""        # 遮阳材料 — sunshade_thickness
    sunshade_install: str = ""         # 遮阳安装形式 — sunshade_install

    # ---- 暖通空调 ----
    cooling_source: str = ""           # 夏季空调冷源 — cold_source
    cold_time: str = ""                # 供冷时间 — cold_time
    cold_date: str = ""                # 每日供冷时间 — cold_date (08:00:00~18:00:00)
    heating_source: str = ""           # 冬季供暖热源 — heat_source
    heat_time: str = ""                # 供暖时间 — heat_time
    heat_date: str = ""                # 每日供暖时间 — heart_date
    cooling_terminal: str = ""         # 夏季空调末端 — air_type
    heating_terminal: str = ""         # 冬季供暖末端 — heat_type

    # ---- 水系统 ----
    water_system: str = ""             # 建筑给水系统 — water_supply
    fire_system: str = ""              # 消防给水系统 — fire_water_supply
    hot_water: str = ""                # 生活热水系统 — hot_water_supply

    # ---- 运行/计量/监管 ----
    monitoring: str = ""               # 能耗在线监测系统 — energy_system ('有'/'无')
    storey_metrology: str = ""         # 楼层单独计量 — storey_metrology ('是'/'否')
    run_time: str = ""                 # 建筑运行时间 — build_run_time

    # ---- 使用期限 ----
    begin_date: str = ""               # 使用开始时间 — use_begin_date
    end_date: str = ""                 # 使用结束时间 — use_end_date

    # ---- 地下车库 ----
    garage: str = ""                   # 地下车库 — garage ('有'/'无')
    garage_area: float = 0             # 地下车库面积 m² — garage_area


@dataclass
class EnergyYearly:
    """年度能耗数据（含月度明细，可选）

    合署办公场景下：
      - 标准字段（electricity_kwh/water_m3/...）= 本单位实际用量（unit_total_value）
      - building_* 字段 = 整栋建筑的合署办公总量（building_total_value），仅合署时有值
    """
    year: int
    electricity_kwh: float = 0
    water_m3: float = 0
    natural_gas_m3: float = 0
    heating_energy_heat_gj: float = 0
    petrol_kg: float = 0
    diesel_kg: float = 0
    electricity_cost_wan: float = 0
    water_cost_wan: float = 0
    natural_gas_cost_wan: float = 0
    heating_cost_wan: float = 0
    petrol_cost_wan: float = 0
    diesel_cost_wan: float = 0
    # 月度明细（可选，用于生成逐月折线图）
    monthly_electricity_kwh: Optional[List[float]] = None
    monthly_water_m3: Optional[List[float]] = None
    monthly_natural_gas_m3: Optional[List[float]] = None
    # 整栋建筑合署办公总量（合署场景下追溯用，非合署时为 0）
    building_electricity_kwh: float = 0
    building_water_m3: float = 0
    building_natural_gas_m3: float = 0
    building_heating_energy_heat_gj: float = 0
    building_petrol_kg: float = 0
    building_diesel_kg: float = 0
    # 当年各类能源折标煤系数（kgce/kWh、kgce/t、kgce/m³ 等），key 为能源类型
    coefficients: Dict[str, float] = field(default_factory=dict)
    # 各能源类型折标煤系数来源，例如 'PG' / 'Config' / 'Excel' / 'default'
    coefficient_sources: Dict[str, str] = field(default_factory=dict)


@dataclass
class EnergyMonthly:
    """逐月能耗（用于第5章图表）"""
    year: int
    month: int
    electricity_kwh: float = 0
    water_m3: float = 0
    natural_gas_m3: float = 0


@dataclass
class Equipment:
    """设备信息"""
    name: str                          # 设备名称
    category: str = ""                 # 分类: 空调/照明/电梯/热水器/厨房/变压器
    spec: str = ""                     # 规格/功率
    quantity: int = 0                  # 数量
    energy_rating: str = ""            # 能效等级
    usage_years: str = ""              # 使用年限
    location: str = ""                 # 所在位置
    remark: str = ""                   # 设备备注信息


@dataclass
class MeteringInfo:
    """计量器具信息"""
    has_monitoring_system: bool = False # 是否有能耗监测系统
    has_household_metering: bool = False# 是否有分户计量
    has_separate_metering: bool = False # 是否有设备单独计量
    electric_meters: int = 0           # 电表数量
    water_meters: int = 0              # 水表数量
    gas_meters: int = 0                # 气表数量
    heat_meters: int = 0               # 热量表数量


@dataclass
class ManagementInfo:
    """能源管理信息（第3章）"""
    management_org: str = ""           # 管理机构描述
    management_policy: str = ""        # 管理方针
    management_goals: str = ""         # 管理目标
    honors: str = ""                   # 已获节能荣誉


@dataclass
class IndoorEnv:
    """室内环境检测"""
    test_date: str = ""
    test_conditions: str = ""
    rooms: List[dict] = field(default_factory=list)  # [{room, temp, humidity, co2, illumination, voc, pm25, remark}]


# ============================================================
# 顶层项目数据
# ============================================================
@dataclass
class AuditProject:
    """完整项目数据"""
    project_id: str = ""               # 自动生成
    created_at: str = ""               # 创建时间
    updated_at: str = ""               # 最后更新时间
    base: ProjectBase = field(default_factory=ProjectBase)
    buildings: List[BuildingInfo] = field(default_factory=list)
    energy_yearly: List[EnergyYearly] = field(default_factory=list)
    energy_monthly: List[EnergyMonthly] = field(default_factory=list)
    equipment: List[Equipment] = field(default_factory=list)
    metering: MeteringInfo = field(default_factory=MeteringInfo)
    management: ManagementInfo = field(default_factory=ManagementInfo)
    indoor_env: IndoorEnv = field(default_factory=IndoorEnv)
    images: List[str] = field(default_factory=list)  # 图片文件路径列表
    data_sources: Dict[str, str] = field(default_factory=dict)  # 字段→来源追溯
    indicators: Dict[str, Any] = field(default_factory=dict)   # 预计算能源审计指标
    _version: str = "1.1.0"            # 数据格式版本（新增 EnergyYearly.coefficients / coefficient_sources）


# ============================================================
# 数据来源解析辅助函数
# ============================================================

def resolve_with_source(field_name: str, *candidates) -> Tuple[Any, str]:
    """按优先级解析字段值并记录数据来源。

    candidates: [(source_name, value_or_dict), ...]
      - value 为 dict 时，从中取 field_name；
      - value 为其它类型时，直接使用。
    返回: (resolved_value, source_name)

    优先级规则：第一个非 None / 非空字符串 / 非 0 / 非 False 的值获胜；
    全部未命中时返回最后一个候选值，来源标记为 'default'。
    """
    for source_name, value in candidates:
        if isinstance(value, dict):
            v = value.get(field_name)
        else:
            v = value
        if v not in (None, '', 0, False):
            return v, source_name
    last_value = candidates[-1][1] if candidates else None
    if isinstance(last_value, dict):
        last_value = last_value.get(field_name)
    return last_value, 'default'


class SourceResolver:
    """辅助按优先级解析字段并统一记录数据来源。"""

    def __init__(self):
        self.values: Dict[str, Any] = {}
        self.sources: Dict[str, str] = {}

    def resolve(self, field_name: str, *candidates) -> Any:
        value, source = resolve_with_source(field_name, *candidates)
        self.values[field_name] = value
        self.sources[field_name] = source
        return value


def first_non_empty_source(*candidates) -> str:
    """返回第一个非空（非 None / 空字符串 / 0 / False / 空列表 / 空 dict）候选的来源名，
    全部未命中时返回 'default'。
    """
    for source_name, value in candidates:
        if value not in (None, '', 0, False) and value != [] and value != {}:
            return source_name
    return 'default'


def is_valid_coefficient(value) -> bool:
    """判断一个折标煤系数是否有效：非 None、非空字符串、可转为 float 且大于 0。"""
    if value is None or value == '':
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


# ============================================================
# 持久化层
# ============================================================

_PROJECTS_ROOT = Path.home() / "projects" / "energy-audit"


def save_project(project: AuditProject) -> str:
    """保存项目数据到 ~/projects/energy-audit/<name>/data.json"""
    if not project.project_id:
        project.project_id = datetime.now().strftime("P%Y%m%d_%H%M%S_") + str(uuid.uuid4())[:8]
    project.created_at = project.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    safe_name = project.base.unit_name or "unnamed"
    data_dir = _PROJECTS_ROOT / safe_name
    data_dir.mkdir(parents=True, exist_ok=True)

    data_path = data_dir / "data.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(project), f, ensure_ascii=False, indent=2, default=str)

    print(f"[datacollection] 数据已保存: {data_path}")
    return str(data_path)


def _dict_to_dataclass(data: dict, cls: type) -> Any:
    """递归把 dict/list 转成对应 dataclass。"""
    if data is None:
        return cls() if not getattr(cls, '__origin__', None) else None

    # 处理 List[SomeDataclass]
    origin = getattr(cls, '__origin__', None)
    if origin is list or origin is List:
        item_cls = cls.__args__[0]
        return [_dict_to_dataclass(item, item_cls) for item in data]

    # 普通 dataclass
    if isinstance(data, dict):
        field_types = {}
        for f in cls.__dataclass_fields__.values():
            field_types[f.name] = f.type

        kwargs = {}
        for k, v in data.items():
            if k not in field_types:
                continue
            ft = field_types[k]
            # 可选类型解包
            if getattr(ft, '__origin__', None) is Union:
                args = ft.__args__
                # Optional[X] = Union[X, None]
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    ft = non_none[0]
            # 是 dataclass 或容器则递归
            if hasattr(ft, '__dataclass_fields__'):
                kwargs[k] = _dict_to_dataclass(v, ft)
            elif getattr(ft, '__origin__', None) in (list, List):
                kwargs[k] = _dict_to_dataclass(v, ft)
            else:
                kwargs[k] = v
        return cls(**kwargs)

    return data


def load_project(unit_name: str) -> Optional[AuditProject]:
    """按单位名加载项目（递归还原 dataclass）"""
    data_path = _PROJECTS_ROOT / unit_name / "data.json"
    if not data_path.exists():
        return None

    with open(data_path, encoding='utf-8') as f:
        raw = json.load(f)

    return _dict_to_dataclass(raw, AuditProject)


def list_projects() -> List[dict]:
    """列出所有已保存的项目"""
    if not _PROJECTS_ROOT.exists():
        return []
    projects = []
    for p in _PROJECTS_ROOT.iterdir():
        data_file = p / "data.json"
        if data_file.exists():
            with open(data_file, encoding='utf-8') as f:
                raw = json.load(f)
            base = raw.get('base', {})
            projects.append({
                'name': base.get('unit_name', p.name),
                'short': base.get('unit_short', ''),
                'type': base.get('unit_type', ''),
                'updated': raw.get('updated_at', ''),
                'path': str(data_file),
            })
    return projects
