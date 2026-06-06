#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill ${pids} 2>/dev/null || true
  fi
}

screen -S voicescribe-backend -X quit >/dev/null 2>&1 || true
screen -S voicescribe-frontend -X quit >/dev/null 2>&1 || true
stop_port "${BACKEND_PORT}"
stop_port "${FRONTEND_PORT}"
