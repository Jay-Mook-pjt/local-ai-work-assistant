#!/usr/bin/env bash
# Start backend (localhost only) and frontend (LAN) in the background.
# Usage: scripts/start.sh [dev|prod]   (default: dev)
source "$(dirname "$0")/_common.sh"
MODE="${1:-dev}"

if ! curl -fsS -m 2 http://127.0.0.1:11434/api/version >/dev/null; then
  echo "⚠️  Ollama가 응답하지 않습니다. 'brew services start ollama'로 실행하세요."
fi

if is_running "$RUN_DIR/backend.pid"; then
  echo "backend 이미 실행 중 (pid $(cat "$RUN_DIR/backend.pid"))"
else
  cd "$ROOT/backend"
  RELOAD=""; [[ "$MODE" == "dev" ]] && RELOAD="--reload"
  nohup .venv/bin/uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" $RELOAD \
    >>"$LOG_DIR/backend.out.log" 2>&1 &
  echo $! >"$RUN_DIR/backend.pid"
  echo "backend 시작: http://$BACKEND_HOST:$BACKEND_PORT (pid $!)"
fi

if is_running "$RUN_DIR/worker.pid"; then
  echo "worker 이미 실행 중 (pid $(cat "$RUN_DIR/worker.pid"))"
else
  cd "$ROOT/backend"
  nohup .venv/bin/python -m worker.main >>"$LOG_DIR/worker.out.log" 2>&1 &
  echo $! >"$RUN_DIR/worker.pid"
  echo "worker 시작 (pid $!)"
fi

if is_running "$RUN_DIR/frontend.pid"; then
  echo "frontend 이미 실행 중 (pid $(cat "$RUN_DIR/frontend.pid"))"
else
  cd "$ROOT/frontend"
  if [[ "$MODE" == "prod" ]]; then
    npm run build >>"$LOG_DIR/frontend.out.log" 2>&1
    nohup npx next start -H "$FRONTEND_HOST" -p "$FRONTEND_PORT" >>"$LOG_DIR/frontend.out.log" 2>&1 &
  else
    nohup npx next dev -H "$FRONTEND_HOST" -p "$FRONTEND_PORT" >>"$LOG_DIR/frontend.out.log" 2>&1 &
  fi
  echo $! >"$RUN_DIR/frontend.pid"
  echo "frontend 시작: http://localhost:$FRONTEND_PORT (pid $!)"
fi
