#!/bin/bash
set -euo pipefail

echo "[start.sh] Using PORT=${PORT:-5000}"

if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('rx') else 1)"; then
	echo "[start.sh] Installing Python dependencies"
	python -m pip install --upgrade pip
	python -m pip install --no-cache-dir -r requirements.txt
fi

exec gunicorn -c gunicorn_config.py app:app
