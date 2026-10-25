#!/usr/bin/env bash
# Main PC Phase C: Quest retarget → contract JSONL (no Pi / SO-101).
# Docs: docs/09_bridge_contract.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ISAAC_TELEOP_VENV:-$HOME/robot/isaac-teleop-env/.venv}"
OUT="${1:-$ROOT/data/quest_teleop/$(date +%Y%m%d_%H%M%S).jsonl}"
DURATION="${DURATION:-20}"
ARMS="${ARMS:-right}"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "ERROR: teleop venv not found: ${VENV}" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Main PC LAN IP: ${HOST_IP:-unknown}"
echo "Quest (Meta Quest Browser): https://${HOST_IP:-<IP>}:48322/client/"
echo "Output: ${OUT}"
echo "----"

exec python -m bridges.isaacteleop_to_so101.record_quest \
  --out "${OUT}" \
  --duration "${DURATION}" \
  --arms "${ARMS}" \
  -v \
  "${@:2}"
