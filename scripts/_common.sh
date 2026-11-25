#!/usr/bin/env bash
# Shared paths/env for the helper scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
RUN_DIR="$LOG_DIR/run"
mkdir -p "$RUN_DIR"

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:$PATH"
export NEXT_TELEMETRY_DISABLED=1
# Model libraries must not contact the internet at runtime (see backend/app/offline.py).
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=false

# Settings profile: .env (development, default) or .env.offline (closed network).
export APP_ENV_FILE="${APP_ENV_FILE:-.env}"
ENV_PATH="$ROOT/$APP_ENV_FILE"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="3000"
if [[ -f "$ENV_PATH" ]]; then
  BACKEND_HOST="$(grep -E '^BACKEND_HOST=' "$ENV_PATH" | cut -d= -f2- || true)"; BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
  BACKEND_PORT="$(grep -E '^BACKEND_PORT=' "$ENV_PATH" | cut -d= -f2- || true)"; BACKEND_PORT="${BACKEND_PORT:-8000}"
  FRONTEND_PORT="$(grep -E '^FRONTEND_PORT=' "$ENV_PATH" | cut -d= -f2- || true)"; FRONTEND_PORT="${FRONTEND_PORT:-3000}"
fi

is_running() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }
