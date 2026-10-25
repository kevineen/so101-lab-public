#!/usr/bin/env bash
# Main PC Phase D: Quest live → contract JSON → Pi bridge → SO-101.
# Pi must already run (relative EE tip tracking):
#   BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v
#   ./scripts/start_camera_server.sh   # cameras-only MJPEG for Quest planes
# Docs: docs/09_bridge_contract.md · docs/11_quest_teleop_runbook.md · configs/quest_teleop.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ISAAC_TELEOP_VENV:-$HOME/robot/isaac-teleop-env/.venv}"
PI_HOST="${1:-}"
# 0 = unlimited until Ctrl+C (default). Example timed run: DURATION=60
DURATION="${DURATION:-0}"
CONFIG="${QUEST_TELEOP_CONFIG:-$ROOT/configs/quest_teleop.yaml}"
ARMS="${ARMS:-from-config}"

if [[ -z "$PI_HOST" ]]; then
  echo "Usage: $0 <Pi_LAN_IP> [extra live_quest args...]" >&2
  echo "Example: $0 <pi-lan-ip>   # configs/lab.local.env の SO101_PI_LAN_IP" >&2
  echo "  DURATION=60 ARMS=both $0 <pi-lan-ip>   # timed smoke test" >&2
  echo "Clutch: hold A (right) / X (left) to follow — see configs/quest_teleop.yaml" >&2
  exit 2
fi
shift || true

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "ERROR: teleop venv not found: ${VENV}" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$HOME/.local/bin:${PATH}"

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Main PC: ${HOST_IP:-unknown}"
echo "Pi bridge: ws://${PI_HOST}:8870/teleop"
echo "Pi cameras: http://${PI_HOST}:8765/ (cameras-only)"
echo "Quest: https://${HOST_IP:-<IP>}:48322/client/  (Meta Quest Browser)"
GO_HOME_FLAG=()
case "${GO_HOME:-1}" in
  0|false|False|no|NO) GO_HOME_FLAG+=(--no-go-home) ;;
  *) GO_HOME_FLAG+=(--go-home) ;;
esac

echo "Config: ${CONFIG}"
echo "Clutch: hold primary button (A/X) to drive; release to hold pose."
echo "On connect: go_home to nest (GO_HOME=0 to skip)."
if [[ "${DURATION}" == "0" || "${DURATION}" == "0.0" ]]; then
  echo "Duration: unlimited — stop with Ctrl+C"
else
  echo "Duration: ${DURATION}s"
fi
echo "Pi must already run: BRIDGE_IK=relative ./scripts/start_bridge_receiver.sh -v"
echo "In-Quest settings (pause CloudXR → Browser):"
echo "  ./scripts/start_quest_teleop_settings.sh ${PI_HOST}"
echo "  → http://${HOST_IP:-<IP>}:8766/"
echo "----"

exec python -m bridges.isaacteleop_to_so101.live_quest \
  --host "${PI_HOST}" \
  --duration "${DURATION}" \
  --arms "${ARMS}" \
  --config "${CONFIG}" \
  "${GO_HOME_FLAG[@]}" \
  -v \
  "$@"
