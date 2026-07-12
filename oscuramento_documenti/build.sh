#!/usr/bin/env bash
# Crea l'eseguibile desktop (Linux/macOS) con PyInstaller.
set -e
cd "$(dirname "$0")"

python3 -m pip install -r requirements.txt

pyinstaller --onefile --windowed --name OscuraDocumenti anonimizza_gui.py

echo "Eseguibile creato in: dist/OscuraDocumenti"
