#!/usr/bin/env bash

set -e

/app/.venv/bin/redis-worker \
  --redis-url "$QSL_REDIS_URL" \
  --svg-path /io/svg:/io/data \
  --data-root /io/data \
  --log-level "$QSL_LOG_LEVEL" \
  ${QSL_RUNNER_PLUGINS:+--runner-plugins "$QSL_RUNNER_PLUGINS"} \
  ${QSL_PROCESS_ALLOWLIST:+--process-allowlist "$QSL_PROCESS_ALLOWLIST"}
