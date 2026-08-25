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

    def get_province_name_by_district_id(self, district_id) -> str:
        """ts_customer_info.district_id → 省级名称（如 山东省）。"""
        province_code = self.district_id_to_province_code(district_id)
        if province_code:
            area = self.get_area_by_code(province_code)
            if area and area.get('f_areaname'):
                return str(area['f_areaname']).strip()
        # 字典缺省级码时，沿父级走到 f_type=0
        current = str(district_id or '').strip()
        seen = set()
        while current and current not in seen and current not in ('0', '00', '000000'):
            seen.add(current)
            area = self.get_area_by_code(current)
            if not area:
                break
            if area.get('f_type') == 0:
                return str(area.get('f_areaname') or '').strip()
            current = str(area.get('f_areasupcode') or '').strip()
        return ''

    # ========== 审计项目 ==========

    def get_institution_project(self, project_id: int = None, audited_name: str = None) -> List[Dict]:
        """获取 ts_institution_project。

        Args:
            project_id: 按项目 ID 精确查询。
            audited_name: 按被审计单位名称模糊查询（ILIKE）。
        """
        query = """SELECT id, audited_name, audited_person, audited_tel,
                    commission_person, commission_tel, audit_dept_name,
                    audit_year, reference_year, start_time, end_time,
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
            WHERE (m.deleted IS NULL OR m.deleted = 0)"""
        params = []
        if customer_id:
            query += " AND m.customer_id = %s"; params.append(customer_id)
        if year:
            query += " AND m.year = %s"; params.append(year)
        if data_type is not None:
            query += " AND m.data_type = %s"; params.append(data_type)
        query += " ORDER BY m.year, m.data_type, m.energy_code, d.period_code"

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
        """获取 ts_institution_build 建筑信息。"""
        query = """SELECT
            id, build_name, address, build_year, build_func, build_func_region,
            other_build_func_region, up_floor, down_floor, build_height, build_face,
            build_area, use_area, cold_area, heat_area,
            stru_type, other_stru_type,
            wallwin_type, other_wallwin_type,
            wallwarm_type, other_wallwarm_type,
            warm_material, other_warm,
            warm_thickness, warm_state,
            wallwarm_change,
            cold_source, cold_time, cold_date, cold_terminal_area,
            heat_source, heat_time, heart_date, heat_terminal_area,
            air_type, heat_type,
            water_supply, fire_water_supply, hot_water_supply,
            energy_system, storey_metrology,
            is_roomwarm, roomwarm_material, roomwarm_thickness, roomwarm_state, roomwarm_change,
            build_sunshade, sunshade_thickness, sunshade_install,
            build_run_time, use_begin_date, use_end_date, garage, garage_area,
            wallbody_thickness, other_wallbody_thickness
        FROM ts_institution_build
        WHERE deleted = 0"""
        params = []
        if customer_id:
            query += " AND customer_id = %s"; params.append(customer_id)
        return self._execute(query, tuple(params))

    # ========== 设备信息 ==========

    def _get_device_by_table(self, table: str, customer_id: int = None) -> List[Dict]:
        """通用设备表查询（使用 SELECT *，避免硬编码字段与实际表结构不一致）。"""
        query = f"SELECT * FROM {table} WHERE deleted = 0"
        params = []
        if customer_id:
            query += " AND customer_id = %s"; params.append(customer_id)
        return self._execute(query, tuple(params))

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
            punit = record.get('power_unit') or 'kW'
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

    # ========== 用能场景 / 计量信息 ==========

    def get_institution_scene(self, customer_id: int = None) -> List[Dict]:
        """ts_institution_scene — 用能场景、计量与供暖信息。"""
        query = """SELECT id, year, mode, split_measure, split_payment,
                    energy_metering, separate_meter, heat_area, heat_day, heat_price,
                    heat_pay_type, work_staff,
                    light_socket_meter, power_meter, aircon_meter, special_meter,
                    other_special_meter, construction_elec_meter, construction_water_meter
                 FROM ts_institution_scene
                 WHERE deleted = 0"""
        params = []
        if customer_id:
            query += " AND customer_id = %s"; params.append(customer_id)
        query += " ORDER BY year DESC"
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
        """
        query = """SELECT id, statistical_year, has_other_meter, meter_count,
                    sub_metering, other_metering_scenario, other_situation,
                    customer_id, data_type, measured_depth, month_measured,
                    month_files, year_measured, year_files, device_img,
                    kitchen_water, year_water, year_water_value,
                    create_time, update_time
                 FROM ts_institution_energy_meter
                 WHERE deleted = 0"""
        params = []
        if customer_id:
            query += " AND customer_id = %s"; params.append(customer_id)
        if data_type is not None:
            query += " AND data_type = %s"; params.append(data_type)
        if year is not None:
            query += " AND statistical_year = %s"; params.append(year)
        query += " ORDER BY statistical_year DESC, data_type, id"
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
                 WHERE deleted = 0"""
        params = []
        if customer_id:
            query += " AND customer_id = %s"; params.append(customer_id)
        if year is not None:
            query += " AND statistical_year = %s"; params.append(year)
        query += " ORDER BY statistical_year DESC, id"
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
