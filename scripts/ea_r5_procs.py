# -*- coding: utf-8 -*-
import subprocess, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ps = (
    "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|hermes' } "
    "| Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
)
out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                     capture_output=True, timeout=60)
txt = out.stdout.decode('utf-8', errors='replace')
try:
    rows = json.loads(txt)
    if isinstance(rows, dict):
        rows = [rows]
    for r in rows:
        cmd = (r.get("CommandLine") or "")[:220]
        print(r.get("ProcessId"), "|", cmd.replace('\r', ' ').replace('\n', ' '))
except Exception as e:
    print("parse fail:", e)
    print(txt[:4000])
