#!/usr/bin/env bash
# Run MolmoAct2 robot_client, then return both arms to the saved nest pose.
#
# Usage:
#   ./scripts/run_molmoact2_client.sh --server_address=<THOR_IP>:8080 [extra lerobot args...]
#
# Nest pose must be saved first from Web Remote (「初期位置を保存」).
# Web Remote must be stopped before this script opens the serial ports.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ラボ固有の実値（アームの by-id パス等）。テンプレート: configs/lab.local.env.example
if [[ -f "$ROOT/configs/lab.local.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/configs/lab.local.env"
  set +a
fi
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
GO_HOME="${GO_HOME:-1}"

if [[ ! -d "$LEROBOT_DIR" ]]; then
  echo "ERROR: lerobot checkout missing at $LEROBOT_DIR" >&2
  exit 1
fi

cleanup() {
  local code=$?
  if [[ "$GO_HOME" == "1" ]]; then
    echo ""
    echo "=== Returning arms to nest pose (GO_HOME=1) ==="
    # Always try go-home even if the client crashed; ignore its exit for the trap.
    "$ROOT/scripts/go_so101_home.sh" || echo "WARN: go_so101_home failed (arms may need manual recovery)" >&2
  else
    echo "GO_HOME=0 — skipped nest return. Run ./scripts/go_so101_home.sh when ready."
  fi
  exit "$code"
}
trap cleanup EXIT

cd "$LEROBOT_DIR"
echo "Starting MolmoAct2 robot_client (Ctrl+C ends episode → nest return)..."
# Defaults match docs/10_molmoact2_thor.md; override via extra args.
# アームの by-id パスは configs/lab.local.env の SO101_FOLLOWER_PORT / SO101_LEADER_PORT。
LEFT_PORT="${SO101_FOLLOWER_PORT:?set SO101_FOLLOWER_PORT in configs/lab.local.env}"
RIGHT_PORT="${SO101_LEADER_PORT:?set SO101_LEADER_PORT in configs/lab.local.env}"
uv run python -m lerobot.async_inference.robot_client \
  --robot.type=bi_so_follower \
  --robot.id=so101_bi \
  --robot.left_arm_config.port="$LEFT_PORT" \
  --robot.right_arm_config.port="$RIGHT_PORT" \
  --robot.left_arm_config.max_relative_target=5 \
  --robot.right_arm_config.max_relative_target=5 \
  --robot.left_arm_config.disable_torque_on_disconnect=false \
  --robot.right_arm_config.disable_torque_on_disconnect=false \
  --policy_type=molmoact2 \
  --client_device=cpu \
  --actions_per_chunk=10 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=30 \
  "$@"
