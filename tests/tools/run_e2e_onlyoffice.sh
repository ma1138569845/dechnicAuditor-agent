#!/usr/bin/env bash
# Real-DS E2E harness: copies the smoke xlsx to a FRESH temp path so each run
# gets a new file_id + OnlyOffice key (reusing a key across runs leaves a stale
# coauthoring lock on the DS and the editor never reaches "ready").
#
# Prereqs: backend up on 12798 with HERMES_OFFICE_* env + the session token
# below; DocumentServer reachable at HERMES_OFFICE_DS_URL.
set -euo pipefail

ROOT="D:/data/pyProject/dc_agent/dechnicAuditor-agent"
API="http://127.0.0.1:12798"
TOKEN="test-e2e-token-001"
PY="D:/develop/anaconda3/python.exe"

WORK="$ROOT/tests/tools/e2e_work"
mkdir -p "$WORK"
TMP="$WORK/smoke_$(date +%s)_$RANDOM.xlsx"
cp "$ROOT/tests/tools/smoke_onlyoffice.xlsx" "$TMP"

RESP=$(curl -s -X POST "$API/api/office-preview/start" \
  -H "Content-Type: application/json" \
  -H "X-Hermes-Session-Token: $TOKEN" \
  -d "{\"file_path\":\"$TMP\",\"workspace\":\"$ROOT\"}")
FID=$(printf '%s' "$RESP" | "$PY" -c "import sys,json; print(json.load(sys.stdin)['file_id'])")
URL=$(printf '%s' "$RESP" | "$PY" -c "import sys,json; print(json.load(sys.stdin)['url'])")

echo "file_id=$FID"
echo "tmp=$TMP"
node "$ROOT/tests/tools/e2e_onlyoffice_ds.mjs" "$URL" "$TMP" "$FID"
STATUS=$?
rm -f "$TMP"
exit $STATUS
