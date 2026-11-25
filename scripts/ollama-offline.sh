#!/usr/bin/env bash
# Configure the Homebrew Ollama service for closed-network use.
#   scripts/ollama-offline.sh status   # show the environment of the running server
#   scripts/ollama-offline.sh apply    # OLLAMA_NO_CLOUD=1, localhost only; restart Ollama
#   scripts/ollama-offline.sh revert   # remove those keys; restart Ollama
#
# Note: `brew services restart ollama` re-copies Homebrew's plist and drops these
# settings — run `apply` again afterwards (health-check.sh warns when it is missing).
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/sh.brew.ollama.plist"
LABEL="sh.brew.ollama"
PB=/usr/libexec/PlistBuddy
# KEY=VALUE pairs (macOS ships bash 3.2: no associative arrays)
WANT="OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434"

running_env() {
  local pid; pid="$(pgrep -f '/ollama serve' | head -1 || true)"
  [[ -n "$pid" ]] || { echo "(ollama serve 실행 중 아님)"; return; }
  ps eww -p "$pid" | tr ' ' '\n' | grep -E '^OLLAMA_' || echo "(OLLAMA_* 환경변수 없음)"
}

restart() {
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$UID" "$PLIST"
  for _ in {1..30}; do curl -fsS -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && return; sleep 1; done
  echo "Ollama가 다시 시작되지 않았습니다. /opt/homebrew/var/log/ollama.log 를 확인하세요." >&2; exit 1
}

[[ -f "$PLIST" ]] || { echo "$PLIST 없음 — 'brew services start ollama'로 먼저 등록하세요." >&2; exit 1; }
case "${1:-status}" in
  status)
    echo "실행 중인 Ollama 서버 환경:"; running_env ;;
  apply)
    cp "$PLIST" "$PLIST.bak"
    for kv in $WANT; do
      k="${kv%%=*}"; v="${kv#*=}"
      $PB -c "Delete :EnvironmentVariables:$k" "$PLIST" 2>/dev/null || true
      $PB -c "Add :EnvironmentVariables:$k string $v" "$PLIST"
    done
    restart; echo "적용 완료 (백업: $PLIST.bak)"; running_env ;;
  revert)
    for kv in $WANT; do $PB -c "Delete :EnvironmentVariables:${kv%%=*}" "$PLIST" 2>/dev/null || true; done
    restart; echo "되돌림 완료"; running_env ;;
  *) echo "usage: $0 status|apply|revert" >&2; exit 2 ;;
esac
