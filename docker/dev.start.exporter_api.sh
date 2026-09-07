#!/bin/bash

uv sync --frozen --group dev
exec uv run exporter-api start --data-root "$QSL_DATA_ROOT" --host 0.0.0.0 --port 5000 --log-level $QSL_LOG_LEVEL
