#!/usr/bin/env bash
# Main PC: Quest 3 / CloudXR 疎通確認（アーム不要・Phase B）
# 手順の本体: docs/08_quest_isaacteleop.md
set -euo pipefail

ISAAC_TELEOP_ROOT="${ISAAC_TELEOP_ROOT:-$HOME/robot/IsaacTeleop}"
VENV="${ISAAC_TELEOP_VENV:-$HOME/robot/isaac-teleop-env/.venv}"
EXAMPLE="${1:-gripper_retargeting_example_simple.py}"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "ERROR: venv not found: ${VENV}" >&2
  echo "  Create with: uv venv --python 3.12 ${VENV%/.venv}/.venv && \\" >&2
  echo "    source ${VENV}/bin/activate && uv pip install 'isaaccapture[cloudxr,retargeters]~=1.7.0' \\" >&2
  echo "      --extra-index-url https://pypi.nvidia.com --prerelease=allow" >&2
  exit 1
fi

EXAMPLE_PATH="${ISAAC_TELEOP_ROOT}/examples/teleop/python/${EXAMPLE}"
if [[ ! -f "${EXAMPLE_PATH}" ]]; then
  echo "ERROR: example not found: ${EXAMPLE_PATH}" >&2
  echo "  Clone: git clone https://github.com/NVIDIA/IsaacTeleop.git ${ISAAC_TELEOP_ROOT}" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Main PC LAN IP (Quest Server IP): ${HOST_IP:-unknown}"
echo "Quest client: https://nvidia.github.io/IsaacCapture/client"
echo "Cert accept:  https://${HOST_IP:-<IP>}:48322/"
echo "Open ports if needed:"
echo "  sudo ufw allow 47998/udp"
echo "  sudo ufw allow 49100,48322/tcp"
echo "Running: ${EXAMPLE_PATH}"
echo "----"

cd "${ISAAC_TELEOP_ROOT}"
exec python "examples/teleop/python/${EXAMPLE}"
