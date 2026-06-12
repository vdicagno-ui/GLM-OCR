#!/bin/bash
# GLM-OCR — start script
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Installing Python dependencies..."
pip install -r backend/requirements.txt -q

echo "==> Starting GLM-OCR server on http://0.0.0.0:8000"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
