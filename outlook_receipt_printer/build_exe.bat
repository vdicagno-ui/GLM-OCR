@echo off
REM ============================================================
REM  Crea un eseguibile .exe autonomo (offline) con PyInstaller
REM ============================================================
setlocal
cd /d "%~dp0"

echo ==^> Installazione dipendenze e PyInstaller...
python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet

echo ==^> Creazione dell'eseguibile...
pyinstaller --noconfirm --onefile --windowed ^
  --name "StampaRicevutePEC" ^
  --add-data "config.py;." ^
  outlook_receipt_printer.py

echo.
echo Eseguibile creato in: dist\StampaRicevutePEC.exe
endlocal
