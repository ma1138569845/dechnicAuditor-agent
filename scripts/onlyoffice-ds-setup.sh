#!/usr/bin/env bash
#
# ONLYOFFICE DocumentServer setup for the Hermes desktop Office integration.
# Run this on the remote server that will host the DS (e.g. 10.10.2.55).
#
# Usage:
#   DS_JWT_SECRET='<shared-secret>' DS_CALLBACK_HOST='192.168.0.238' \
#     DS_CALLBACK_PORT=39250 bash scripts/onlyoffice-ds-setup.sh
#
# Required env:
#   DS_JWT_SECRET     shared HS256 secret — MUST match HERMES_OFFICE_JWT_SECRET
#                     on the desktop machine. Not echoed unless VERBOSE=1.
# Optional env (defaults shown):
#   DS_HTTP_PORT      8090         host port mapped to container :80
#   DS_CALLBACK_HOST  192.168.0.238  LAN IP of the Hermes desktop backend
#   DS_CALLBACK_PORT  39250        preview-server port (firewall-scoped)
#   DS_VOLUME         onlyoffice_data  docker named volume for app data
#   DS_FONTS          1            also mount a fonts dir when set
#   DS_SKIP_GATE      0            set to 1 to skip the reverse-connectivity gate
#                                  (desktop backend not running yet)
#   VERBOSE           0            set to 1 to print commands being run
#
set -euo pipefail

: "${DS_HTTP_PORT:=8090}"
: "${DS_CALLBACK_HOST:=192.168.0.238}"
: "${DS_CALLBACK_PORT:=39250}"
: "${DS_VOLUME:=onlyoffice_data}"
: "${DS_FONTS:=1}"
: "${DS_SKIP_GATE:=0}"
: "${VERBOSE:=0}"
[ "${VERBOSE}" = "1" ] && set -x

if [ -z "${DS_JWT_SECRET:-}" ]; then
  echo "ERROR: DS_JWT_SECRET is required (shared with HERMES_OFFICE_JWT_SECRET on the desktop)." >&2
  exit 1
fi

log() { printf '\n==> %s\n' "$*"; }

# --- 1. Docker ---------------------------------------------------------------
log "Ensuring Docker is available"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install it first, e.g.:" >&2
  echo "  curl -fsSL https://get.docker.com | sh" >&2
  echo "  sudo usermod -aG docker $USER   # then re-login" >&2
  exit 1
fi
docker --version

# --- 2. Pull + run DocumentServer -------------------------------------------
log "Pulling onlyoffice/documentserver"
docker pull onlyoffice/documentserver:latest

log "Creating named volume ${DS_VOLUME} (idempotent)"
docker volume create "${DS_VOLUME}" >/dev/null 2>&1 || true

RUN_ARGS=(
  -d
  --name onlyoffice-documentserver
  --restart=always
  -p "${DS_HTTP_PORT}:80"
  -e JWT_ENABLED=true
  -e "JWT_SECRET=${DS_JWT_SECRET}"
  -v "${DS_VOLUME}:/var/www/onlyoffice/Data"
)

# Fonts make CJK + docs render correctly. Mount a host dir; drop .ttf/.ttc files in it.
FONT_DIR=/opt/onlyoffice/fonts
if [ "${DS_FONTS}" = "1" ]; then
  mkdir -p "${FONT_DIR}"
  RUN_ARGS+=( -v "${FONT_DIR}:/usr/share/fonts/onlyoffice:ro" )
fi

log "Starting DocumentServer on port ${DS_HTTP_PORT}"
docker rm -f onlyoffice-documentserver >/dev/null 2>&1 || true
docker run "${RUN_ARGS[@]}" onlyoffice/documentserver:latest

# --- 3. Healthcheck -----------------------------------------------------------
log "Waiting for healthcheck at http://127.0.0.1:${DS_HTTP_PORT}/healthcheck"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${DS_HTTP_PORT}/healthcheck" >/dev/null 2>&1; then
    echo "OK: DocumentServer healthy after ${i}0s of polling."
    break
  fi
  sleep 10
  [ "${i}" = "60" ] && { echo "FAIL: healthcheck never turned green." >&2; exit 1; }
done

# --- 4. Reverse connectivity gate -------------------------------------------
# The DS must be able to reach the Hermes backend's preview server to fetch the
# original file and to POST saves back. If this fails, OnlyOffice cannot write
# edits back to disk (plan Phase 0 gate #1).
if [ "${DS_SKIP_GATE}" = "1" ]; then
  log "Reverse connectivity gate skipped (DS_SKIP_GATE=1)."
  log "Re-run the gate later with the desktop backend up and firewall open:"
  log "  curl http://${DS_CALLBACK_HOST}:${DS_CALLBACK_PORT}/api/health"
else
  log "Reverse connectivity gate: DS -> ${DS_CALLBACK_HOST}:${DS_CALLBACK_PORT}"
  if curl -fsS --max-time 5 "http://${DS_CALLBACK_HOST}:${DS_CALLBACK_PORT}/api/health" >/dev/null 2>&1; then
    echo "OK: backend preview server reachable from the DS host."
  else
    echo "WARN: cannot reach ${DS_CALLBACK_HOST}:${DS_CALLBACK_PORT}." >&2
    echo "      Check the Windows firewall inbound rule for the preview port and" >&2
    echo "      that the backend is running with HERMES_OFFICE_DS_URL set." >&2
    echo "      OnlyOffice preview/editing will not work until this passes." >&2
    exit 1
  fi
fi

# --- 5. JWT probe -------------------------------------------------------------
# Confirm the DS sends the Authorization header on callback/download fetches.
# If the header is absent we must switch the download auth to the query-token
# scheme (already supported by /api/onlyoffice/download).
log "JWT probe (informational only)"
API_JS_HTTP=$(curl -fsS -o /dev/null -w '%{http_code}' \
  "http://127.0.0.1:${DS_HTTP_PORT}/web-apps/apps/api/documents/api.js" || true)
echo "document api.js status: ${API_JS_HTTP}"

log "Done. DocumentServer:  http://${HOSTNAME}:${DS_HTTP_PORT}"
echo "Now on the desktop, set:"
echo "  HERMES_OFFICE_DS_URL       http://<this-host>:${DS_HTTP_PORT}"
echo "  HERMES_OFFICE_JWT_SECRET   <same DS_JWT_SECRET>"
echo "  HERMES_OFFICE_CALLBACK_HOST ${DS_CALLBACK_HOST}"
echo "  HERMES_OFFICE_PREVIEW_PORT ${DS_CALLBACK_PORT}"
