@echo off
REM build_executable.bat - Crea un eseguibile standalone della GUI (Windows).
REM
REM Il file prodotto (TrascrittoreManoscritti.exe) NON richiede Python installato
REM sulla macchina finale. Richiede pero' che Ollama sia in esecuzione con un
REM modello vision (es. gemma3:4b).
REM
REM Uso:  fai doppio clic su questo file, oppure eseguilo da terminale.
REM Risultato:  dist\TrascrittoreManoscritti.exe

setlocal
cd /d "%~dp0"

echo ==^> Installazione dipendenze di build...
python -m pip install --upgrade pip -q
python -m pip install pyinstaller httpx Pillow -q

echo ==^> Creazione dell'eseguibile con PyInstaller...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "TrascrittoreManoscritti" ^
  --collect-all PIL ^
  handwriting_gui.py

echo.
echo ==^> Fatto. Eseguibile creato in: dist\TrascrittoreManoscritti.exe
pause
