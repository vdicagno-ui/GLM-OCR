@echo off
REM ============================================================
REM  Estrattore Spese - generazione eseguibile Windows (.exe)
REM  Eseguire questo script SU WINDOWS, con Python 3.10+ installato.
REM ============================================================

echo [1/3] Installazione dipendenze...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :errore

echo [2/3] Generazione eseguibile con PyInstaller...
python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name "EstrattoreSpese" ^
  --collect-all openpyxl ^
  app.py
if errorlevel 1 goto :errore

echo [3/3] Fatto!
echo Eseguibile creato in:  dist\EstrattoreSpese.exe
goto :fine

:errore
echo.
echo *** ERRORE durante la build. Controllare i messaggi sopra. ***
exit /b 1

:fine
