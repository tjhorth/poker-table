#!/usr/bin/env bash
# Runs the simulated table and the dealer UI together so the UI can be tried
# on an iPad (or any device on the same Wi-Fi). Ctrl+C stops both.
#
#   ./scripts/dev-ipad.sh            # normal pace
#   SIM_SPEED=0.3 ./scripts/dev-ipad.sh   # faster simulated hands
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
export SIM_SPEED="${SIM_SPEED:-0.6}"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python3"
fi

cleanup() {
  trap - INT TERM EXIT
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${UI_PID:-}" ] && kill "$UI_PID" 2>/dev/null || true
  echo; echo "Stopped."
}
trap cleanup INT TERM EXIT

cd "$ROOT"
# `python -m api` reads api/config.py (host, port, WebSocket keep-alive, ...)
POKER_HOST=0.0.0.0 POKER_PORT="$API_PORT" "$PYTHON" -m api &
API_PID=$!

cd "$ROOT/web/dealer"
# BROWSER=none stops Vite opening a window on this Mac
BROWSER=none npx vite --host --port "$UI_PORT" --strictPort &
UI_PID=$!

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '<this-mac-ip>')"
HOST="$(scutil --get LocalHostName 2>/dev/null || echo '')"
sleep 3
cat <<MSG

────────────────────────────────────────────────────────────
  Simulated table is running.

  On the iPad (same Wi-Fi), open Safari and go to:

      http://$IP:$UI_PORT
$( [ -n "$HOST" ] && echo "      http://$HOST.local:$UI_PORT   (if the address above changes)" )

  Overlay for OBS / a second browser tab:

      http://$IP:$API_PORT/overlay/index.html?ws=ws://$IP:$API_PORT/ws/overlay

  PIN for the Configs tab: ${VITE_DEALER_PIN:-1234}
  Ctrl+C here stops everything.
────────────────────────────────────────────────────────────

MSG
wait
