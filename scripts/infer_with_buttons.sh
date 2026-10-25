#!/usr/bin/env bash
# robot_client plus a phone page for Start / Pause / Success / Failure.
# Arguments are forwarded to lerobot.async_inference.robot_client.
# This process does not open Web Remote and claims the follower serial.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ラボ固有の実値（IP・シリアル等）。テンプレート: configs/lab.local.env.example
if [[ -f "$ROOT/configs/lab.local.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/configs/lab.local.env"
  set +a
fi
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
PORT="${SO101_INFER_BUTTONS_PORT:-8771}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH="${LEROBOT_DIR}/src:${PYTHONPATH}"

# Optional: pull task / model label from argv for the phone header.
for arg in "$@"; do
  case "$arg" in
    --task=*) export SO101_INFER_TASK="${arg#--task=}" ;;
    --policy_type=*) export SO101_INFER_POLICY_TYPE="${arg#--policy_type=}" ;;
    --pretrained_name_or_path=*) export SO101_INFER_MODEL="${arg#--pretrained_name_or_path=}" ;;
  esac
done

# Model catalog: SO101_INFER_MODELS env → configs/infer_models.local.json
# (gitignored, real checkpoint paths) → configs/infer_models.snakebowl.json (example).
if [[ -z "${SO101_INFER_MODELS:-}" ]]; then
  if [[ -f "$ROOT/configs/infer_models.local.json" ]]; then
    export SO101_INFER_MODELS="$ROOT/configs/infer_models.local.json"
  else
    export SO101_INFER_MODELS="$ROOT/configs/infer_models.snakebowl.json"
  fi
fi

echo "Phone infer controls listen on port ${PORT} after the robot connects (trials, cameras, start / pause / result / model switch)."
echo "Keep LeLab and Web Remote stopped (they share the serial ports)."
echo "Default timeout ${SO101_INFER_TIMEOUT_S:-60}s · trials ${SO101_INFER_TRIALS:-10}."
echo "Model catalog: ${MODELS_FILE}"
if [[ "${SO101_INFER_INCLUDE_OPTIONAL:-0}" == "1" ]]; then
  echo "Optional catalog rows included (SO101_INFER_INCLUDE_OPTIONAL=1)."
fi
echo "ESTOP stays on the desk. This page does not cut torque."

exec "$VENV_PY" -m infer_buttons.cli "$@"
