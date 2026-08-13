#!/bin/bash
# build_executable.sh — Crea un eseguibile standalone della GUI (Linux/macOS).
#
# Il file prodotto NON richiede Python installato sulla macchina finale.
# Richiede però che Ollama sia in esecuzione con un modello vision (es. gemma3:4b).
#
# Uso:
#   ./build_executable.sh
#
# Risultato:
#   dist/TrascrittoreManoscritti     (eseguibile a singolo file)

set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installazione dipendenze di build..."
pip install --upgrade pip -q
pip install pyinstaller httpx Pillow -q

echo "==> Creazione dell'eseguibile con PyInstaller..."
pyinstaller \
  --onefile \
  --windowed \
  --name "TrascrittoreManoscritti" \
  --collect-all PIL \
  handwriting_gui.py

echo ""
echo "==> Fatto. Eseguibile creato in: dist/TrascrittoreManoscritti"
echo "    Avvialo con:  ./dist/TrascrittoreManoscritti"
