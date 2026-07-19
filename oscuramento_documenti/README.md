# Oscura Documenti

App desktop con interfaccia grafica per oscurare più nominativi, più date di
nascita, numeri di telefono e codice fiscale all'interno di file `.docx`
(paragrafi, tabelle, intestazioni, piè di pagina e caselle di testo).

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
3. Per ogni persona da oscurare, aggiungi una riga con "+ Aggiungi
   nominativo": inserisci nome e cognome (riconosce anche l'ordine
   invertito e le iniziali puntate) e la dicitura di sostituzione da usare
   per quella persona (es. `[soggetto_1]`). Se la dicitura viene lasciata
   vuota si usa il valore predefinito `[soggetto_interessato]`.
4. Per ogni data di nascita da oscurare, aggiungi una riga con "+ Aggiungi
   data" e inseriscila in un formato qualsiasi (es. `12/07/1990`,
   `12 luglio 1990`, `1990-07-12`). Tutte le date vengono sostituite dalla
   stringa fissa `00.00.00`.
5. Lascia attiva (o disattiva) la casella "Oscura anche i numeri di
   telefono" per oscurare anche cellulari e fissi italiani rilevati nel
   testo, sostituendoli con `[numero_di_telefono_oscurato]`.
6. Premi "Avvia oscuramento": il log mostra in tempo reale i file
   modificati o saltati.

Il codice fiscale viene sempre oscurato con il tag
`[codice_fiscale_oscurato]`. I file vengono sovrascritti in loco.
