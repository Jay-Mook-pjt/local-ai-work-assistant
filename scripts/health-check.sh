#!/usr/bin/env bash
# Check Ollama, backend and frontend. Exit code 0 only if everything is healthy.
source "$(dirname "$0")/_common.sh"
fail=0

check() {
  local name="$1" url="$2"
  if out="$(curl -fsS -m 5 "$url" 2>&1)"; then echo "✅ $name"; else echo "❌ $name: $out"; fail=1; fi
}

check "Ollama   (127.0.0.1:11434)" "http://127.0.0.1:11434/api/version"
check "Backend  ($BACKEND_HOST:$BACKEND_PORT)" "http://$BACKEND_HOST:$BACKEND_PORT/api/health"
check "Frontend (:$FRONTEND_PORT)" "http://127.0.0.1:$FRONTEND_PORT/"
check "Frontend → Backend proxy" "http://127.0.0.1:$FRONTEND_PORT/api/health"

if is_running "$RUN_DIR/worker.pid"; then echo "✅ Worker   (pid $(cat "$RUN_DIR/worker.pid"))"; else echo "❌ Worker   실행 중 아님"; fail=1; fi

# Offline settings actually present in the running processes (not just in files).
proc_env() { ps eww -p "$1" 2>/dev/null | tr ' ' '\n' | grep -E "^$2=" | head -1 | cut -d= -f2-; }
check_env() {  # name pid VAR expected
  local v; v="$(proc_env "$2" "$3")"
  if [[ "$v" == "$4" ]]; then echo "✅ $1 $3=$v"; else echo "❌ $1 $3=${v:-(없음)} (기대값 $4)"; fail=1; fi
}
echo "— 오프라인 설정 (실행 중인 프로세스 기준, 설정 파일: $APP_ENV_FILE)"
for name in worker backend; do
  if is_running "$RUN_DIR/$name.pid"; then
    pid="$(cat "$RUN_DIR/$name.pid")"
    check_env "$name" "$pid" HF_HUB_OFFLINE 1
    check_env "$name" "$pid" PYANNOTE_METRICS_ENABLED false
  fi
done
opid="$(pgrep -f '/ollama serve' | head -1 || true)"
if [[ -n "$opid" ]]; then
  check_env ollama "$opid" OLLAMA_NO_CLOUD 1
  [[ "$(proc_env "$opid" OLLAMA_NO_CLOUD)" == "1" ]] || echo "   → scripts/ollama-offline.sh apply 로 적용하세요 (brew services restart 후 다시 필요)"
fi

if health="$(curl -fsS -m 10 "http://$BACKEND_HOST:$BACKEND_PORT/api/health" 2>/dev/null)"; then
  echo "$health" | /usr/bin/python3 -c '
import json, sys
d = json.load(sys.stdin)
print("   status=%s llm=%s" % (d["status"], d["llm_model"]))
for k, c in d["components"].items():
    mark = "OK " if c["ok"] else "ERR"
    print("   [%s] %s: %s" % (mark, k, c.get("detail") or c.get("version") or "ok"))
'
  [[ "$health" == *'"status":"ok"'* ]] || fail=1
fi
exit $fail
