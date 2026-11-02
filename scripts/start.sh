#!/usr/bin/env bash
# Starts local ComfyUI (if installed) and the studio, then opens it in your browser.
# Ctrl+C (or closing the window) stops both.
set -uo pipefail
APP="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${HIGGS_RUNTIME_DIR:-$(dirname "$APP")/runtime}"
PORT="${HIGGS_PORT:-7860}"
COMFY_PORT="${HIGGS_COMFY_PORT:-8188}"
LOGS="$APP/data/logs"; mkdir -p "$LOGS"
export HIGGS_RUNTIME_DIR="$RUNTIME"
export PATH="$RUNTIME/bin:$PATH"

[ -x "$APP/backend/.venv/bin/python" ] || { echo "Not installed yet. Run: bash \"$APP/scripts/install.sh\""; exit 1; }

PIDS=()
cleanup() { echo; echo "Stopping HIGGS Studio…"; for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; exit 0; }
trap cleanup INT TERM HUP

port_open() { (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null; }

if [ -d "$RUNTIME/ComfyUI" ] && [ -x "$RUNTIME/venv/bin/python" ]; then
  if port_open "$COMFY_PORT"; then
    echo "ComfyUI already running on :$COMFY_PORT"
  else
    EXTRA=()
    if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "x86_64" ]; then EXTRA=(--cpu); fi
    if [ "$(uname -s)" = "Linux" ] && ! command -v nvidia-smi >/dev/null 2>&1; then EXTRA=(--cpu); fi
    echo "Starting local ComfyUI on :$COMFY_PORT ${EXTRA[*]:-} (log: $LOGS/comfyui.log)"
    (cd "$RUNTIME/ComfyUI" && exec "$RUNTIME/venv/bin/python" main.py --listen 127.0.0.1 --port "$COMFY_PORT" \
        --preview-method none "${EXTRA[@]}" >"$LOGS/comfyui.log" 2>&1) &
    PIDS+=($!)
  fi
else
  echo "Local ComfyUI not installed. That's fine if you generate on Kaggle (Settings → Kaggle free GPU)."
fi

echo "Starting HIGGS Studio on http://127.0.0.1:$PORT (log: $LOGS/studio.log)"
(cd "$APP/backend" && exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$LOGS/studio.log" 2>&1) &
PIDS+=($!)

for _ in $(seq 1 60); do port_open "$PORT" && break; sleep 0.5; done
if port_open "$PORT"; then
  URL="http://127.0.0.1:$PORT"
  echo; echo "  ✦ HIGGS Studio is running at $URL"; echo "    Keep this window open. Press Ctrl+C to stop."; echo
  if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1; fi
else
  echo "The studio didn't start. Last log lines:"; tail -n 30 "$LOGS/studio.log"; cleanup
fi
wait
