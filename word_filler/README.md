# Compilatore Template Word — Offline

Applicazione desktop con interfaccia grafica per **Windows** che compila un
template Word riempiendo dei segnaposto («da compilare …») con i dati estratti
da uno o più **file guida**. Funziona **completamente offline**: se serve l'AI,
usa un modello **locale** tramite LM Studio o Ollama. Nessun dato lascia il
computer.

## Come funziona

1. **Template Word** (`.docx`) con etichette segnaposto, per esempio:
   > Il sottoscritto **da compilare nome cognome**, procedimento **da compilare nr. RG**, con incarico del **da compilare data di incarico**…
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
   - *Etichetta «da compilare …»* (predefinito) → riconosce `da compilare nome cognome`
   - *Doppia graffa* → `{{nome cognome}}`
   - *Parentesi quadra* → `[nome cognome]`
   - *Guillemet* → `«nome cognome»`
   - oppure una **espressione regolare personalizzata** (il gruppo 1 cattura il
     nome del campo).
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

- Nel formato *«da compilare …»* il nome del campo è il testo che segue
  `da compilare` fino a **due o più spazi, una tabulazione o fine riga**. Così
  descrizioni con un punto (es. `nr. RG`) restano integre. Se hai più campi
  sulla stessa riga, separali con **almeno due spazi** o una tabulazione, oppure
  usa un formato con delimitatori (`{{…}}`, `[…]`, `«…»`) più robusto.
- L'app cerca i segnaposto anche dentro **tabelle, intestazioni e piè di pagina**.

## Privacy

Tutto avviene in locale. Le chiamate all'AI vanno solo all'indirizzo locale
configurato (es. `http://localhost:1234`) e **bypassano eventuali proxy** di
sistema.
