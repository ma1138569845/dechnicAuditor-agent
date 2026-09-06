# -*- coding: utf-8 -*-
"""Round-5 preflight: PG via official PgDataQuery API + toolchain + profiles."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("=== 1) PG 登记锚点 (官方 PgDataQuery) ===")
try:
    from tools.energy_audit.pg_query import PgDataQuery
    from tools.energy_audit.db_config import get_file_base_url
    pg = PgDataQuery()
    pg.connect()
    print('  file_base_url:', get_file_base_url())
except Exception as e:
    print('  FAIL init:', repr(e)); sys.exit(1)

def show(rows):
    if not rows:
        print('    (none)')
    for r in rows:
        keys = [k for k in ('id','audited_name','customer_id','audit_year','reference_year','status','create_time') if k in r]
        print('   ', {k: r.get(k) for k in keys})

print('  -- 正式登记 id=2087807622972936194 --')
try:
    show(pg.get_institution_project(project_id=2087807622972936194))
except Exception as e:
    print('  FAIL:', repr(e))
print('  -- 测试登记 id=2095793661742092289 --')
try:
    show(pg.get_institution_project(project_id=2095793661742092289))
except Exception as e:
    print('  FAIL:', repr(e))
print('  -- 按名称 ILIKE 烟台经济技术开发区人民法院（全量，防误取）--')
try:
    show(pg.get_institution_project(audited_name='烟台经济技术开发区人民法院'))
except Exception as e:
    print('  FAIL:', repr(e))
print('  -- customer 2083089316391030786 --')
try:
    show(pg.get_customer_info(customer_id=2083089316391030786))
except Exception as e:
    print('  FAIL:', repr(e))

print("=== 2) repo 工具链导入 ===")
try:
    import tools.energy_audit.pg_collector as pc
    import tools.energy_audit.project_data as pd
    import tools.energy_audit.indicators as ind
    print('  pg_collector/project_data/indicators import OK')
except Exception as e:
    print('  FAIL:', repr(e)); sys.exit(1)

print("=== 3) profiles 存在 ===")
import os
from pathlib import Path
proot = Path(os.environ.get('LOCALAPPDATA', os.path.expanduser('~/AppData/Local'))) / 'hermes' / 'profiles'
for p in ['datacollection', 'datava', 'caliber', 'author', 'editor']:
    print(f'  {p}:', (proot / p).is_dir())
print('  profiles root =', proot)
