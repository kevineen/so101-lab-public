#!/usr/bin/env bash
# SO-101 MuJoCo シーンのインタラクティブ viewer（要 ディスプレイ）。
# SSH 経由では動かない。Pi のデスクトップ / VNC 上か、X 転送 (`ssh -X`) で起動すること。
#
#   ./scripts/start_sim_viewer.sh                      # 生成したシーンを表示
#   SIM_SCENE=... ./scripts/start_sim_viewer.sh        # 別 XML を指定
#
# viewer 操作: Ctrl+ドラッグ=回転 / 右ドラッグ=移動 / スペース=物理再生 /
#   obstacle はダブルクリック後ドラッグで移動（干渉の見える化）。
# ヘッドレスで画像が欲しい場合は sim_check.py --render（MUJOCO_GL=egl）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"
SCENE="${SIM_SCENE:-$ROOT/assets/robots/so101/sim/so101_scene.xml}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv not found at $VENV_PY" >&2
  exit 1
fi
if [[ ! -f "$SCENE" ]]; then
  echo "ERROR: scene not found: $SCENE" >&2
  exit 1
fi
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "ERROR: ディスプレイが無い (DISPLAY 未設定)。Pi のデスクトップ/VNC 上、もしくは ssh -X で実行。" >&2
  echo "       ヘッドレスで干渉チェックのみなら: scripts/sim_check.py" >&2
  exit 1
fi

exec "$VENV_PY" -m mujoco.viewer --mjcf "$SCENE" "$@"
