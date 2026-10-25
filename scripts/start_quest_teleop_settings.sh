#!/usr/bin/env bash
# Quest Browser–friendly teleop settings UI (run on main PC).
# Save writes local overrides and pushes to Pi bridge when PI_HOST is set.
#
#   ./scripts/start_quest_teleop_settings.sh <pi-lan-ip>
#   （Pi の IP は configs/lab.local.env の SO101_PI_LAN_IP）
# Quest: pause CloudXR → Browser → http://<MainPC>:8766/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ISAAC_TELEOP_VENV:-$HOME/robot/isaac-teleop-env/.venv}"
CONFIG="${QUEST_TELEOP_CONFIG:-$ROOT/configs/quest_teleop.yaml}"
PORT="${QUEST_SETTINGS_PORT:-8766}"
PI_HOST="${1:-${PI_HOST:-}}"

if [[ -n "${1:-}" ]]; then
  shift || true
fi

if [[ -x "${VENV}/bin/python" ]]; then
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

EXTRA=()
if [[ -n "$PI_HOST" ]]; then
  EXTRA+=(--bridge-host "$PI_HOST")
fi

exec python -m bridges.isaacteleop_to_so101.settings_ui \
  --config "${CONFIG}" \
  --port "${PORT}" \
  "${EXTRA[@]}" \
  "$@"
