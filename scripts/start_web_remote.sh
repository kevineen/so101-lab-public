#!/usr/bin/env bash
# Start SO-101 Web Remote (browser joint teleop + camera MJPEG) on the LAN.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
CONFIG="${WEB_REMOTE_CONFIG:-$ROOT/configs/so101_dual_cam.yaml}"
HOST="${WEB_REMOTE_HOST:-0.0.0.0}"
PORT="${WEB_REMOTE_PORT:-8765}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config not found: $CONFIG" >&2
  exit 1
fi

# Ensure robot + web + camera deps are available in the lerobot venv (idempotent).
"$VENV_PY" -c "import fastapi, uvicorn, yaml, scservo_sdk, deepdiff, pyrealsense2, cv2" 2>/dev/null || {
  echo "Installing web_remote deps into lerobot venv via uv..."
  uv pip install --python "$VENV_PY" \
    fastapi "uvicorn[standard]" pyyaml \
    feetech-servo-sdk pyserial deepdiff \
    pyrealsense2 opencv-python-headless
}

export PYTHONPATH="${ROOT}:${ROOT}/web_remote${PYTHONPATH:+:$PYTHONPATH}"
# Prefer the editable lerobot package from the local checkout.
export PYTHONPATH="${LEROBOT_DIR}/src:${PYTHONPATH}"

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Starting Web Remote on http://${HOST}:${PORT}/"
if [[ -n "${LAN_IP}" ]]; then
  echo "Open from another PC: http://${LAN_IP}:${PORT}/"
fi
echo "Config: $CONFIG"
if [[ -n "${CENTER_SOURCE:-}" ]]; then
  echo "CENTER_SOURCE=${CENTER_SOURCE} (overrides yaml center_source)"
fi
echo "Do not run LeLab at the same time (shared serial / cameras)."
echo "Press Ctrl+C to stop."

# Default 40 Hz motor loop (override with --control-hz / WEB_REMOTE_CONTROL_HZ).
CONTROL_HZ="${WEB_REMOTE_CONTROL_HZ:-40}"

exec "$VENV_PY" -m web_remote.server \
  --config "$CONFIG" \
  --host "$HOST" \
  --port "$PORT" \
  --control-hz "$CONTROL_HZ" \
  "$@"
