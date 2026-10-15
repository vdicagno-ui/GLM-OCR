#!/usr/bin/env bash
# Compila CambiaIcona.exe per Windows a 64 bit usando mingw-w64.
set -e
cd "$(dirname "$0")"

CC=x86_64-w64-mingw32-gcc
WINDRES=x86_64-w64-mingw32-windres

echo "Compilazione risorse..."
"$WINDRES" resource.rc -O coff -o resource.o

echo "Compilazione eseguibile..."
"$CC" -O2 -municode -mwindows -o CambiaIcona.exe \
    icon_changer.c resource.o \
    -lcomctl32 -lcomdlg32 -lshlwapi -luser32 -lgdi32 \
    -Wl,--subsystem,windows -s

echo "Fatto: $(pwd)/CambiaIcona.exe"
