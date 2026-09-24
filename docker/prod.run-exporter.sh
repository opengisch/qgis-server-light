#!/usr/bin/env bash

set -e

/app/.venv/bin/gunicorn qgis_server_light.exporter.api:app \
  --bind 127.0.0.1:8000 \
  --workers 2 \
  --access-logfile - \
  --error-logfile - \
  --timeout 30
