@echo off
REM Avvia l'applicazione senza creare l'eseguibile (richiede Python).
REM Installa le dipendenze la prima volta, poi lancia la GUI.

cd /d "%~dp0"
python -c "import docx, pypdf" 2>nul
if errorlevel 1 (
  echo Installazione dipendenze in corso...
  python -m pip install -r requirements.txt
)
python app.py
