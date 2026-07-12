@echo off
REM Crea l'eseguibile desktop (Windows) con PyInstaller.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    set PYCMD=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PYCMD=py
    ) else (
        echo ERRORE: Python non trovato nel PATH.
        echo Installa Python da https://www.python.org/downloads/
        echo IMPORTANTE: durante l'installazione spunta "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

echo Uso comando Python: %PYCMD%
%PYCMD% --version

%PYCMD% -c "import tkinter" >nul 2>nul
if not %errorlevel%==0 (
    echo ERRORE: il modulo tkinter non e' disponibile in questa installazione di Python.
    echo Reinstalla Python da https://www.python.org/downloads/ lasciando attiva
    echo l'opzione "tcl/tk and IDLE" nel programma di installazione.
    pause
    exit /b 1
)

echo.
echo Installazione dipendenze...
%PYCMD% -m pip install --upgrade pip
%PYCMD% -m pip install -r requirements.txt
if not %errorlevel%==0 (
    echo ERRORE durante l'installazione delle dipendenze. Vedi il messaggio sopra.
    pause
    exit /b 1
)

echo.
echo Creazione dell'eseguibile...
%PYCMD% -m PyInstaller --onefile --windowed --name OscuraDocumenti anonimizza_gui.py
if not %errorlevel%==0 (
    echo ERRORE durante la creazione dell'eseguibile. Vedi il messaggio sopra.
    pause
    exit /b 1
)

echo.
echo Eseguibile creato in: dist\OscuraDocumenti.exe
pause
