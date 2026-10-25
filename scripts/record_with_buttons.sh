#!/usr/bin/env bash
# lerobot-record plus a phone page for Start / Stop / keep on the same Wi-Fi.
# Arguments are forwarded to lerobot-record. This process does not open the
# Web Remote port and does not claim the arm serial ports by itself.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
PORT="${SO101_RECORD_BUTTONS_PORT:-8770}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH="${LEROBOT_DIR}/src:${PYTHONPATH}"

# ラボ固有の実値（IP・シリアル等）。テンプレート: configs/lab.local.env.example
LAB_ENV="$ROOT/configs/lab.local.env"
if [[ -f "$LAB_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$LAB_ENV"
  set +a
fi

# Destination IP changes often. The file is gitignored; see dataset.local.env.example.
LOCAL_ENV="${SO101_DATASET_ENV:-$ROOT/configs/dataset.local.env}"
if [[ -f "$LOCAL_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$LOCAL_ENV"
  set +a
fi

echo "Phone controls listen on port ${PORT} after the robot connects (episode, cameras, record time, start / stop / pause)."
echo "Keep LeLab and Web Remote stopped (they share the serial ports)."
if [[ "${SO101_RECORD_GO_HOME:-1}" != "0" ]]; then
  echo "Ready phase starts in leader follow; phone nest toggle holds both arms at nest (SO101_RECORD_GO_HOME=0 disables nest)."
fi
if [[ -n "${SO101_DATASET_SSH:-}" ]]; then
  echo "Kept episodes sync to ${SO101_DATASET_SSH}:${SO101_DATASET_DIR:-} before the next Start (Pi copy removed after the final sync)."
else
  echo "SO101_DATASET_SSH is empty. The dataset stays on this Pi."
fi

# Pi 4 + depth: encode after the take so the control loop stays responsive.
# Override with an explicit --dataset.streaming_encoding=... or SO101_RECORD_STREAMING_ENCODING=1.
DEFAULT_ARGS=()
has_streaming=0
for arg in "$@"; do
  case "$arg" in
    --dataset.streaming_encoding|--dataset.streaming_encoding=*) has_streaming=1 ;;
  esac
done
if [[ "$has_streaming" -eq 0 ]]; then
  if [[ "${SO101_RECORD_STREAMING_ENCODING:-0}" == "1" ]]; then
    DEFAULT_ARGS+=(--dataset.streaming_encoding=true)
    echo "Streaming encoding ON (SO101_RECORD_STREAMING_ENCODING=1)."
  else
    DEFAULT_ARGS+=(--dataset.streaming_encoding=false)
    echo "Streaming encoding OFF (default). Encode after each kept take; pass --dataset.streaming_encoding=true to override."
  fi
fi

exec "$VENV_PY" -m record_buttons.cli "${DEFAULT_ARGS[@]}" "$@"
