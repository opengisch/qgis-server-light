#!/bin/sh

set -e
exec uv run hupper -m qgis_server_light.worker.redis \
  --redis-url "$QSL_REDIS_URL" \
  --svg-path "$QSL_SVG_PATH" \
  --data-root "$QSL_DATA_ROOT" \
  --log-level "$QSL_LOG_LEVEL" \
  ${QSL_ENGINE:+--engine "$QSL_ENGINE"} \
  ${QSL_RUNNER_PLUGINS:+--runner-plugins "$QSL_RUNNER_PLUGINS"} \
  ${QSL_PROCESS_ALLOWLIST:+--process-allowlist "$QSL_PROCESS_ALLOWLIST"} \
  ${QSL_PROCESS_OUTPUT_DIR:+--process-output-dir "$QSL_PROCESS_OUTPUT_DIR"}
