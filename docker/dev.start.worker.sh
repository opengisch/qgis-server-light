#!/bin/sh
# we start the python process under the passed DEBUGPY_LAUNCH
set -e
exec ${DEBUGPY_LAUNCH:-} "$(command -v hupper)" -m qgis_server_light.worker.redis \
  --redis-url "$QSL_REDIS_URL" \
  --svg-path "$QSL_SVG_PATH" \
  --data-root "$QSL_DATA_ROOT" \
  --log-level "$QSL_LOG_LEVEL"
