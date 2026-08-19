@echo off
REM ============================================================
REM  Crea l'eseguibile Windows (.exe) del Compilatore Template
REM  Word. Eseguire questo file su Windows con Python installato.
REM ============================================================

echo.
echo [1/3] Installazione dipendenze...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
if errorlevel 1 goto :error

echo.
echo [2/3] Creazione eseguibile con PyInstaller...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "CompilatoreTemplateWord" ^
  --collect-all docx ^
  --collect-all pypdf ^
  app.py
if errorlevel 1 goto :error

echo.
echo [3/3] Fatto!
echo L'eseguibile si trova in:  dist\CompilatoreTemplateWord.exe
echo.
goto :eof

:error
echo.
echo *** Errore durante la creazione dell'eseguibile. ***
exit /b 1
