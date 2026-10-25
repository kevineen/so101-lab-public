#!/usr/bin/env bash
# LeRobot Dataset Curator 起動スクリプト
#
# 使い方:
#   ./run.sh <repo-id> <dataset-root> [port]
# 例:
#   ./run.sh local/so101_singlearm_pickup_cobra_20261018_205119 \
#       $HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119
set -euo pipefail

REPO_ID="${1:?使い方: ./run.sh <repo-id> <dataset-root> [port]}"
ROOT="${2:?データセットのルートディレクトリを指定してください}"
PORT="${3:-8787}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# lerobot フォークの venv を使用（正規配置は ~/robot/lerobot。LEROBOT_DIR で上書き可）
LEROBOT_DIR="${LEROBOT_DIR:-$HOME/robot/lerobot}"
PY="${LEROBOT_DIR}/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: lerobot の venv がありません: $PY" >&2
  echo "docs/00_repos.md の手順で ~/robot/lerobot を用意してください。" >&2
  exit 1
fi

exec "$PY" "$SCRIPT_DIR/curate_server.py" \
  --repo-id "$REPO_ID" \
  --root "$ROOT" \
  --host 127.0.0.1 \
  --port "$PORT"
