#!/usr/bin/env sh
set -eu

if [ ! -f "${CHICKENRICE_RUNTIME_DIR}/INSTALLATION.json" ]; then
  python3.10 -m chickenrice_service.bootstrap \
    --runtime-dir "${CHICKENRICE_RUNTIME_DIR}" \
    --device "${CHICKENRICE_DEVICE}" \
    --skip-dependencies
fi

exec python3.10 -m chickenrice_service \
  --runtime-dir "${CHICKENRICE_RUNTIME_DIR}" \
  --device "${CHICKENRICE_DEVICE}" \
  --compute-type "${CHICKENRICE_COMPUTE_TYPE}" \
  --host "${CHICKENRICE_HOST}" \
  --port "${CHICKENRICE_PORT}"
