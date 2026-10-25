#!/usr/bin/env bash
# Re-enable torque on both SO-101 arms and hold the measured pose.
# Use after a limp/drop (e.g. process exit that disabled torque).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
CONFIG="${BRIDGE_CONFIG:-$ROOT/configs/so101_dual_cam.yaml}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}:${LEROBOT_DIR}/src${PYTHONPATH:+:$PYTHONPATH}"
export BRIDGE_CONFIG="$CONFIG"

exec "$VENV_PY" -m bridges.isaacteleop_to_so101.hold_torque
