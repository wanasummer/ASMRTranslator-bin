#!/usr/bin/env sh
set -eu

PLUGIN_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEVICE=${1:-cuda}
RUNTIME_DIR=${CHICKENRICE_RUNTIME_DIR:-"$PLUGIN_ROOT/runtime"}

python3 -c 'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 12)'
python3 -m venv "$PLUGIN_ROOT/.venv"
PYTHONPATH="$PLUGIN_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PLUGIN_ROOT/.venv/bin/python" -m chickenrice_service.bootstrap \
  --runtime-dir "$RUNTIME_DIR" --device "$DEVICE"
printf '\n安装完成。运行 ./start.sh %s\n' "$DEVICE"
