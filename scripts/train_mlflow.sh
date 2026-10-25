#!/usr/bin/env bash
# lerobot-train with metrics sent to local MLflow (docs/16_local_mlflow.md).
# Working directory is the lerobot fork checkout, same as a direct lerobot-train launch.
# Do not pass a real W&B login. --wandb.enable is forced on so LeRobot builds
# a logger; that class writes to MLflow.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# lerobot フォークの解決: LEROBOT_DIR 環境変数 → ~/robot/lerobot（正規配置）→ vendor/lerobot（旧構成）
if [ -z "${LEROBOT_DIR:-}" ]; then
  if [ -d "$HOME/robot/lerobot" ]; then LEROBOT_DIR="$HOME/robot/lerobot"; else LEROBOT_DIR="$ROOT/vendor/lerobot"; fi
fi
VENV_PY="${LEROBOT_DIR}/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: lerobot venv がありません: $VENV_PY" >&2
  echo "docs/00_repos.md の手順で lerobot フォーク（~/robot/lerobot）を用意してください。" >&2
  exit 1
fi

if ! "$VENV_PY" -c "import mlflow, sqlalchemy, alembic" >/dev/null 2>&1; then
  echo "MLflow クライアントを lerobot の venv に入れます"
  # skinny: tracking client only. sqlalchemy/alembic: sqlite when the UI server is down.
  uv pip install --python "$VENV_PY" 'mlflow-skinny>=2.19,<4' 'sqlalchemy>=2' 'alembic>=1.14'
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH="${LEROBOT_DIR}/src:${PYTHONPATH}"
# If the class swap ever fails, keep the wandb client from uploading.
export WANDB_MODE="${WANDB_MODE:-disabled}"
export MLFLOW_DISABLE_AGENT_HINT=1

cd "$LEROBOT_DIR"
exec "$VENV_PY" -m tracking.train_main "$@"
