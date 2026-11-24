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
