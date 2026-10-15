# Cambia Icona

Utility **offline** con interfaccia grafica per Windows che sostituisce
l'icona di un file eseguibile (`.exe`) o di una libreria (`.dll`).

Non richiede connessione a Internet, non installa nulla e non modifica il
sistema: agisce solo sul file scelto. Usa esclusivamente le API ufficiali di
Windows per l'aggiornamento delle risorse (`BeginUpdateResource` /
`UpdateResource` / `EndUpdateResource`).

## Uso

1. Avvia `CambiaIcona.exe`.
2. **Sfoglia** e seleziona l'eseguibile da modificare.
3. **Sfoglia** e seleziona il file `.ico` con la nuova icona (ne vedi l'anteprima).
4. Premi **Applica nuova icona**.

### Eseguibili PyInstaller / installer

Funziona anche con eseguibili che contengono dati aggiunti in coda (overlay),
come i programmi Python impacchettati con **PyInstaller**, gli installer
**NSIS**/**Inno Setup** e gli autoestraenti: l'app salva l'overlay prima di
modificare l'icona e lo rimette a posto dopo, così il programma continua a
partire. (Le API di Windows da sole scarterebbero l'overlay, corrompendo il
file.) Resta comunque prudente lavorare su una **copia**.

Note:
- L'eseguibile da modificare non deve essere in esecuzione.
- Possono servire i permessi di scrittura sul file (se si trova in cartelle
  protette come `C:\Program Files`, avvia il programma come amministratore).
- L'icona mostrata da Esplora risorse può aggiornarsi con un po' di ritardo
  per via della cache delle icone di Windows.

## Compilazione

L'eseguibile precompilato è `CambiaIcona.exe`. Per ricompilarlo serve
`mingw-w64`:

```bash
./build.sh
```

## File

- `icon_changer.c` — sorgente dell'applicazione Win32.
- `app.manifest` / `resource.rc` — manifest per lo stile grafico moderno.
- `build.sh` — script di compilazione (mingw-w64).
- `CambiaIcona.exe` — eseguibile Windows a 64 bit pronto all'uso.
