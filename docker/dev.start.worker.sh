#!/bin/sh

set -e
exec uv run hupper -m qgis_server_light.worker.redis \
  --redis-url "$QSL_REDIS_URL" \
  --svg-path "$QSL_SVG_PATH" \
  --data-root "$QSL_DATA_ROOT" \
  --log-level "$QSL_LOG_LEVEL"
