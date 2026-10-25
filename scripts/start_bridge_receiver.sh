#!/usr/bin/env bash
# Pi: Isaac Teleop → SO-101 dual-arm bridge receiver (WebSocket).
# Do NOT run with LeLab / Web Remote (shared serial).
#
# Quest tip tracking (relative EE):
#   BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v
# Demo / dry-run without placo (default):
#   ./scripts/start_bridge_receiver.sh --dry-run -v
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
CONFIG="${BRIDGE_CONFIG:-$ROOT/configs/so101_dual_cam.yaml}"
TELEOP_CONFIG="${BRIDGE_TELEOP_CONFIG:-$ROOT/configs/quest_teleop.yaml}"
URDF="${BRIDGE_URDF:-$ROOT/assets/robots/so101/so101.urdf}"
HOST="${BRIDGE_HOST:-0.0.0.0}"
PORT="${BRIDGE_PORT:-8870}"
# approx (default) | relative | placo | none
IK="${BRIDGE_IK:-approx}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config not found: $CONFIG" >&2
  exit 1
fi

"$VENV_PY" -c "import websockets, yaml" 2>/dev/null || {
  echo "Installing bridge deps into lerobot venv via uv..."
  uv pip install --python "$VENV_PY" websockets pyyaml
}

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH="${LEROBOT_DIR}/src:${PYTHONPATH}"

IK_ARGS=(--ik "$IK")
if [[ "$IK" == "relative" || "$IK" == "placo" ]]; then
  if [[ ! -f "$URDF" ]]; then
    echo "ERROR: URDF not found: $URDF" >&2
    exit 1
  fi
  IK_ARGS+=(--urdf "$URDF")
fi
if [[ "$IK" == "relative" ]]; then
  if [[ ! -f "$TELEOP_CONFIG" ]]; then
    echo "ERROR: teleop config not found: $TELEOP_CONFIG" >&2
    exit 1
  fi
  IK_ARGS+=(--teleop-config "$TELEOP_CONFIG")
fi

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Bridge receiver ws://${HOST}:${PORT}/teleop"
if [[ -n "${LAN_IP}" ]]; then
  echo "From main PC: python -m bridges.isaacteleop_to_so101.sender --host ${LAN_IP} --demo-bimanual"
fi
echo "Config: $CONFIG"
echo "IK: $IK${URDF:+  urdf=$URDF}"
echo "Stop LeLab / Web Remote first. Ctrl+C to stop."

exec "$VENV_PY" -m bridges.isaacteleop_to_so101.receiver \
  --config "$CONFIG" \
  --host "$HOST" \
  --port "$PORT" \
  "${IK_ARGS[@]}" \
  "$@"
