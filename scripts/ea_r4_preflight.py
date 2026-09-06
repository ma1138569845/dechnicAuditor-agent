# -*- coding: utf-8 -*-
"""Round4 preflight: PG connectivity + repo energy_audit tools import + WINWORD check."""
import sys, subprocess

ok = True

# 1. WINWORD zombie check
out = subprocess.run(["tasklist"], capture_output=True).stdout.decode("gbk", errors="replace")
zw = [l for l in out.splitlines() if "WINWORD" in l.upper()]
print("WINWORD processes:", zw if zw else "none")

# 2. repo tools import + official PG config resolution
sys.path.insert(0, r"D:/data/pyProject/dc_agent/dechnicAuditor-agent")
try:
    from tools.energy_audit import db_config
    print("db_config import OK")
except Exception as e:
    print("tools import FAIL:", e)
    ok = False

# 3. PG connectivity via db_config.get_pg_config()
try:
    import psycopg2
    pg = db_config.get_pg_config()
    print("PG cfg resolved keys:", sorted(pg.keys()))
    conn = psycopg2.connect(connect_timeout=6, **pg)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM ts_institution_project WHERE id = 2087807622972936194 AND (deleted IS NULL OR deleted = 0)")
    n1 = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM ts_institution_project WHERE id = 2095793661742092289 AND (deleted IS NULL OR deleted = 0)")
    n2 = cur.fetchone()[0]
    cur.execute("SELECT id, audited_name, customer_id FROM ts_institution_project WHERE id IN (2087807622972936194, 2095793661742092289)")
    rows = cur.fetchall()
    print(f"PG OK | rows={rows}")
    cur.close(); conn.close()
except Exception as e:
    print("PG FAIL:", e)
    ok = False

print("PREFLIGHT:", "PASS" if ok else "FAIL")
