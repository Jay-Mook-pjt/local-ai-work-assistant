#!/usr/bin/env bash
# Closed-network integration test.
# Runs Ollama, Backend, Worker, Frontend and a localhost SMTP relay inside a macOS
# sandbox that blocks every outbound connection and DNS (loopback only), with an
# isolated database/storage, then drives the app end to end.
#
# The regular services are stopped during the test and started again afterwards.
# The regular Homebrew Ollama service keeps running; the sandboxed copy listens on
# :11435 and reads the same model store (OLLAMA_NOPRUNE so nothing is deleted).
set -euo pipefail
source "$(dirname "$0")/../_common.sh"
SB="$ROOT/scripts/offline/no-network.sb"
DATA="$(mktemp -d -t lawa-offline-data)"
OLLAMA_PORT=11435
PIDS=()
# Variables this test overrides. They are exported only for the sandboxed stack and
# must be removed before the regular services are started again (otherwise those
# would keep using the test database/storage/Ollama port).
TEST_VARS=(DATABASE_URL STORAGE_DIR LOG_DIR OLLAMA_BASE_URL DIARIZATION_ENABLED LLM_ALLOW_CLOUD
  SMTP_HOST SMTP_PORT SMTP_USE_TLS SMTP_USERNAME SMTP_PASSWORD SMTP_KEYCHAIN_SERVICE SMTP_FROM HF_HOME)

cleanup() {
  for p in "${PIDS[@]:-}"; do [[ -n "$p" ]] && { pkill -TERM -P "$p" 2>/dev/null || true; kill -TERM "$p" 2>/dev/null || true; }; done
  sleep 2
  unset "${TEST_VARS[@]}"
  "$ROOT/scripts/start.sh" >/dev/null
  echo "[offline] 정상 서비스 재시작 완료. 테스트 데이터: $DATA (확인 후 삭제 가능)"
}
trap cleanup EXIT

"$ROOT/scripts/stop.sh" >/dev/null
mkdir -p "$DATA"/{storage,logs,mailbox/cur,mailbox/new,mailbox/tmp}
export DATABASE_URL="sqlite:///$DATA/meeting.db" STORAGE_DIR="$DATA/storage" LOG_DIR="$DATA/logs"
export OLLAMA_BASE_URL="http://127.0.0.1:$OLLAMA_PORT" DIARIZATION_ENABLED=true LLM_ALLOW_CLOUD=false
export SMTP_HOST=127.0.0.1 SMTP_PORT=2525 SMTP_USE_TLS=false SMTP_USERNAME= SMTP_PASSWORD= SMTP_KEYCHAIN_SERVICE= SMTP_FROM=minutes@internal.test
export HF_HOME="$DATA/empty-hf-home"   # no Hugging Face cache: models must come from models/

run_sb() { sandbox-exec -f "$SB" "$@"; }

echo "[offline] sandboxed Ollama :$OLLAMA_PORT"
OLLAMA_HOST="127.0.0.1:$OLLAMA_PORT" OLLAMA_NO_CLOUD=1 OLLAMA_NOPRUNE=1 \
  run_sb /opt/homebrew/opt/ollama/bin/ollama serve >"$DATA/logs/ollama.log" 2>&1 & PIDS+=($!)
echo "[offline] sandboxed SMTP relay :2525 (stands in for an internal mail server)"
(cd "$ROOT/backend" && run_sb .venv/bin/python -m aiosmtpd -n -l 127.0.0.1:2525 -c aiosmtpd.handlers.Mailbox "$DATA/mailbox" >"$DATA/logs/smtp.log" 2>&1) & PIDS+=($!)
echo "[offline] sandboxed Backend / Worker / Frontend"
(cd "$ROOT/backend" && run_sb .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" >"$DATA/logs/backend.out.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/backend" && run_sb .venv/bin/python -m worker.main >"$DATA/logs/worker.out.log" 2>&1) & PIDS+=($!)
(cd "$ROOT/frontend" && npm run build >"$DATA/logs/frontend-build.log" 2>&1 && run_sb npx next start -H 127.0.0.1 -p "$FRONTEND_PORT" >"$DATA/logs/frontend.out.log" 2>&1) & PIDS+=($!)

for _ in {1..120}; do curl -fsS -m 2 "http://127.0.0.1:$FRONTEND_PORT/api/health" >/dev/null 2>&1 && break; sleep 1; done
# collect the real process ids (sandbox-exec execs the target, wrappers are subshells)
ALL=$(for p in "${PIDS[@]}"; do echo "$p"; pgrep -P "$p" || true; for c in $(pgrep -P "$p" || true); do pgrep -P "$c" || true; done; done | sort -u | tr '\n' ' ')

cd "$ROOT/backend"
OFFLINE_DATA_DIR="$DATA" OFFLINE_PIDS="$ALL" E2E_OLLAMA="http://127.0.0.1:$OLLAMA_PORT" E2E_LOG_DIR="$DATA/logs" \
  .venv/bin/python -u -m tests.integration.offline_check
