#!/usr/bin/env bash
# Preflight for docs/11_quest_teleop_runbook.md — does not move arms.
# Usage: ./scripts/check_quest_teleop.sh <Pi_LAN_IP>
#   （Pi の IP は configs/lab.local.env の SO101_PI_LAN_IP。source すれば引数不要）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT/configs/lab.local.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/configs/lab.local.env"
  set +a
fi
PI_HOST="${1:-${SO101_PI_LAN_IP:-}}"
if [[ -z "$PI_HOST" ]]; then
  echo "ERROR: Pi IP not given." >&2
  echo "  Usage: $0 <Pi_LAN_IP>" >&2
  echo "  or set SO101_PI_LAN_IP in configs/lab.local.env" >&2
  exit 1
fi
MAIN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "${MAIN_IP}" ]]; then
  MAIN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
fi
VENV="${ISAAC_TELEOP_VENV:-$HOME/robot/isaac-teleop-env/.venv}"
CFG="${ROOT}/configs/quest_teleop.yaml"

ok=0
warn=0
fail=0

pass() { echo "[OK]  $*"; ok=$((ok + 1)); }
note() { echo "[..]  $*"; warn=$((warn + 1)); }
bad()  { echo "[NG]  $*"; fail=$((fail + 1)); }

echo "=== Quest teleop preflight ==="
echo "Main PC: ${MAIN_IP:-unknown}"
echo "Pi hint: ${PI_HOST}"
echo

# Config / scripts
[[ -f "$CFG" ]] && pass "config $CFG" || bad "missing $CFG"
[[ -x "$ROOT/scripts/start_quest_bridge_live.sh" ]] && pass "start_quest_bridge_live.sh" || bad "live script"
[[ -x "$ROOT/scripts/start_camera_server.sh" ]] && pass "start_camera_server.sh" || bad "camera script"
[[ -x "$ROOT/scripts/start_bridge_receiver.sh" ]] && pass "start_bridge_receiver.sh" || bad "receiver script"

# Teleop venv
if [[ -x "${VENV}/bin/python" ]]; then
  pass "teleop venv ${VENV}"
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  python -c "import isaaccapture" 2>/dev/null && pass "import isaaccapture" || bad "isaaccapture not importable"
else
  bad "teleop venv missing: ${VENV}"
fi

# Pi reachability
if ping -c 1 -W 1 "$PI_HOST" >/dev/null 2>&1; then
  pass "ping ${PI_HOST}"
else
  bad "ping ${PI_HOST} failed"
fi

probe_tcp() {
  local host="$1" port="$2" label="$3"
  if timeout 1 bash -c "echo >/dev/tcp/${host}/${port}" 2>/dev/null; then
    pass "${label} ${host}:${port} open"
  else
    note "${label} ${host}:${port} closed (start service when you need it)"
  fi
}

probe_tcp "$PI_HOST" 8870 "bridge"
probe_tcp "$PI_HOST" 8765 "cameras-only / web_remote"
probe_tcp "${MAIN_IP:-127.0.0.1}" 48322 "CloudXR WSS (local)"

# YAML clutch hint
if [[ -f "$CFG" ]]; then
  echo
  echo "--- quest_teleop.yaml (controls) ---"
  grep -E '^(arms:|  clutch:|  gripper:|  pos_scale:|  enabled:)' "$CFG" || true
fi

echo
echo "=== Summary: OK=${ok}  notes=${warn}  NG=${fail} ==="
echo
echo "Next steps (docs/11_quest_teleop_runbook.md):"
echo "  Step 0  ./scripts/start_quest_gripper_example.sh"
echo "  Step 1  Pi: start_bridge_receiver.sh --dry-run -v   (IK=approx OK)"
echo "  Step 4  Pi: BRIDGE_IK=relative start_bridge_receiver.sh -v  (placo+URDF)"
echo "          PC: start_bridge_sender_demo.sh ${PI_HOST} --duration 10 -v"
echo "  Step 2  Pi: start_bridge_receiver.sh -v   (real arms)"
echo "          PC: start_bridge_sender_demo.sh ${PI_HOST} --duration 20 -v"
echo "  Step 3  Pi: start_camera_server.sh"
echo "  Step 4  PC: start_quest_bridge_live.sh ${PI_HOST}"
echo

[[ "$fail" -eq 0 ]]
