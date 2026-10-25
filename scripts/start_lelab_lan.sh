#!/usr/bin/env bash
# Start LeLab bound to all interfaces so another PC on the LAN can open the UI.
# Default lelab CLI binds 127.0.0.1 only — this wrapper uses uvicorn with 0.0.0.0.
set -euo pipefail

HOST="${LELAB_HOST:-0.0.0.0}"
PORT="${LELAB_PORT:-8000}"

resolve_uvicorn() {
  # Always prefer the isolated uv-tool LeLab environment (pins its own lerobot).
  local tool_dir tool_uvicorn
  tool_dir="$(uv tool dir 2>/dev/null || true)"
  tool_uvicorn="${tool_dir}/lelab/bin/uvicorn"
  if [[ -x "$tool_uvicorn" ]]; then
    echo "$tool_uvicorn"
    return
  fi

  # Fallback: lelab next to uvicorn on PATH (same tool env after `uv tool update-shell`).
  if command -v lelab >/dev/null 2>&1; then
    local lelab_bin lelab_root
    lelab_bin="$(command -v lelab)"
    lelab_root="$(cd "$(dirname "$lelab_bin")/.." && pwd)"
    if [[ -x "$lelab_root/bin/uvicorn" ]]; then
      echo "$lelab_root/bin/uvicorn"
      return
    fi
  fi

  echo "ERROR: LeLab uvicorn not found. Install with:" >&2
  echo "  uv tool install --python 3.12 git+https://github.com/huggingface/leLab.git" >&2
  exit 1
}

UVICORN_BIN="$(resolve_uvicorn)"
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo "Starting LeLab on http://${HOST}:${PORT}/"
if [[ -n "${LAN_IP}" ]]; then
  echo "Open from another PC: http://${LAN_IP}:${PORT}/"
fi
echo "Do not run Web Remote at the same time (shared serial / cameras)."
echo "Press Ctrl+C to stop."

exec "$UVICORN_BIN" lelab.server:app --host "$HOST" --port "$PORT" --log-level info
