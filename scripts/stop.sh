#!/usr/bin/env bash
# Stop backend and frontend started by start.sh. Does not touch Ollama.
source "$(dirname "$0")/_common.sh"

for name in frontend backend; do
  pidfile="$RUN_DIR/$name.pid"
  if is_running "$pidfile"; then
    pid="$(cat "$pidfile")"
    pkill -TERM -P "$pid" 2>/dev/null || true   # child processes (reloader / next workers)
    kill -TERM "$pid" 2>/dev/null || true
    for _ in {1..20}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
    echo "$name 중지 (pid $pid)"
  else
    echo "$name 실행 중 아님"
  fi
  rm -f "$pidfile"
done
