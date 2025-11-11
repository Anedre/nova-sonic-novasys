#!/bin/bash
set -e

echo "=== Installing FFmpeg ==="
apt-get update && apt-get install -y ffmpeg

echo "=== Installing Python packages ==="
pip install --upgrade pip
pip install --no-cache-dir reactivex==4.0.4
pip install --no-cache-dir -r requirements.txt

echo "=== Installation complete ==="
python --version
pip list | grep -E "(reactivex|flask|gunicorn)"
