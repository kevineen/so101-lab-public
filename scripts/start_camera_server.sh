#!/usr/bin/env bash
# Pi: cameras + MJPEG only (no USB serial). Safe alongside bridge receiver.
# Streams: http://<Pi>:8765/api/stream/<name>  (see configs/so101_dual_cam.yaml)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/start_web_remote.sh" --cameras-only "$@"
