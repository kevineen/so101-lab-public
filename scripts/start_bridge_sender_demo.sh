#!/usr/bin/env bash
# Main PC (or any host): send bimanual joint demo to Pi bridge receiver.
# Default: go_home to Web Remote nest, then sinusoid around nest.
# Skip nest: GO_HOME=0 ./scripts/start_bridge_sender_demo.sh <Pi_IP> --duration 20
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Prefer lab lerobot venv if present; else current python.
# 解決順序: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
LEROBOT_DIR="${LEROBOT_DIR:-}"
if [[ -z "$LEROBOT_DIR" ]]; then
  if [[ -d "$HOME/robot/lerobot" ]]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
if [[ -x "${LEROBOT_DIR}/.venv/bin/python" ]]; then
  PY="${LEROBOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null; then
  PY="$(command -v python3)"
else
  echo "ERROR: no python3" >&2
  exit 1
fi

HOST="${1:-}"
if [[ -z "$HOST" ]]; then
  echo "Usage: $0 <Pi_LAN_IP> [extra sender args...]" >&2
  echo "Example: $0 <pi-lan-ip> --duration 20   # IP は configs/lab.local.env の SO101_PI_LAN_IP" >&2
  echo "  GO_HOME=0 $0 <pi-lan-ip> --duration 20   # skip nest approach" >&2
  exit 2
fi
shift || true

"$PY" -c "import websockets" 2>/dev/null || {
  echo "Installing websockets..."
  if command -v uv >/dev/null; then
    uv pip install --python "$PY" websockets
  else
    "$PY" -m pip install websockets
  fi
}

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

GO_HOME_FLAG=()
case "${GO_HOME:-1}" in
  0|false|False|no|NO) GO_HOME_FLAG+=(--no-go-home) ;;
  *) GO_HOME_FLAG+=(--go-home) ;;
esac

echo "Pi bridge: ws://${HOST}:8870/teleop"
echo "On connect: go_home to nest (GO_HOME=0 to skip), then demo."

exec "$PY" -m bridges.isaacteleop_to_so101.sender \
  --host "$HOST" \
  --demo-bimanual \
  "${GO_HOME_FLAG[@]}" \
  "$@"
