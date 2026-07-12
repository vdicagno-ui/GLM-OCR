@echo off
REM Crea l'eseguibile desktop (Windows) con PyInstaller.
cd /d "%~dp0"

python -m pip install -r requirements.txt

pyinstaller --onefile --windowed --name OscuraDocumenti anonimizza_gui.py

echo Eseguibile creato in: dist\OscuraDocumenti.exe
