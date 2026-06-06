#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"
NPM_BIN="$(command -v npm || true)"

mkdir -p "${PROJECT_DIR}/logs"

if [[ -z "${NPM_BIN}" ]]; then
  echo "npm was not found. Install Node.js or Homebrew Node, then try again." >&2
  exit 1
fi

if [[ ! -x "${PROJECT_DIR}/backend/.venv/bin/uvicorn" ]]; then
  echo "Backend virtual environment is missing. Run backend setup first." >&2
  exit 1
fi

if [[ ! -d "${PROJECT_DIR}/frontend/node_modules" ]]; then
  echo "Frontend dependencies are missing; running npm install..."
  (cd "${PROJECT_DIR}/frontend" && "${NPM_BIN}" install)
fi

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill ${pids} 2>/dev/null || true
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  for _ in {1..45}; do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "${label} did not start. Check logs in ${PROJECT_DIR}/logs." >&2
  return 1
}

open_frontend() {
  if [[ -d "/Applications/Google Chrome.app" || -d "${HOME}/Applications/Google Chrome.app" ]]; then
    open -a "Google Chrome" "${FRONTEND_URL}"
  else
    open "${FRONTEND_URL}"
  fi
}

screen -S voicescribe-backend -X quit >/dev/null 2>&1 || true
screen -S voicescribe-frontend -X quit >/dev/null 2>&1 || true
stop_port "${BACKEND_PORT}"
stop_port "${FRONTEND_PORT}"

screen -dmS voicescribe-backend bash -lc "
  export PATH='${PATH}' &&
  cd '${PROJECT_DIR}/backend' &&
  source .venv/bin/activate &&
  export HF_HUB_DISABLE_XET=1 &&
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port '${BACKEND_PORT}' >> '../logs/backend.log' 2>&1
"

screen -dmS voicescribe-frontend bash -lc "
  export PATH='${PATH}' &&
  cd '${PROJECT_DIR}/frontend' &&
  VITE_API_BASE_URL='${BACKEND_URL}/api' '${NPM_BIN}' run dev -- --host 127.0.0.1 --port '${FRONTEND_PORT}' >> '../logs/frontend.log' 2>&1
"

wait_for_url "${BACKEND_URL}/health" "Backend"
wait_for_url "${FRONTEND_URL}" "Frontend"

open_frontend
