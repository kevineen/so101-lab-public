#!/usr/bin/env bash
# Move SO-101 arm(s) to the nest pose saved from Web Remote
# (~/.cache/so101-lab/home_poses.json). Do not run with Web Remote / LeLab /
# MolmoAct2 robot_client (shared serial).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
CONFIG="${WEB_REMOTE_CONFIG:-$ROOT/configs/so101_dual_cam.yaml}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}:${ROOT}/web_remote:${LEROBOT_DIR}/src${PYTHONPATH:+:$PYTHONPATH}"

echo "Going to nest pose (Web Remote / LeLab / robot_client must be stopped)."
exec "$VENV_PY" -m web_remote.go_home_cli --config "$CONFIG" "$@"
