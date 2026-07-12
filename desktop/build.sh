#!/bin/bash
# Build a standalone GLM-OCR desktop executable with PyInstaller.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Installing desktop dependencies..."
pip install -r desktop/requirements.txt -q

echo "==> Building executable with PyInstaller..."
pyinstaller --noconfirm --clean desktop/glm_ocr.spec

echo "==> Done. Output in dist/GLM-OCR"
