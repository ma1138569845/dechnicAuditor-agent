"""
能源审计PostgreSQL数据查询工具
适配 dc_energy_audit2 数据库实际表结构

prod - serial number - 2
"""

import psycopg2
import psycopg2.extras
from typing import Dict, List

from .db_config import get_pg_config



# ============================================================
# PgDataQuery — PostgreSQL 通用查询器
# ============================================================

class PgDataQuery:
    """PostgreSQL能源审计数据查询器"""

    def __init__(self, config: Dict = None):
        # 连接配置统一走 db_config 解析链（参数 > env > config.yaml > 默认值），
        # 密码不得硬编码，见 db_config.py 模块 docstring。
        self.config = get_pg_config(config)
        self.connection = None
        self.cursor = None

    def connect(self):
        """建立数据库连接"""
        self.connection = psycopg2.connect(**self.config)
        self.connection.autocommit = True  # 必须：否则一次 SQL 异常后事务 aborted，后续查询全报 InFailedSqlTransaction
        self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def disconnect(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def _execute(self, query: str, params: tuple = None) -> List[Dict]:
        """执行查询"""
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    # ---------- 健康检查 ----------

    def ping(self) -> bool:
        """测试数据库连接是否可用。返回 True/False，不抛异常。"""
        try:
            self._execute("SELECT 1")
            return True
        except Exception:
            return False

    # ========== 客户信息 ==========

    def get_customer_info(self, customer_id: int = None) -> List[Dict]:
        """获取 ts_customer_info"""
        query = """SELECT id, credit_code, customer_name, address,
                    contact, mobile, email, industry_id, district_id,
                    field_type, customer_func, children_func, climate_type, basic_situation
                 FROM ts_customer_info WHERE (deleted IS NULL OR deleted = 0)"""
        params = []
        if customer_id:
            query += " AND id = %s"; params.append(customer_id)
        return self._execute(query, tuple(params))

    @staticmethod
    def district_id_to_province_code(district_id) -> str:
        """行政区划代码 → 省级代码。例：370611 → 370000。"""
        digits = ''.join(ch for ch in str(district_id or '') if ch.isdigit())
        if len(digits) < 2:
            return ''
        return f"{digits[:2]}0000"

    @staticmethod
    def short_province_name(name: str) -> str:
        """省级全称缩短为规章检索用简称。例：山东省 → 山东。"""
        text = (name or '').strip()
        if not text:
            return ''
        for suffix in (
            '特别行政区', '维吾尔自治区', '壮族自治区', '回族自治区',
            '自治区', '省', '市',
        ):
            if text.endswith(suffix) and len(text) > len(suffix):
                return text[:-len(suffix)]
        return text

    def get_area_by_code(self, area_code: str) -> Dict | None:
        """system_bd_areadict 按 f_areacode 查一条。"""
        code = str(area_code or '').strip()
        if not code:
            return None
        rows = self._execute(
            """SELECT f_areacode, f_areaname, f_areasupcode, f_type, f_memo
               FROM system_bd_areadict WHERE f_areacode = %s LIMIT 1""",
            (code,),
        )
        return rows[0] if rows else None

    @staticmethod
    def district_id_to_city_code(district_id) -> str:
        """行政区划代码 → 地市级代码。例：370611 → 370600。"""
        digits = ''.join(ch for ch in str(district_id or '') if ch.isdigit())
        if len(digits) < 4:
            return ''
        return f"{digits[:4]}00"

    @staticmethod
    def short_city_name(name: str) -> str:
        text = (name or '').strip()
        if not text:
            return ''
        for suffix in ('自治州', '地区', '盟', '市'):
            if text.endswith(suffix) and len(text) > len(suffix):
                return text[:-len(suffix)]
        return text

    @staticmethod
    def short_district_name(name: str) -> str:
        text = (name or '').strip()
        if not text:
            return ''
        if any(token in text for token in ('开发区', '新区', '高新区', '保税区', '园区')):
            return text
        for suffix in ('区', '县', '旗'):
            if text.endswith(suffix) and len(text) - len(suffix) >= 2:
                return text[:-len(suffix)]
        return text

    def get_admin_division_by_district_id(self, district_id) -> dict:
        """district_id → 省/地市/区县简称与全称。查不到的层级为空字符串。"""
        empty = {
            "province": "",
            "city": "",
            "district": "",
            "province_full": "",
            "city_full": "",
            "district_full": "",
        }
        digits = ''.join(ch for ch in str(district_id or '') if ch.isdigit())
        if len(digits) < 2:
            return empty

        def _name(code: str) -> str:
            area = self.get_area_by_code(code)
            if not area:
                return ''
            return str(area.get('f_areaname') or '').strip()

        province_full = _name(self.district_id_to_province_code(digits))
        city_full = _name(self.district_id_to_city_code(digits))
        district_code = digits[:6] if len(digits) >= 6 else digits
        district_full = _name(district_code)
        if district_full and district_full in {province_full, city_full}:
            district_full = ''
        if city_full and city_full == province_full:
            # 直辖市：地市与省同名时仍保留市名，便于路径匹配。
            pass
        return {
            "province_full": province_full,
            "city_full": city_full,
            "district_full": district_full,
            "province": self.short_province_name(province_full),
            "city": self.short_city_name(city_full),
            "district": self.short_district_name(district_full) if district_full else '',
        }

    def get_province_name_by_district_id(self, district_id) -> str:
        """ts_customer_info.district_id → 省级名称（如 山东省）。"""
        return self.get_admin_division_by_district_id(district_id).get("province_full") or ""

    # ========== 审计项目 ==========

    def get_institution_project(self, project_id: int = None, audited_name: str = None) -> List[Dict]:
        """获取 ts_institution_project。

        Args:
            project_id: 按项目 ID 精确查询。
            audited_name: 按被审计单位名称模糊查询（ILIKE）。
        """
        query = """SELECT id, audited_name, audited_person, audited_tel,
                    commission_person, commission_tel, audit_dept_name,
                    audit_dept_person, audit_dept_tel,
                    audit_year, reference_year, start_time, end_time, create_time,
                    status, customer_id, remark, energy_codes, audit_template
                 FROM ts_institution_project WHERE (deleted IS NULL OR deleted = 0)"""
        params = []
        if project_id:
            query += " AND id = %s"; params.append(project_id)
        if audited_name:
            query += " AND audited_name ILIKE %s"; params.append(f"%{audited_name}%")
        query += " ORDER BY create_time DESC"
        return self._execute(query, tuple(params))

    def find_project_by_name(self, project_name: str) -> Dict | None:
        """按名称模糊匹配最新一个项目，返回单条记录（含 customer_id）。"""
        rows = self.get_institution_project(audited_name=project_name)
        return rows[0] if rows else None

    # ========== 标准规范 ==========

    def get_energy_standards(self) -> List[Dict]:
        """获取 ts_energy_standard 能源折标系数"""
        return self._execute("""SELECT id, energy_code, energy_name, energy_unit,
                                standard_base, begin_time, end_time
                             FROM ts_energy_standard WHERE deleted = 0
                             ORDER BY energy_code""")

    # ========== 机构能耗（新两表结构） ==========

    @staticmethod
    def period_to_months(period_code: str) -> List[int]:
        """period_code → 覆盖的月份列表。

        示例（与 granularity 语义一致）：
          '01'     → [1]            （粒度=月）
          '01~02'  → [1, 2]         （粒度=双月）
          '01~03'  → [1, 2, 3]      （粒度=季度）
          '01~06'  → [1..6]         （粒度=半年）
        """
        s = (period_code or '').strip()
        if '~' in s:
            lo, _, hi = s.partition('~')
            if lo.isdigit() and hi.isdigit():
                return list(range(int(lo), int(hi) + 1))
            return []
        return [int(s)] if s.isdigit() else []

    @staticmethod
    def expand_periods_to_monthly(periods: List[tuple]) -> List[float]:
        """将 [(period_code, energy_value), ...] 展开为 12 个月列表。

        粒度非月度时按覆盖月数均摊（period_value / len(months)），
        保持与下游 monthly_xxx_kwh 12 元素列表契约兼容。
        """
        monthly = [0.0] * 12
        for code, value in periods:
            months = PgDataQuery.period_to_months(code)
            if not months or value is None:
                continue
            per_month = float(value) / len(months)
            for m in months:
                if 1 <= m <= 12:
                    monthly[m - 1] = per_month
        return monthly

    def get_institution_energy(self, customer_id: int = None, year: str = None, data_type: int = None) -> List[Dict]:
        """获取机构能耗数据（新结构 main + data 两表）。

        返回每条主表记录 + 按粒度展开的 12 个月列表，字段与旧单表结构对齐：
        value1..value12 由 ts_institution_energy_data 按 period_code 展开生成。

        版本归一规则：同一 (year, data_type, energy_code) 只返回一条 ——
        优先取草稿（is_draft=1，最新编辑数据）；无草稿时取正式版本（version_code 大者优先）
        草稿优先（is_draft=1=最新编辑数据）；无草稿时取正式版本（version_code 大者优先）。
        """
        query = """
            SELECT m.id, m.year, m.data_type, m.energy_code, m.energy_name,
                   m.energy_unit, m.standard_coal_coefficient,
                   m.total_value AS building_total_value,
                   m.real_value AS unit_total_value,
                   m.granularity, m.customer_id,
                   d.period_code, d.energy_value
            FROM ts_institution_energy_main m
            LEFT JOIN ts_institution_energy_data d ON d.main_id = m.id
            WHERE (m.deleted IS NULL OR m.deleted = 0)
              AND m.id IN (
                  SELECT DISTINCT ON (mm.year, mm.data_type, mm.energy_code) mm.id
                  FROM ts_institution_energy_main mm
                  WHERE (mm.deleted IS NULL OR mm.deleted = 0)"""
        params = []
        if customer_id:
            query += " AND m.customer_id = %s"; params.append(customer_id)
        if year:
            query += " AND m.year = %s"; params.append(year)
        if data_type is not None:
            query += " AND m.data_type = %s"; params.append(data_type)
        # 子查询镜像同样过滤条件（版本归一：草稿优先，无草稿时版本号大者优先）
        sub_filters = ""
        sub_params = []
        if customer_id:
            sub_filters += " AND mm.customer_id = %s"; sub_params.append(customer_id)
        if year:
            sub_filters += " AND mm.year = %s"; sub_params.append(year)
        if data_type is not None:
            sub_filters += " AND mm.data_type = %s"; sub_params.append(data_type)
        query += sub_filters + (
            " ORDER BY mm.year, mm.data_type, mm.energy_code,"
            " COALESCE(mm.is_draft, 0) DESC,"
            " mm.version_code DESC NULLS LAST,"
            " mm.id DESC"
            ")"
            " ORDER BY m.year, m.data_type, m.energy_code, d.period_code"
        )
        params = params + sub_params

        rows = self._execute(query, tuple(params))

        # 按主表记录聚合明细行
        grouped: Dict[int, Dict] = {}
        for r in rows:
            main_id = r['id']
            if main_id not in grouped:
                grouped[main_id] = {
                    **{k: r[k] for k in (
                        'id', 'year', 'data_type', 'energy_code', 'energy_name',
                        'energy_unit', 'standard_coal_coefficient',
                        'building_total_value', 'unit_total_value', 'granularity', 'customer_id')},
                    'periods': [],
                }
            if r.get('period_code') is not None:
                grouped[main_id]['periods'].append((r['period_code'], r.get('energy_value')))

        # 展开为兼容旧结构的 value1..value12 字段
        result = []
        for main_id, rec in grouped.items():
            monthly = self.expand_periods_to_monthly(rec.pop('periods'))
            rec.update({f'value{i}': monthly[i - 1] for i in range(1, 13)})
            rec['avg_value'] = rec['unit_total_value']  # 旧结构兼容字段（取本单位实际用量）
            result.append(rec)
        return result

    def get_institution_energy_cost(self, customer_id: int = None, year: str = None) -> List[Dict]:
        """获取机构能耗费用数据（data_type=2）。"""
        return self.get_institution_energy(customer_id=customer_id, year=year, data_type=2)

    # ========== 建筑信息 ==========

    def get_institution_build(self, customer_id: int = None) -> List[Dict]:
        """获取 ts_institution_build 建筑信息。

        版本归一规则（与 get_institution_energy 一致）：建筑表同一业务键
        (build_name, build_func) 并存草稿（is_draft=1, version_code=NULL）
        + 多个正式版本（is_draft=0, version_code 非空）。同一业务键只返回一条：
        草稿优先（is_draft=1，最新编辑数据）、无草稿时取正式版本（version_code 大者优先）；
        归一键含 build_func，避免同名不同功能建筑被误并（2026-09-03）。
        """
        query = """SELECT
            b.id, b.build_name, b.address, b.build_year, b.build_func, b.build_func_region,
            b.other_build_func_region, b.up_floor, b.down_floor, b.build_height, b.build_face,
            b.build_area, b.use_area, b.cold_area, b.heat_area,
            b.stru_type, b.other_stru_type,
            b.wallwin_type, b.other_wallwin_type,
            b.wallwarm_type, b.other_wallwarm_type,
            b.warm_material, b.other_warm,
            b.warm_thickness, b.warm_state,
            b.wallwarm_change,
            b.cold_source, b.cold_time, b.cold_date, b.cold_terminal_area,
            b.heat_source, b.heat_time, b.heart_date, b.heat_terminal_area,
            b.air_type, b.heat_type,
            b.water_supply, b.fire_water_supply, b.hot_water_supply,
            b.energy_system, b.storey_metrology,
            b.is_roomwarm, b.roomwarm_material, b.roomwarm_thickness, b.roomwarm_state, b.roomwarm_change,
            b.build_sunshade, b.sunshade_thickness, b.sunshade_install,
            b.build_run_time, b.use_begin_date, b.use_end_date, b.garage, b.garage_area,
            b.wallbody_thickness, b.other_wallbody_thickness, b.build_img
        FROM ts_institution_build b
        WHERE (b.deleted IS NULL OR b.deleted = 0)
          AND b.id IN (
              SELECT DISTINCT ON (bb.build_name, bb.build_func) bb.id
              FROM ts_institution_build bb
              WHERE (bb.deleted IS NULL OR bb.deleted = 0)"""
        params = []
        if customer_id:
            query += " AND b.customer_id = %s"; params.append(customer_id)
        sub_filters = ""
        sub_params = []
        if customer_id:
            sub_filters += " AND bb.customer_id = %s"; sub_params.append(customer_id)
        query += sub_filters + (
            # 版本归一：草稿(is_draft=1)优先（最新编辑数据），无草稿时 version_code 大者优先
            " ORDER BY bb.build_name, bb.build_func,"
            " COALESCE(bb.is_draft, 0) DESC,"
            " bb.version_code DESC NULLS LAST,"
            " bb.id DESC"
            ")"
            " ORDER BY b.build_name"
        )
        params = params + sub_params
        return self._execute(query, tuple(params))

    # ========== 设备信息 ==========

    def _get_device_by_table(self, table: str, customer_id: int = None) -> List[Dict]:
        """通用设备表查询（使用 SELECT *，避免硬编码字段与实际表结构不一致）。

        设备表与能耗/建筑/场景表同为版本机制（草稿 + PL 正式版本），
        同一设备（device_name+power+power_unit）并存多版本时按版本归一：
        草稿优先（is_draft=1，最新编辑数据），无草稿时 version_code 大者优先，避免设备清单出现重复。
        表无 version_code/is_draft 列时回退全量查询。
        """
        base = f"FROM {table} t WHERE t.deleted = 0"
        params = []
        if customer_id:
            base += " AND t.customer_id = %s"
            params.append(customer_id)
        versioned = f"""
            SELECT * FROM (
                SELECT t.*, ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(t.device_name, 'id_' || t.id::text), t.power, t.power_unit
                    ORDER BY CASE WHEN t.is_draft = 1 THEN 0 ELSE 1 END,
                             t.version_code DESC NULLS LAST
                ) AS _rn
                {base}
            ) x WHERE _rn = 1
        """
        try:
            rows = self._execute(versioned, tuple(params))
            for r in rows:
                r.pop('_rn', None)
            return rows
        except Exception:
            # 表无版本字段（version_code/is_draft 缺失等），回退全量
            try:
                self.connection.rollback()  # 防御：非 autocommit 连接下清理 aborted 事务
            except Exception:
                pass
            return self._execute(f"SELECT * {base}", tuple(params))

    def get_device_air(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_air — 冷热源/空调设备。"""
        return self._get_device_by_table("ts_institution_device_air", customer_id)

    def get_device_light(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_light — 照明设备。"""
        return self._get_device_by_table("ts_institution_device_light", customer_id)

    def get_device_office(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_office — 办公设备。"""
        return self._get_device_by_table("ts_institution_device_office", customer_id)

    def get_device_power(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_power — 动力设备。"""
        return self._get_device_by_table("ts_institution_device_power", customer_id)

    def get_device_hygiene(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_hygiene — 卫生器具。"""
        return self._get_device_by_table("ts_institution_device_hygiene", customer_id)

    def get_device_hotwater(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_hotwater — 生活热水设备。"""
        return self._get_device_by_table("ts_institution_device_hotwater", customer_id)

    def get_device_other(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_other — 其他设备。"""
        return self._get_device_by_table("ts_institution_device_other", customer_id)

    def get_device_special(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_special — 特殊设备。"""
        return self._get_device_by_table("ts_institution_device_special", customer_id)

    def get_device_steam(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_steam — 蒸汽设备。"""
        return self._get_device_by_table("ts_institution_device_steam", customer_id)

    def get_device_td(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_device_td — 输配设备（冷冻水泵/冷却塔等）。"""
        return self._get_device_by_table("ts_institution_device_td", customer_id)

    def get_all_devices(self, customer_id: int = None) -> Dict[str, List[Dict]]:
        """一次性获取所有分类设备，返回 {category: [records]}。"""
        return {
            "空调": self.get_device_air(customer_id),
            "照明": self.get_device_light(customer_id),
            "办公": self.get_device_office(customer_id),
            "动力": self.get_device_power(customer_id),
            "卫生器具": self.get_device_hygiene(customer_id),
            "生活热水": self.get_device_hotwater(customer_id),
            "其他设备": self.get_device_other(customer_id),
            "特殊设备": self.get_device_special(customer_id),
            "蒸汽": self.get_device_steam(customer_id),
            "输配设备": self.get_device_td(customer_id),
        }

    @staticmethod
    def _flag_cn(val, yes: str = '有', no: str = '无') -> str:
        """把 1/0 计量标记转成有/无；未填返回空串。"""
        if val is None or val == '':
            return ''
        try:
            v = int(val)
        except (TypeError, ValueError):
            return str(val).strip()
        if v == 1:
            return yes
        if v == 0:
            return no
        return str(v)

    @staticmethod
    def _default_power_unit(category: str) -> str:
        """设备表无 power_unit 列/值时，按类别推断功率单位。

        DB 实况：照明/办公类 power 存 W 数值（40W 灯具、150W 台式机、20W 云桌面），
        空调/动力/热水器类存 kW 数值（187kW 冷水机组、13.74kW 多联机、5kW 电开水器）。
        历史事故：默认 kW 导致灯具 40W 被显示为 40.00 kW（放大 1000 倍）。
        """
        return 'W' if category in ('照明', '办公') else 'kW'

    @staticmethod
    def _fmt_device(record: Dict, category: str) -> Dict:
        """把单条设备原始记录格式化为设备清单字段（含独立计量，表无该列则为空）。"""
        name = record.get('device_name') or '未命名'
        quantity = 0
        for qkey in ('device_num', 'use_num', 'quantity'):
            if record.get(qkey) is not None:
                try:
                    quantity = int(record[qkey])
                    break
                except (TypeError, ValueError):
                    pass

        spec_parts = []
        if record.get('brand_model'):
            spec_parts.append(str(record['brand_model']))
        if record.get('specs'):
            spec_parts.append(str(record['specs']))
        if record.get('device_type'):
            spec_parts.append(str(record['device_type']))
        if record.get('power'):
            punit = record.get('power_unit') or PgDataQuery._default_power_unit(category)
            spec_parts.append(f"{record['power']}{punit}")
        if record.get('air_technology'):
            spec_parts.append(str(record['air_technology']))
        if record.get('run_time'):
            spec_parts.append(f"运行:{record['run_time']}")
        if record.get('use_area'):
            spec_parts.append(f"区域:{record['use_area']}")
        if record.get('other_desc'):
            spec_parts.append(str(record['other_desc']))

        metering = ''
        if 'is_metering' in record:
            metering = PgDataQuery._flag_cn(record.get('is_metering'))

        return {
            'name': name,
            'category': category,
            'spec': ' | '.join(filter(None, spec_parts)),
            'quantity': quantity,
            'independent_metering': metering,
            'independent_metering_desc': str(record['metering_desc']).strip()
            if record.get('metering_desc') else '',
            'independent_metering_ratio': str(record['metering_ratio']).strip()
            if record.get('metering_ratio') else '',
            'independent_metering_time': str(record['metering_time']).strip()
            if record.get('metering_time') else '',
        }

    def get_formatted_equipment(self, customer_id: int = None, category: str = None) -> List[Dict]:
        """获取格式化后的设备清单，结构同 pg_collector.collect_from_pg 的 equipment。"""
        all_devs = self.get_all_devices(customer_id)
        result = []
        for cat, records in all_devs.items():
            if category and cat != category:
                continue
            for r in records:
                result.append(self._fmt_device(r, cat))
        return result

    # ========== 人员信息 ==========

    def get_project_audit_users(self, project_id: int = None) -> List[Dict]:
        """ts_project_audit_user — 审计组成员。"""
        query = """SELECT id, name, position, degree, qualifications, major
                 FROM ts_project_audit_user WHERE 1=1"""
        params = []
        if project_id:
            query += " AND project_id = %s"; params.append(project_id)
        return self._execute(query, tuple(params))

    def get_project_audited_users(self, project_id: int = None) -> List[Dict]:
        """ts_project_audited_user — 被审计单位配合人员。"""
        query = """SELECT id, name, position, department, sex, group_position
                 FROM ts_project_audited_user WHERE 1=1"""
        params = []
        if project_id:
            query += " AND project_id = %s"; params.append(project_id)
        return self._execute(query, tuple(params))

    def get_project_dept(self, project_id: int = None) -> List[Dict]:
        """ts_project_dept — 项目级审计机构信息表（能源审计机构信息表数据源）。

        字段：dept_name(机构名称)/address(地址)/contact(负责人)/mobile(联系方式)/project_id。
        按项目 id 精确查询，id 倒序取最新记录。
        """
        query = "SELECT id, dept_name, address, contact, mobile, project_id FROM ts_project_dept"
        params = []
        if project_id:
            query += " WHERE project_id = %s"
            params.append(project_id)
        query += " ORDER BY id DESC"
        return self._execute(query, tuple(params))

    def get_register_info(self, credit_code: str = None, dept_name: str = None) -> List[Dict]:
        """ts_register_dept — 注册单位表（审计机构信息源）。

        按统一信用代码精确匹配或单位名称模糊匹配（ILIKE），
        返回 dept_name/address/contact/mobile 供"能源审计机构信息表"使用：
        - dept_name（单位名称）/ address（详细地址）：表内有值直接用，缺失由用户提问提供
        - contact/mobile：仅作提问预填参考，不作为最终值

        注：审计机构数据源为 ts_register_dept（注册单位表），
        不是 ts_register_info（被审计单位注册申请表）。
        """
        query = """SELECT id, credit_code, dept_name, address, contact, mobile
                 FROM ts_register_dept WHERE (deleted IS NULL OR deleted = 0)"""
        params = []
        if credit_code:
            query += " AND credit_code = %s"; params.append(credit_code)
        if dept_name:
            query += " AND dept_name ILIKE %s"; params.append(f"%{dept_name}%")
        query += " ORDER BY update_time DESC"
        return self._execute(query, tuple(params))

    # ========== 用能场景 / 计量信息 ==========

    def get_institution_scene(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_scene — 用能场景、计量与供暖信息。

        版本归一：同一 (year) 并存草稿/多个正式版本，草稿优先、
        无草稿时 version_code 大者优先（与 energy/build 取数规则一致）。
        """
        query = """SELECT
                    s.id, s.year, s.mode, s.split_measure, s.split_payment,
                    s.energy_metering, s.separate_meter, s.heat_area, s.heat_day, s.heat_price,
                    s.heat_pay_type, s.work_staff,
                    s.light_socket_meter, s.power_meter, s.aircon_meter, s.special_meter,
                    s.other_special_meter, s.construction_elec_meter, s.construction_water_meter,
                    s.install_position, s.position_reasonable, s.metering_standard,
                    s.partition_payment, s.electric_pay_type, s.service_staff,
                    s.scene_desc, s.record_attach_id,
                    s.aircon_staff_num, s.light_staff_num, s.power_room_staff_num
                 FROM ts_institution_scene s
                 WHERE (s.deleted IS NULL OR s.deleted = 0)
                   AND s.id IN (
                       SELECT DISTINCT ON (ss.year) ss.id
                       FROM ts_institution_scene ss
                       WHERE (ss.deleted IS NULL OR ss.deleted = 0)"""
        params = []
        if customer_id:
            query += " AND s.customer_id = %s"; params.append(customer_id)
        sub_filters = ""
        sub_params = []
        if customer_id:
            sub_filters += " AND ss.customer_id = %s"; sub_params.append(customer_id)
        query += sub_filters + (
            " ORDER BY ss.year,"
            " COALESCE(ss.is_draft, 0) DESC,"
            " ss.version_code DESC NULLS LAST,"
            " ss.id DESC"
            ")"
            " ORDER BY s.year DESC"
        )
        params = params + sub_params
        return self._execute(query, tuple(params))

    def get_institution_scene_mode(self, customer_id: int = None,
                                   scene_id: int = None) -> List[Dict]:
        """ts_institution_scene_mode — 合署办公单位明细（含是否独立计量）。"""
        query = """SELECT id, mode_dept_name, mode_reason, pay_type,
                    start_time, end_time, scene_id, customer_id,
                    mode_build, mode_area, mode_ratio, is_metering
                 FROM ts_institution_scene_mode
                 WHERE deleted = 0"""
        params = []
        if customer_id:
            query += " AND customer_id = %s"
            params.append(customer_id)
        if scene_id:
            query += " AND scene_id = %s"
            params.append(scene_id)
        query += " ORDER BY id"
        return self._execute(query, tuple(params))

    @staticmethod
    def _fmt_scene_mode(record: Dict) -> Dict:
        """格式化合署办公明细，含独立计量。"""
        metering = ''
        if 'is_metering' in record:
            metering = PgDataQuery._flag_cn(record.get('is_metering'))
        area = record.get('mode_area')
        ratio = record.get('mode_ratio')
        try:
            area_v = float(area) if area is not None else 0.0
        except (TypeError, ValueError):
            area_v = 0.0
        try:
            ratio_v = float(ratio) if ratio is not None else 0.0
        except (TypeError, ValueError):
            ratio_v = 0.0
        return {
            'dept_name': (record.get('mode_dept_name') or '').strip(),
            'reason': (record.get('mode_reason') or '').strip(),
            'pay_type': (record.get('pay_type') or '').strip(),
            'start_time': str(record['start_time'])[:10] if record.get('start_time') else '',
            'end_time': str(record['end_time'])[:10] if record.get('end_time') else '',
            'building': (record.get('mode_build') or '').strip(),
            'area': area_v,
            'ratio': ratio_v,
            'independent_metering': metering,
        }

    # ========== 表具计量信息 ==========

    def get_energy_meter(self, customer_id: int = None, data_type: int = None,
                         year: int = None) -> List[Dict]:
        """ts_institution_energy_meter — 公共机构用电/用水计量信息。

        Args:
            customer_id: 所属客户 ID。
            data_type: 1=电表，2=水表；不填则返回全部。
            year: 统计年份；不填则返回全部。

        版本归一：同一 (data_type, statistical_year) 并存草稿/多个正式版本，
        草稿优先（is_draft=1，最新编辑数据），无草稿时 version_code 大者优先。
        """
        query = """SELECT m.id, m.statistical_year, m.has_other_meter, m.meter_count,
                    m.sub_metering, m.other_metering_scenario, m.other_situation,
                    m.customer_id, m.data_type, m.measured_depth, m.month_measured,
                    m.month_files, m.year_measured, m.year_files, m.device_img,
                    m.kitchen_water, m.year_water, m.year_water_value, m.ledger_files,
                    m.create_time, m.update_time
                 FROM ts_institution_energy_meter m
                 WHERE (m.deleted IS NULL OR m.deleted = 0)
                   AND m.id IN (
                       SELECT DISTINCT ON (mm.data_type, mm.statistical_year) mm.id
                       FROM ts_institution_energy_meter mm
                       WHERE (mm.deleted IS NULL OR mm.deleted = 0)"""
        params = []
        if customer_id:
            query += " AND m.customer_id = %s"; params.append(customer_id)
        if data_type is not None:
            query += " AND m.data_type = %s"; params.append(data_type)
        if year is not None:
            query += " AND m.statistical_year = %s"; params.append(year)
        sub_filters = ""
        sub_params = []
        if customer_id:
            sub_filters += " AND mm.customer_id = %s"; sub_params.append(customer_id)
        if data_type is not None:
            sub_filters += " AND mm.data_type = %s"; sub_params.append(data_type)
        if year is not None:
            sub_filters += " AND mm.statistical_year = %s"; sub_params.append(year)
        query += sub_filters + (
            " ORDER BY mm.data_type, mm.statistical_year,"
            " COALESCE(mm.is_draft, 0) DESC,"
            " mm.version_code DESC NULLS LAST,"
            " mm.id DESC"
            ")"
            " ORDER BY m.statistical_year DESC, m.data_type, m.id"
        )
        params = params + sub_params
        return self._execute(query, tuple(params))

    # ========== 节能管理信息 ==========

    def get_institution_energy_saving(self, customer_id: int = None,
                                      year: int = None) -> List[Dict]:
        """ts_institution_energy_saving — 公共机构节能管理信息。

        Args:
            customer_id: 所属客户 ID。
            year: 统计年份；不填则返回全部。
        """
        query = """SELECT id, statistical_year, energy_management, energy_pain_points,
                    management_files, has_awards, award_name, award_certificate,
                    other_measures, third_party_system, charging_pile,
                    charging_settlement, charging_installation, third_party_outsource,
                    outsource_content, outsource_settlement, lighting_replacement,
                    ac_replacement, water_saving_fixture_replacement, central_ac_control,
                    customer_id, version_code, is_draft
                 FROM ts_institution_energy_saving
                 WHERE deleted = 0
                   AND id IN (
                       SELECT DISTINCT ON (COALESCE(ss.statistical_year, 0)) ss.id
                       FROM ts_institution_energy_saving ss
                       WHERE ss.deleted = 0"""
        params = []
        if customer_id:
            query += " AND customer_id = %s"; params.append(customer_id)
        if year is not None:
            query += " AND statistical_year = %s"; params.append(year)
        # 子查询镜像过滤 + 版本归一（草稿优先=最新编辑数据，无草稿时 version_code 大者优先）
        sub_filters = ""
        sub_params = []
        if customer_id:
            sub_filters += " AND ss.customer_id = %s"; sub_params.append(customer_id)
        if year is not None:
            sub_filters += " AND ss.statistical_year = %s"; sub_params.append(year)
        query += sub_filters + (
            " ORDER BY COALESCE(ss.statistical_year, 0),"
            " COALESCE(ss.is_draft, 0) DESC,"
            " ss.version_code DESC NULLS LAST,"
            " ss.id DESC"
            ")"
        )
        query += " ORDER BY statistical_year DESC, id"
        params = params + sub_params
        return self._execute(query, tuple(params))

    # ========== 附件（文件） ==========

    def get_attachments(self, group_ids: List[int] = None) -> List[Dict]:
        """ts_attachment — 按附件组 ID（group_id）批量查询附件元数据。

        ts_institution_energy_saving.management_files / award_certificate 中
        逗号分隔的雪花 ID 即 ts_attachment.group_id。返回列表元素包含
        group_id / attach_initial_name（原始文件名）/ attach_name / attach_url（相对路径）
        / attach_size / attach_type。
        """
        if not group_ids:
            return []
        query = """SELECT group_id, attach_initial_name, attach_name, attach_url, attach_size, attach_type
                   FROM ts_attachment
                   WHERE group_id = ANY(%s) AND (deleted IS NULL OR deleted = 0)"""
        return self._execute(query, (list(group_ids),))

    # ========== 兼容旧接口 ==========

    def get_energy_consumption(self, start_date: str = None, end_date: str = None,
                               project_id: int = None, customer_id: int = None):
        """兼容旧接口：按时间范围查询能耗数据，返回 DataFrame（含 consumption 列）。

        底层已适配新两表结构（ts_institution_energy_main + ts_institution_energy_data）。
        project_id 仅用于兼容签名；实际按 customer_id 过滤，未提供时返回全部。
        """
        import pandas as pd

        def _year(d):
            if not d:
                return None
            digits = ''.join(ch for ch in str(d)[:10] if ch.isdigit())
            return int(digits[:4]) if len(digits) >= 4 else None

        y1, y2 = _year(start_date), _year(end_date)
        energy = self.get_institution_energy(customer_id=customer_id)

        rows = []
        for e in energy:
            year = e.get('year')
            if year:
                try:
                    year_int = int(year)
                    if y1 and year_int < y1:
                        continue
                    if y2 and year_int > y2:
                        continue
                except (TypeError, ValueError):
                    pass
            row = {
                'id': e.get('id'),
                'project_id': project_id,
                'year': year,
                'energy_type': e.get('energy_name'),
                'energy_unit': e.get('energy_unit'),
                'consumption': e.get('unit_total_value'),
            }
            for i in range(1, 13):
                row[f'month{i}'] = e.get(f'value{i}', 0)
            rows.append(row)
        return pd.DataFrame(rows)


# 使用示例
if __name__ == "__main__":
    # 连接配置走 db_config 解析链（env / config.yaml），不在源码中写凭据
    with PgDataQuery() as db:
        # 测试查询
        energy = db.get_institution_energy()
        print(f"机构能耗: {len(energy)} 条")
        for e in energy[:3]:
            print(f"  year={e['year']}, name={e['energy_name']}, total={e['unit_total_value']}")
