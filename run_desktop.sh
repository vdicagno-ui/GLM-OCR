#!/bin/bash
# GLM-OCR — launch the desktop window (dev mode, no packaging required)
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Installing dependencies..."
pip install -r desktop/requirements.txt -q

echo "==> Launching GLM-OCR desktop app..."
python -m desktop.app
