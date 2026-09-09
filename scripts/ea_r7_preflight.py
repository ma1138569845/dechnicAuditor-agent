# -*- coding: utf-8 -*-
"""R7 预检：显式锚定正式登记 2087807622972936194 / customer 2083089316391030786。

只读探查：项目行（audit_year/reference_year/status/create_time/customer_id）、
客户行（field_type/district_id）、审计机构 ts_project_dept、注册 ts_register_dept、
同名登记核查（ILIKE 应唯一命中正式登记）。禁止写库。
"""
import os
import pathlib

# datacollection profile 的 config.yaml 无 energy_audit 段，密码/文件 base_url 位于
# 默认 Hermes config —— 从该文件引导进环境变量（不打印明文），符合 db_config 配置链。
_default_hermes_cfg = pathlib.Path(r"C:/Users/matianyuan/AppData/Local/hermes/config.yaml")
if _default_hermes_cfg.exists():
    try:
        import yaml as _yaml
        _cfg = _yaml.safe_load(_default_hermes_cfg.read_text(encoding='utf-8')) or {}
        _ea = _cfg.get('energy_audit') or {}
        _db = _ea.get('database') or {}
        _fl = _ea.get('file') or {}
        if _db.get('password'):
            os.environ.setdefault('EA_PG_PASSWORD', str(_db['password']))
        if _fl.get('base_url'):
            os.environ.setdefault('EA_FILE_BASE_URL', str(_fl['base_url']))
    except Exception as _e:  # noqa: BLE001
        print('[preflight] hermes config 引导失败:', _e)

from tools.energy_audit.pg_query import PgDataQuery

PROJECT_ID = 2087807622972936194
CUSTOMER_ID = 2083089316391030786
NAME = "烟台经济技术开发区人民法院"

pg = PgDataQuery()
pg.connect()
try:
    # 1) 同名登记核查：按名称 ILIKE
    rows = pg.get_institution_project(audited_name=NAME)
    print("== ILIKE by audited_name ==")
    for r in rows:
        print({k: r.get(k) for k in ('id', 'audited_name', 'customer_id', 'status', 'audit_year', 'reference_year')})

    # 2) 显式 ID 锚定
    proj_rows = pg.get_institution_project(project_id=PROJECT_ID)
    print("== explicit project_id ==")
    for r in proj_rows:
        print({k: r.get(k) for k in ('id', 'audited_name', 'customer_id', 'status',
                                     'audit_year', 'reference_year', 'create_time',
                                     'audit_dept_name', 'audit_dept_person', 'audit_dept_tel',
                                     'energy_codes', 'audit_template', 'commission_person',
                                     'commission_tel', 'remark')})

    # 3) 客户行
    cust = pg.get_customer_info(customer_id=CUSTOMER_ID)
    print("== customer ==")
    for c in (cust or []):
        print({k: c.get(k) for k in ('id', 'name', 'field_type', 'district_id',
                                     'address', 'basic_situation', 'contact')})

    # 4) 审计机构项目级信息
    pd_rows = pg.get_project_dept(project_id=PROJECT_ID) or []
    print("== ts_project_dept ==")
    for p in pd_rows:
        print({k: p.get(k) for k in ('id', 'project_id', 'dept_name', 'address', 'contact', 'mobile')})

    # 5) 注册机构（正式落款用）
    regs = pg.get_register_info(dept_name='同方德诚') or []
    print("== ts_register_dept(德诚) ==")
    for r in regs:
        print({k: r.get(k) for k in ('id', 'dept_name', 'address', 'contact', 'mobile', 'update_time')})

    # 6) 折标系数表
    stds = pg.get_energy_standards() or []
    print(f"== ts_energy_standard: {len(stds)} rows ==")
    for s in stds:
        print({k: s.get(k) for k in ('id', 'energy_code', 'energy_name', 'coefficient', 'unit') if k in s})

    # 7) 场景行（人数/热价/照片 id）
    scenes = pg.get_institution_scene(customer_id=CUSTOMER_ID) or []
    print(f"== ts_institution_scene: {len(scenes)} rows ==")
    for sc in scenes:
        print({k: sc.get(k) for k in ('id', 'year', 'work_staff', 'heat_area', 'heat_day', 'heat_price',
                                      'scene_img_id', 'energy_metering', 'separate_meter') if k in sc})

    # 8) 表具/发票/节能
    meters = pg.get_energy_meter(customer_id=CUSTOMER_ID) or []
    print(f"== ts_institution_energy_meter: {len(meters)} rows ==")
    inv = pg.get_institution_energy_invoice(customer_id=CUSTOMER_ID) or []
    print(f"== ts_institution_energy_invoice: {len(inv)} rows ==")
    saving = pg.get_institution_energy_saving(customer_id=CUSTOMER_ID) or []
    print(f"== ts_institution_energy_saving: {len(saving)} rows ==")
    for s in saving:
        print({k: s.get(k) for k in ('id', 'statistical_year', 'energy_management', 'has_awards') if k in s})
    audit_users = pg.get_project_audit_users(project_id=PROJECT_ID) or []
    audited_users = pg.get_project_audited_users(project_id=PROJECT_ID) or []
    print(f"== audit_user: {len(audit_users)} / audited_user: {len(audited_users)} ==")
finally:
    pg.disconnect()
