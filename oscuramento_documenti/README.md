# Oscura Documenti

App desktop con interfaccia grafica per oscurare nome/cognome, data di nascita
e codice fiscale all'interno di file `.docx` (paragrafi, tabelle, intestazioni,
piè di pagina e caselle di testo).

## Avvio in modalità sviluppo

```bash
pip install -r requirements.txt
python anonimizza_gui.py
```

## Creazione dell'eseguibile desktop

Su Linux/macOS:

```bash
./build.sh
```

Su Windows:

```bat
build.bat
```

In entrambi i casi l'eseguibile viene generato dentro la cartella `dist/`
(`OscuraDocumenti` su Linux/macOS, `OscuraDocumenti.exe` su Windows) e può
essere lanciato senza bisogno di Python installato.

## Utilizzo

1. Avvia l'applicazione.
2. Seleziona la cartella contenente i file `.docx` da elaborare.
3. Inserisci nome e cognome del soggetto da oscurare (riconosce anche
   l'ordine invertito e le iniziali puntate).
4. Inserisci la data di nascita in un formato qualsiasi (es. `12/07/1990`,
   `12 luglio 1990`, `1990-07-12`).
5. Premi "Avvia oscuramento": il log mostra in tempo reale i file
   modificati o saltati.

I file vengono sovrascritti in loco con i dati sensibili sostituiti dai tag
`[soggetto_interessato]`, `[data_nascita_oscurata]` e
`[codice_fiscale_oscurato]`.
