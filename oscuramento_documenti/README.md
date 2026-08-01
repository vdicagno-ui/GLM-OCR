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
   elaborati.

Le date vengono riconosciute in **qualsiasi formato** (es. `12/07/1990`,
`12-07-1990`, `12.07.1990`, `12 07 1990`, `12/7/90`, `12 luglio 1990`,
`12 lug 1990`, ISO `1990-07-12`), indipendentemente dal formato con cui
sono state digitate nell'app.

Il codice fiscale viene sempre oscurato con il tag
`[codice_fiscale_oscurato]`.

## File di output

I file originali **non vengono modificati**. I documenti anonimizzati
vengono salvati in una sottocartella `Documenti_Anonimizzati` creata
dentro la cartella selezionata. Questo evita anche l'errore di "permesso
negato" (Errore 13) che si verifica quando si prova a sovrascrivere un
file aperto in Word o in sola lettura: chiudere comunque i file in Word
prima di elaborarli è consigliato.
