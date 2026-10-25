#!/usr/bin/env bash
# 両リポの学習ドキュメントを同時 serve（sim2rl :8100 / so101-lab :8101）。
#
# 同じ Wi-Fi:      http://<このマシンのLAN-IP>:8100 / :8101
# 外出先（推奨）:  スマホで Tailscale アプリを ON にして
#                  http://<このマシンのMagicDNS名>:8100 / :8101
#                  （例: http://so101pi:8100 。tailscale ip -4 で確認）
#
# ポートを変える:  SIM2RL_PORT=8200 SO101_PORT=8201 ./scripts/serve_docs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM2RL="${SIM2RL_ROOT:-$ROOT/../sim2rl}"
SIM2RL_PORT="${SIM2RL_PORT:-8100}"
SO101_PORT="${SO101_PORT:-8101}"

if [[ ! -d "$SIM2RL" ]]; then
  echo "ERROR: sim2rl が見つかりません: $SIM2RL（SIM2RL_ROOT で指定可）" >&2
  exit 1
fi
command -v uv >/dev/null || { echo "ERROR: uv がありません（~/.local/bin/uv 等）" >&2; exit 1; }

# Tailscale に入っていたら案内を表示（無くても動く）
TS_HINT=""
if command -v tailscale >/dev/null 2>&1; then
  TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  [[ -n "$TS_IP" ]] && TS_HINT="  Tailscale IP: $TS_IP"
fi

echo "sim2rl   -> http://0.0.0.0:${SIM2RL_PORT}  (${SIM2RL})"
echo "so101-lab-> http://0.0.0.0:${SO101_PORT}  (${ROOT})"
echo "スマホ: Tailscale ON で http://<このマシンの名前>:${SIM2RL_PORT} / :${SO101_PORT}${TS_HINT}"
echo "止めるとき: Ctrl+C"

cleanup() {
  [[ -n "${SIM_PID:-}" ]] && kill "$SIM_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$SIM2RL"
  uv run --group docs mkdocs serve --dev-addr "0.0.0.0:${SIM2RL_PORT}"
) &
SIM_PID=$!

cd "$ROOT"
uv run --group docs mkdocs serve --dev-addr "0.0.0.0:${SO101_PORT}"
