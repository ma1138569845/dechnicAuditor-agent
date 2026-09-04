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
# 照片分类（名称与 photo_manager.PHOTO_REQUIREMENTS 一一对应）
# 数据采集 agent 写入 project.images 时按此分类标注，报告按分类路由到各章节。
# ============================================================
PHOTO_CATEGORIES = (
    '建筑外观',      # 第2章 被审计单位建筑全景或主立面照片
    '各建筑外观',    # 第2章 每栋建筑单独外观照
    '管理文件/荣誉',  # 第3章 能源管理制度文件、节能荣誉证书
    '计量器具',      # 第4章 电表、水表、气表等计量仪表照片
    '能耗账单',      # 第5章 电费、水费、燃气费账单示例
    '制冷设备',      # 第6章 冷水机组/多联机外机/分体空调等
    '照明设备',      # 第6章 典型照明灯具照片
    '变压器/配电',   # 第6章 变压器室、配电柜等
    '水泵/水箱',     # 第6章 生活水泵、消防水箱等
    '厨房设备',      # 第6章 厨房设备
    '节能改造示意',  # 第7章 改造前现状照片（可选对比）
)


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
    basic_situation: str = ""          # 单位基本情况概述（来自 ts_customer_info.basic_situation）
    contact_person: str = ""           # 联系人
    contact_phone: str = ""            # 联系电话
    audit_start: str = ""              # 审计起始时间 ex: "2025年6月"
    audit_end: str = ""                # 审计结束时间 ex: "2025年7月"
    audit_period: str = ""             # 审计期 ex: "2025年1月-2026年9月"（audit_year）
    base_period: str = ""               # 基准期 ex: "2023年1月-2024年1月"（reference_year）
    data_start: str = ""               # 数据起始年份 ex: "2022-01-01"
    data_end: str = ""                 # 数据结束年份 ex: "2024-12-31"
    building_area: float = 0           # 总建筑面积 m²
    people_count: int = 0              # 用能人数/职工数
    beds_count: int = 0                # 床位数（医院用）
    admin_affiliation: str = ""        # 行政归属 ex: "山东省卫生健康委员会"
    department_count: str = ""         # 内设机构/科室 ex: "23个临床科室、7个医技科室"
    project_manager: str = ""          # 审计项目负责人
    auditor: str = ""                  # 审计机构名称
    # ---- 审计机构信息（能源审计机构信息表数据源）----
    # 来源: ts_register_info（dept_name/address）；负责人/联系方式由用户提问提供，
    # 表内 contact/mobile 仅作提问预填参考（audit_org_*_hint）。
    audit_org_name: str = ""           # 审计机构名称 — ts_register_info.dept_name
    audit_org_address: str = ""        # 审计机构详细地址 — ts_register_info.address（缺失→向用户提问）
    audit_org_contact: str = ""        # 审计机构负责人（用户提问提供，不静默【待补充】）
    audit_org_phone: str = ""          # 审计机构联系方式（用户提问提供，不静默【待补充】）
    audit_org_contact_hint: str = ""   # ts_register_info.contact（提问预填参考）
    audit_org_phone_hint: str = ""     # ts_register_info.mobile（提问预填参考）
    report_date: str = ""              # 报告日期 ex: "2026年6月"
    province: str = "山东"             # 所在省份（用于规章检索与同类报告匹配）
    city: str = ""                     # 地市，如 烟台
    district: str = ""                 # 区县，如 芝罘 / 经济技术开发区


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
    heating_energy_kwh: float = 0  # 供暖电耗 kWh（供暖循环泵/风机，dt=4 挂电记录；须从总电量剔除）
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
    img_ids: List[str] = field(default_factory=list)  # 设备照片附件 file id（设备分表 _img 列，供第6章照片分类采集）
    energy_rating: str = ""            # 能效等级
    usage_years: str = ""              # 使用年限
    location: str = ""                 # 所在位置
    remark: str = ""                   # 设备备注信息
    independent_metering: str = ""     # 独立计量 — is_metering（有/无/空=该表无此字段或未填）
    independent_metering_desc: str = ""  # 独立计量情况 — metering_desc
    independent_metering_ratio: str = ""  # 独立计量比例 — metering_ratio
    independent_metering_time: str = ""   # 独立计量时间 — metering_time


@dataclass
class MeteringInfo:
    """计量器具信息"""
    has_monitoring_system: bool = False # 是否有能耗监测系统
    has_household_metering: bool = False# 是否有分户计量
    has_separate_metering: bool = False # 是否有设备单独计量（场景表独立计量电表）
    electric_meters: int = 0           # 电表数量
    water_meters: int = 0              # 水表数量
    gas_meters: int = 0                # 气表数量
    heat_meters: int = 0               # 热量表数量
    independent_light_socket: bool = False   # 照明和插座用电独立计量
    independent_power: bool = False          # 动力用电独立计量
    independent_aircon: bool = False         # 空调用电独立计量
    independent_special: bool = False        # 特殊用电独立计量
    independent_other_special: str = ""      # 其他特殊用电独立计量描述
    independent_construction_elec: bool = False  # 施工用电独立计量
    independent_construction_water: bool = False # 施工用水独立计量
    has_shared_office: bool = False          # 是否合署办公 — ts_institution_scene.mode (1是/2否)
    has_household_payment: bool = False      # 分户缴费 — split_payment (1是/2否)
    install_position: int = 0                # 计量器具安装位置 1按要求/2未按要求
    position_reasonable: int = 0             # 位置合理性 1合理/2不合理
    metering_standard: int = 0               # 计量规范性 1非常规范/2一般规范/3不规范
    partition_payment: bool = False          # 分区缴费 — partition_payment (1是/2否)
    electric_pay_type: str = ""              # 电费收费方式
    service_staff: str = ""                  # 第三方服务人员
    scene_desc: str = ""                     # 现场描述
    ledger_files: str = ""                   # 计量器具台账附件文件 id（逗号分隔，电/水表记录拼接）
    ledger_text: str = ""                    # 台账文档下载后提取的文字（enrich_meter_ledger 回填）
    record_attach_id: int = 0                # 运行记录抽样文件 id（scene.record_attach_id）
    aircon_staff_num: int = 0                # 空调系统运维人数（4.2 专职人员判定）
    light_staff_num: int = 0                 # 照明系统运维人数
    power_room_staff_num: int = 0            # 配电室运维人数


@dataclass
class SharedOfficeUnit:
    """合署办公单位 — ts_institution_scene_mode"""
    dept_name: str = ""                    # 合署单位名称 — mode_dept_name
    reason: str = ""                       # 合署原因 — mode_reason
    pay_type: str = ""                     # 缴费方式 — pay_type
    start_time: str = ""                   # 开始日期
    end_time: str = ""                     # 结束日期
    building: str = ""                     # 使用建筑/楼层 — mode_build
    area: float = 0                        # 使用面积 m² — mode_area
    ratio: float = 0                       # 使用建筑比例 — mode_ratio
    independent_metering: str = ""         # 独立计量 — is_metering（有/无/空）


SHARED_OFFICE_METERED = "有合署办公且实现了合办公单位独立计量"
SHARED_OFFICE_UNMETERED = "有合署办公，但未实现各办公单位独立计量"
_SHARED_OFFICE_YES = {"有", "是", "1", 1, True}


def _shared_office_unit_metered(val) -> bool:
    if val in _SHARED_OFFICE_YES:
        return True
    return str(val).strip() in {"有", "是", "1"} if val is not None else False


def shared_office_metering_sentence(has_shared_office, shared_offices=None) -> str:
    """第4章合署办公独立计量固定句。合署办公为否时返回空串，不回显「合署办公：是/否」。

    - 列表中只要有一个独立计量为是/有 → 有合署办公且实现了合办公单位独立计量
    - 全部为否/无（或无明细）→ 有合署办公，但未实现各办公单位独立计量
    """
    if not has_shared_office:
        return ""
    units = shared_offices or []
    for unit in units:
        val = unit.get("independent_metering") if isinstance(unit, dict) else getattr(
            unit, "independent_metering", ""
        )
        if _shared_office_unit_metered(val):
            return SHARED_OFFICE_METERED
    return SHARED_OFFICE_UNMETERED


@dataclass
class ManagementInfo:
    """能源管理信息（第3章）"""
    management_org: str = ""           # 管理机构描述
    management_policy: str = ""        # 管理方针
    management_goals: str = ""         # 管理目标
    honors: str = ""                   # 已获节能荣誉


@dataclass
class EnergySaving:
    """公共机构节能管理信息 —— 对应 PG 表 ts_institution_energy_saving

    所有字段对齐 ts_institution_energy_saving 表结构，0/1 标记字段沿用 int 类型
    （1:有/是, 0:无/否），与 BuildingInfo 中 wallwarm_change 等字段风格一致。
    """
    statistical_year: int = 0           # 统计年
    energy_management: Optional[int] = None  # 能源管理制度 (1:有, 0:无, None:未填写)
    energy_pain_points: str = ""        # 目前能源利用痛点
    management_files: str = ""          # 能源管理制度文件ID，多个以逗号分隔
    management_file_images: List[str] = field(default_factory=list)  # 管理制度附件解析下载后的图片本地路径
    has_awards: int = 0                 # 节能相关奖项 (1:有, 0:无)
    award_name: str = ""                # 节能奖项名称
    award_certificate: str = ""         # 节能奖项证明文件ID
    award_certificate_images: List[str] = field(default_factory=list)  # 奖项证明附件解析下载后的图片本地路径
    other_measures: str = ""            # 其他节能改造措施
    third_party_system: str = ""        # 第三方托管能源系统
    charging_pile: int = 0              # 充电桩 (1:有, 0:无)
    charging_settlement: str = ""       # 充电桩结算方式
    charging_installation: str = ""     # 充电桩安装方式
    third_party_outsource: int = 0      # 第三方外包用能系统 (1:有, 0:无)
    outsource_content: str = ""         # 第三方外包用能系统内容
    outsource_settlement: str = ""      # 第三方外包用能系统结算方式
    lighting_replacement: int = 0       # 照明灯具更换 (1:有, 0:无)
    ac_replacement: int = 0             # 空调设备更换 (1:有, 0:无)
    water_saving_fixture_replacement: int = 0  # 节水型卫生器具更换 (1:有, 0:无)
    central_ac_control: int = 0         # 中央空调系统增加集中控制 (1:有, 0:无)


@dataclass
class IndoorEnv:
    """室内环境检测"""
    test_date: str = ""
    test_conditions: str = ""
    rooms: List[dict] = field(default_factory=list)  # [{room, temp, humidity, co2, illumination, voc, pm25, remark}]


@dataclass
class TeamMember:
    """审计组人员（能源审计组人员名单）

    对齐 ts_project_audit_user（position 在报告"组内职务"列展示，
    存储审计负责人/审计联络人/成员等职务）。
    """
    role: str = ""                      # 组内职务 — position（审计负责人/审计联络人/成员）
    name: str = ""                      # 姓名
    education: str = ""                 # 学历 — degree
    certification: str = ""             # 所获资质 — qualifications
    major: str = ""                     # 专业


@dataclass
class CoopMember:
    """被审计单位配合人员（能源审计配合人员名单）

    对齐 ts_project_audited_user（group_position=组内职务，position=职务）。
    """
    role: str = ""                      # 组内职务 — group_position（组长/联系人等）
    dept: str = ""                      # 部门 — department
    name: str = ""                      # 姓名
    gender: str = ""                    # 性别 — sex
    position: str = ""                  # 职务 — position（主任/科长等）


@dataclass
class ImageItem:
    """项目照片（带分类，供报告章节路由与照片完整性校验）

    category 取 PHOTO_CATEGORIES 之一；空字符串表示未分类（兼容旧数据，报告兜底进第2章）。
    """
    path: str                          # 图片文件路径（本地绝对路径）
    category: str = ""                 # 照片分类（PHOTO_CATEGORIES）
    caption: str = ""                  # 图注（可选，报告内展示用）


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
    energy_meter: List[dict] = field(default_factory=list)  # 表具计量信息（ts_institution_energy_meter 原始记录，按 data_type/statistical_year 版本归一后）
    shared_offices: List[SharedOfficeUnit] = field(default_factory=list)  # 合署办公明细
    management: ManagementInfo = field(default_factory=ManagementInfo)
    energy_saving: List[EnergySaving] = field(default_factory=list)  # 节能管理信息（ts_institution_energy_saving）
    audit_team: List[TeamMember] = field(default_factory=list)      # 审计组人员（ts_project_audit_user）
    cooperation: List[CoopMember] = field(default_factory=list)     # 配合人员（ts_project_audited_user）
    indoor_env: IndoorEnv = field(default_factory=IndoorEnv)
    images: List[ImageItem] = field(default_factory=list)  # 照片列表（带分类）
    data_sources: Dict[str, str] = field(default_factory=dict)  # 字段→来源追溯
    indicators: Dict[str, Any] = field(default_factory=dict)   # 预计算能源审计指标
    _version: str = "1.3.0"            # 数据格式版本（images 升级为带分类的 ImageItem）


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


def total_building_area(buildings: List[dict]) -> float:
    """各建筑面积合计（m²），None / 缺字段按 0 计。

    采集（pg_collector）与质检（data_collection_cli）多处需要"建筑合计面积"，
    统一收敛到此，避免 sum(b.get('area', 0)) 散落多个文件。
    """
    return sum(b.get('area', 0) or 0 for b in buildings)


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

    # 裸 dict（原始记录，如 energy_meter / rooms 字段类型为 List[dict]）：原样透传
    if cls is dict:
        return data

    # 处理 List[SomeDataclass] / List[dict]
    origin = getattr(cls, '__origin__', None)
    if origin is list or origin is List:
        item_cls = cls.__args__[0]
        # List[dict]：原 dict 元素直接透传（勿按 dataclass 递归）
        if item_cls is dict:
            return list(data)
        result = []
        for item in data:
            # 兼容旧数据：images 为纯字符串路径 → 转为 ImageItem(path=...)
            if isinstance(item, str) and hasattr(item_cls, '__dataclass_fields__') \
                    and 'path' in item_cls.__dataclass_fields__:
                result.append(item_cls(path=item))
            else:
                result.append(_dict_to_dataclass(item, item_cls))
        return result

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
