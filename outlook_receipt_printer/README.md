# Stampa Ricevute PEC

Programma desktop **offline** per **Windows** che stampa in PDF le ricevute di
consegna PEC presenti nelle sottocartelle della *Posta in arrivo* di Outlook e
le salva, ordinate, nelle sottocartelle corrispondenti di una cartella scelta.

## Cosa fa (in breve)

1. All'avvio apre la **Posta in arrivo di Outlook** e la **cartella scelta**.
2. Chiedi una **data** e una **cartella di destinazione**.
3. Per ogni **sottocartella di Outlook** cerca, nella cartella scelta, la
   sottocartella la cui **dicitura contiene il nome** della cartella Outlook
   (es. cartella Outlook `Rossi Mario` → cartella scelta `2024-001 Rossi Mario c. INPS`).
4. Stampa in **PDF** tutte le **ricevute di consegna PEC** (oggetto che inizia
   con `CONSEGNA:`) **ricevute nella data indicata**, escludendo quelle
   collegate agli indirizzi INPS configurati.
5. Salva ogni PDF con il nome **`bozza ad avv.`** nella sottocartella
   corrispondente. Se ce n'è più di una: `bozza ad avv..pdf`,
   `bozza ad avv. (2).pdf`, `bozza ad avv. (3).pdf`, …

## Scarica e clicca (senza installare nulla)

L'eseguibile viene costruito automaticamente dai server di GitHub. Per ottenerlo:

1. Vai alla pagina **Releases** del repository:
   <https://github.com/vdicagno-ui/GLM-OCR/releases>
2. Apri la release **"Stampa Ricevute PEC (ultima versione)"**.
3. Scarica il file **`StampaRicevutePEC.exe`**.
4. **Doppio clic** sul file. Fatto.

> La prima compilazione parte dopo il push e richiede pochi minuti. Se la
> release non c'è ancora, attendi che l'automazione (scheda **Actions** del
> repository) termini.
>
> L'eseguibile funziona su Windows con **Outlook classico** e **Word**
> installati; non richiede Python.

## Requisiti

- **Windows** con **Microsoft Outlook** (classico, non "nuovo Outlook") già
  configurato con l'account PEC.
- **Microsoft Word** (usato per la conversione in PDF) **oppure** **PDF24**
  (vedi `config.py`).
- **Python 3.8+** per Windows — <https://www.python.org/downloads/windows/>
  (durante l'installazione spunta *"Add Python to PATH"*).

Tutto funziona **in locale, senza connessione a Internet**.

## Avvio rapido

1. Copia questa cartella sul PC dove sono installati Outlook e Word.
2. Doppio clic su **`run.bat`**.
   - La prima volta installa automaticamente la dipendenza `pywin32`.
   - Se il PC è offline, installa prima `pywin32` una volta sola con:
     `python -m pip install pywin32`
3. Nella finestra:
   - inserisci la **data** (formato `GG/MM/AAAA`, predefinita: oggi);
   - premi **Scegli...** e seleziona la **cartella di destinazione**;
   - premi **Avvia stampa ricevute**.
4. Segui l'avanzamento nel **Registro operazioni**.

## Creare un eseguibile autonomo (facoltativo)

Per distribuire il programma senza dover installare Python su ogni PC:

```
build_exe.bat
```

Crea `dist\StampaRicevutePEC.exe`. Tieni il file **`config.py` accanto
all'eseguibile**: il programma lo legge da lì, così puoi modificarlo senza
ricompilare.

## Configurazione (`config.py`)

| Voce | Significato |
|------|-------------|
| `EXCLUDED_ADDRESSES` | Indirizzi da escludere (già impostati sui due INPS). |
| `EXCLUSION_SCOPE` | `"any"` = cerca l'indirizzo ovunque (mittente, destinatari, oggetto, corpo); `"sender"` = solo mittente. |
| `RECEIPT_SUBJECT_PREFIXES` | Prefissi oggetto che identificano una ricevuta (`CONSEGNA:`). |
| `BASE_FILENAME` | Nome base dei PDF (`bozza ad avv.`). |
| `PDF_ENGINE` | `"word"` (consigliato) oppure `"pdf24"`. |
| `PDF24_DOCTOOL` | Percorso dello strumento a riga di comando di PDF24. |
| `OPEN_OUTLOOK_INBOX` / `OPEN_CHOSEN_FOLDER` | Aprire o meno le cartelle all'avvio. |

## Note e limitazioni

- Il programma agisce sulle **sottocartelle dirette** della Posta in arrivo.
- La corrispondenza tra cartelle non fa distinzione tra maiuscole/minuscole e
  ignora gli spazi doppi. Se il nome della cartella Outlook compare in **più**
  sottocartelle scelte, viene usata la prima e segnalato nel registro.
- Funziona con l'**Outlook classico** da desktop. Il "nuovo Outlook" e
  Outlook sul web non espongono l'automazione COM richiesta.
- Se usi Word e vedi PDF vuoti, verifica che Word non abbia finestre di dialogo
  aperte; il programma lo avvia in modalità silenziosa.
