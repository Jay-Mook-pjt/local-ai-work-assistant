#!/usr/bin/env bash
# Stop frontend, worker and backend started by start.sh. Does not touch Ollama.
# The worker gets up to 10 s to finish its current step; an interrupted job is
# marked FAILED (retryable) the next time the worker starts.
source "$(dirname "$0")/_common.sh"

for name in frontend worker backend; do
  pidfile="$RUN_DIR/$name.pid"
  if is_running "$pidfile"; then
    pid="$(cat "$pidfile")"
    pkill -TERM -P "$pid" 2>/dev/null || true   # child processes (reloader / next workers)
    kill -TERM "$pid" 2>/dev/null || true
    for _ in {1..40}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
    echo "$name 중지 (pid $pid)"
  else
    echo "$name 실행 중 아님"
  fi
  rm -f "$pidfile"
done
