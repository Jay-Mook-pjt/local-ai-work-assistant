#!/usr/bin/env bash
# Shared paths/env for the helper scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
RUN_DIR="$LOG_DIR/run"
mkdir -p "$RUN_DIR"

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:$PATH"
export NEXT_TELEMETRY_DISABLED=1

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="3000"
if [[ -f "$ROOT/.env" ]]; then
  BACKEND_HOST="$(grep -E '^BACKEND_HOST=' "$ROOT/.env" | cut -d= -f2- || true)"; BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
  BACKEND_PORT="$(grep -E '^BACKEND_PORT=' "$ROOT/.env" | cut -d= -f2- || true)"; BACKEND_PORT="${BACKEND_PORT:-8000}"
fi

is_running() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }
