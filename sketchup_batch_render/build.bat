@echo off
REM ==========================================================================
REM  Crea l'eseguibile Windows SketchUpBatchRender.exe
REM  Requisiti: Python 3.8+ installato (con "Add to PATH" durante il setup).
REM  Esegui questo file facendo doppio clic, oppure da prompt dei comandi.
REM ==========================================================================

setlocal
cd /d "%~dp0"

echo === Installazione dipendenze ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo.
echo === Creazione eseguibile ===
REM --onefile     : un solo .exe
REM --windowed    : niente finestra console (app grafica)
REM --add-data    : allega lo script Ruby (dentro l'exe finisce nella root)
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name SketchUpBatchRender ^
  --add-data "sketchup_runner.rb;." ^
  gui.py
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Fatto! L'eseguibile e' in:  dist\SketchUpBatchRender.exe
echo ============================================================
pause
exit /b 0

:error
echo.
echo *** ERRORE durante la creazione. Controlla i messaggi sopra. ***
pause
exit /b 1
