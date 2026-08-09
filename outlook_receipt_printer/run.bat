@echo off
REM ============================================================
REM  Stampa Ricevute PEC - avvio su Windows
REM ============================================================
setlocal
cd /d "%~dp0"

echo ==^> Verifica dipendenze Python...
python -m pip install -r requirements.txt --quiet

echo ==^> Avvio del programma...
python outlook_receipt_printer.py

endlocal
