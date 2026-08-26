# Estrattore Spese — GLM-OCR

Applicazione desktop **Windows** (Python) che:

1. Carica una serie di **foto** di appunti di spesa (cifre e causali scritte in corsivo).
2. Esegue l'**OCR** di ogni foto tramite **GLM-OCR** (modello di visione servito da Ollama) ed estrae le coppie **causale + importo**.
3. **Somma gli importi raggruppandoli per causale**, ignorando i **totali** (righe con causale `totale`/`totali`/`somma` oppure righe con solo una cifra senza causale).
4. Scrive/accoda i dati in un **foglio Excel** ordinato su 3 colonne:

   | Data inserimento | Causale | Valore |
   |------------------|---------|--------|
   | 26/08/2026       | Benzina | −50,00 € |

   Il **Valore è sempre negativo** (spesa).

---

## Perché Windows e non Android

Un `.exe` "unico file" con interfaccia grafica su Windows si genera in modo affidabile con PyInstaller. Un APK Android che faccia OCR + Excel richiederebbe invece toolchain e test su dispositivo non disponibili in questo ambiente. Come indicato nella richiesta, si ripiega quindi su **Windows** riusando il motore **GLM-OCR** già presente nel progetto. La logica di estrazione/aggregazione è comunque separata dalla GUI (`estrattore_spese/`), quindi riutilizzabile in futuro anche per un'app mobile.

---

## Requisiti

- **Windows 10/11**, **Python 3.10+**
- Il motore OCR **GLM-OCR** raggiungibile via **Ollama** (di default `http://localhost:11434`, modello `glm-ocr`).
  Endpoint e nome modello sono modificabili direttamente nella finestra dell'app.

## Avvio in sviluppo

```bat
pip install -r requirements.txt
python app.py
```

## Generazione dell'eseguibile (.exe)

Su Windows, dalla cartella `desktop/`:

```bat
build.bat
```

L'eseguibile viene creato in `dist\EstrattoreSpese.exe` (doppio clic per avviarlo, nessuna installazione di Python richiesta sul PC finale).

---

## Come si usa

1. **Motore OCR**: verifica in alto che lo stato sia `● Pronto` (endpoint e modello corretti).
2. **1. Foto**: *Aggiungi foto…* o *Aggiungi cartella…*.
3. **2. File Excel**: scegli dove salvare (se il file esiste, le righe vengono **accodate**).
4. **▶ Elabora foto**: parte l'OCR; l'anteprima mostra le causali con il totale sommato.
5. **💾 Salva su Excel**: scrive le righe nel foglio.

---

## Struttura del progetto

```
desktop/
├── app.py                     # interfaccia grafica (tkinter) + avvio
├── build.bat                  # genera l'eseguibile Windows con PyInstaller
├── requirements.txt
├── test_core.py               # test della logica (senza OCR/GUI)
└── estrattore_spese/
    ├── config.py              # configurazione (endpoint, modello, ecc.)
    ├── ocr_backend.py         # OCR via GLM-OCR/Ollama + prompt di estrazione
    ├── importi.py             # parsing importi in formato italiano
    ├── parsing.py             # da output OCR a voci; filtra i totali
    ├── aggregate.py           # somma per causale
    ├── excel_writer.py        # scrittura/append sul foglio Excel
    └── pipeline.py            # orchestrazione (con callback di avanzamento)
```

## Test

```bat
python test_core.py
```

Copre: parsing importi (formato IT/EN), riconoscimento ed esclusione dei totali, aggregazione per causale e scrittura Excel con valori negativi e append.
