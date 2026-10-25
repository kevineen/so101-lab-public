#!/usr/bin/env bash
# Local MLflow tracking server (sqlite + file artifacts under mlflow_store/).
# Default: Docker Compose. Fallback: SO101_MLFLOW_BACKEND=uv
# UI: http://127.0.0.1:5000  (LAN: http://<this-host>:5000)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND="${SO101_MLFLOW_BACKEND:-docker}"
export MLFLOW_DISABLE_AGENT_HINT=1

load_settings_uv() {
  uv sync --all-groups
  # shellcheck disable=SC2046
  eval "$(uv run --all-groups -m tracking.settings --shell)"
}

# Flat yaml + env (no Python required for the Docker path).
load_settings_shell() {
  local cfg="$ROOT/configs/mlflow.yaml"
  local host_v=0.0.0.0 port_v=5000 store_v=mlflow_store exp_v=so101
  if [[ -f "$cfg" ]]; then
    while IFS=: read -r key value; do
      key="$(echo "$key" | tr -d '[:space:]')"
      value="$(echo "$value" | sed 's/#.*//; s/^[[:space:]]*//; s/[[:space:]]*$//; s/^["'\'']//; s/["'\'']$//')"
      case "$key" in
        host) host_v="$value" ;;
        port) port_v="$value" ;;
        store_dir) store_v="$value" ;;
        experiment) exp_v="$value" ;;
      esac
    done < <(grep -E '^(host|port|store_dir|experiment):' "$cfg" || true)
  fi
  HOST="${SO101_MLFLOW_HOST:-$host_v}"
  PORT="${SO101_MLFLOW_PORT:-$port_v}"
  STORE_DIR="${SO101_MLFLOW_STORE:-$store_v}"
  EXPERIMENT="${SO101_MLFLOW_EXPERIMENT:-$exp_v}"
  if [[ "$STORE_DIR" != /* ]]; then
    STORE_DIR="$ROOT/$STORE_DIR"
  fi
  ARTIFACT_DIR="$STORE_DIR/artifacts"
  DB_URI="sqlite:///${STORE_DIR}/mlflow.db"
}

print_banner() {
  local lan_ip
  lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "MLflow backend: $BACKEND"
  echo "MLflow store: $STORE_DIR"
  echo "  sqlite と artifacts はこのディレクトリに入ります（gitignore 済み）"
  echo "UI: http://127.0.0.1:${PORT}"
  if [[ -n "${lan_ip}" ]]; then
    echo "別 PC から: http://${lan_ip}:${PORT}"
  fi
  echo "experiment: $EXPERIMENT"
}

start_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker がありません。インストールするか SO101_MLFLOW_BACKEND=uv で起動してください。" >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: docker compose がありません。" >&2
    exit 1
  fi
  export SO101_MLFLOW_PORT="$PORT"
  export SO101_MLFLOW_STORE="$STORE_DIR"
  echo "起動: docker compose up -d mlflow  （止める: docker compose stop mlflow）"
  docker compose up -d --pull missing mlflow
  echo "疎通確認中..."
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      echo "ready: http://127.0.0.1:${PORT}"
      docker compose ps mlflow
      return 0
    fi
    sleep 1
  done
  echo "WARN: health がまだ応答しません。ログ: docker compose logs -f mlflow" >&2
  docker compose logs --tail 40 mlflow || true
  return 1
}

start_uv() {
  load_settings_uv
  mkdir -p "$STORE_DIR" "$ARTIFACT_DIR"
  print_banner
  exec uv run --all-groups mlflow server \
    --backend-store-uri "$DB_URI" \
    --default-artifact-root "$ARTIFACT_DIR" \
    --artifacts-destination "$ARTIFACT_DIR" \
    --host "$HOST" \
    --port "$PORT"
}

case "$BACKEND" in
  docker|compose)
    load_settings_shell
    mkdir -p "$STORE_DIR" "$ARTIFACT_DIR"
    print_banner
    start_docker
    ;;
  uv|local)
    start_uv
    ;;
  *)
    echo "ERROR: unknown SO101_MLFLOW_BACKEND=$BACKEND (docker|uv)" >&2
    exit 1
    ;;
esac
