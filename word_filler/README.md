# Compilatore Template Word — Offline

Applicazione desktop con interfaccia grafica per **Windows** che compila un
template Word riempiendo dei segnaposto («da compilare …») con i dati estratti
da uno o più **file guida**. Funziona **completamente offline**: se serve l'AI,
usa un modello **locale** tramite LM Studio o Ollama. Nessun dato lascia il
computer.

## Come funziona

1. **Template Word** (`.docx`) con segnaposto a **delimitatori forti**, dove
   dentro le parentesi quadre scrivi la descrizione del dato, per esempio:
   > Il sottoscritto **[da compilare nome e cognome]**, procedimento **[da compilare nr. RG]**, con incarico del **[da compilare data di incarico]**…

   Le parentesi quadre eliminano ogni ambiguità sui confini del campo; nel
   documento finale le parentesi vengono rimosse e il prefisso «da compilare»
   non fa parte del nome del campo (il campo è «nome e cognome»).
2. **Uno o più file guida** (`.docx`, `.pdf`, `.txt`, `.md`) da cui estrarre i valori.
3. L'app estrae i dati **da ogni singolo file guida** e genera **un documento di
   output per ciascuno**. Ogni output usa i dati **solo** del proprio file guida.
4. Prima di generare puoi **rivedere e correggere** i valori estratti.

```
template.docx  +  guida_A.pdf   ->  guida_A_compilato.docx   (dati solo da guida_A)
               +  guida_B.docx  ->  guida_B_compilato.docx   (dati solo da guida_B)
               +  guida_C.txt   ->  guida_C_compilato.docx   (dati solo da guida_C)
```

## Requisiti

- **Windows** con **Python 3.9+** installato (tkinter è già incluso).
- Dipendenze Python: `python-docx`, `pypdf` (installate automaticamente).
- **Opzionale (per l'AI):** [LM Studio](https://lmstudio.ai) oppure
  [Ollama](https://ollama.com) in esecuzione in locale con un modello caricato.

## Avvio rapido (senza creare l'eseguibile)

Doppio clic su **`run_app.bat`** — installa le dipendenze la prima volta e apre
la GUI. In alternativa, da terminale:

```bat
pip install -r requirements.txt
python app.py
```

## Creare l'eseguibile `.exe`

Doppio clic su **`build_exe.bat`** (su Windows). Al termine trovi:

```
dist\CompilatoreTemplateWord.exe
```

È un file singolo e autonomo: puoi copiarlo e avviarlo senza installare nulla.

## Uso passo-passo

**Scheda «1 · Configurazione»**

1. Seleziona il **template Word**.
2. Scegli il **formato delle etichette** dei segnaposto:
   - *Parentesi quadra* (predefinito, consigliato) → `[da compilare nome e cognome]`
   - *Doppia graffa* → `{{nome e cognome}}`
   - *Guillemet* → `«nome e cognome»`
   - *Etichetta «da compilare …» (senza parentesi)* → `da compilare nome cognome`
     (meno robusto: usalo solo se il template non ha delimitatori)
   - oppure una **espressione regolare personalizzata** (il gruppo 1 cattura il
     nome del campo).

   Con i formati a delimitatori il prefisso «da compilare» / «da inserire»
   dentro le parentesi è opzionale e viene comunque tolto dal nome del campo:
   `[da compilare nome e cognome]` e `[nome e cognome]` danno lo stesso campo.
3. Premi **«Analizza template»**: mostra i campi rilevati.
4. Aggiungi **uno o più file guida**.
5. (Opzionale) Imposta cartella di output e suffisso del nome file.
6. **AI locale:** scegli l'endpoint (LM Studio `:1234` o Ollama `:11434`),
   premi **«Prova connessione»** e, se vuoi, seleziona il modello.
   Se disattivi l'AI, viene usata un'euristica offline (righe tipo `Etichetta: valore`).
7. Premi **«Estrai dati dai file guida»**.

**Scheda «2 · Revisione e generazione»**

8. Scegli un file guida dall'elenco e **controlla/correggi** i valori.
9. Premi **«Genera tutti i documenti»**.

## Note sui segnaposto nel template

- **Consigliato:** usa i delimitatori a parentesi quadre `[ … ]`. Tutto ciò che
  sta tra le parentesi è il campo, senza ambiguità sui confini; puoi mettere più
  campi sulla stessa riga o dentro una frase. Il prefisso «da compilare» è
  opzionale e viene rimosso dal nome del campo.
- Il formato *«da compilare …» senza parentesi* è disponibile per compatibilità:
  lì il nome del campo termina a **virgola, punto e virgola, due o più spazi,
  tabulazione o fine riga**, quindi è meno affidabile per il testo inline.
- L'app cerca i segnaposto anche dentro **tabelle, intestazioni e piè di pagina**.

## Risoluzione problemi

- **«Prova connessione» resta senza esito / non diventa verde.** Significa che
  non è in ascolto nessun server AI locale all'indirizzo indicato. Serve avere
  **LM Studio** (con il *Local Server* avviato) oppure **Ollama** in esecuzione,
  con un modello caricato. Verde = connesso; rosso = server non raggiungibile.
  Puoi anche lavorare **senza AI**: togli la spunta *«Usa AI locale»* (vedi sotto).
- **Non vedo il pulsante «Estrai dati».** Ora è in una **barra fissa in fondo**
  alla scheda «1 · Configurazione», sempre visibile; il resto del modulo è
  scorrevole (rotellina del mouse o barra laterale).
- **Voglio usarlo senza AI.** Togli la spunta *«Usa AI locale»*: l'estrazione
  usa un'euristica che funziona quando nei file guida i dati sono su righe del
  tipo `Nome e cognome: Mario Rossi`, `Nr. RG: 1234/2026`. In ogni caso, nella
  scheda «2 · Revisione» puoi correggere o inserire a mano ogni valore prima di
  generare i documenti.
- **L'`.exe` dà errore all'avvio.** Ricrea l'eseguibile con `build_exe.bat`
  aggiornato (include `lxml`, necessario a python-docx). Se l'errore persiste,
  usa `run_app.bat`, che è equivalente e non richiede la compilazione.

## Privacy

Tutto avviene in locale. Le chiamate all'AI vanno solo all'indirizzo locale
configurato (es. `http://localhost:1234`) e **bypassano eventuali proxy** di
sistema.
