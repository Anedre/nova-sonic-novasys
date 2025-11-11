#!/bin/bash
set -euo pipefail

echo "[start.sh] Using PORT=${PORT:-5000}"
exec gunicorn -c gunicorn_config.py app:app
