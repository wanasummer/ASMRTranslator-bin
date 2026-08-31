#!/usr/bin/env sh
set -eu

PLUGIN_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEVICE=${1:-cuda}
RUNTIME_DIR=${CHICKENRICE_RUNTIME_DIR:-"$PLUGIN_ROOT/runtime"}
HOST=${CHICKENRICE_HOST:-127.0.0.1}
PORT=${CHICKENRICE_PORT:-7870}

"$PLUGIN_ROOT/.venv/bin/python" -m chickenrice_service \
  --runtime-dir "$RUNTIME_DIR" --device "$DEVICE" --check

exec "$PLUGIN_ROOT/.venv/bin/python" -m chickenrice_service \
  --runtime-dir "$RUNTIME_DIR" --device "$DEVICE" --host "$HOST" --port "$PORT"
