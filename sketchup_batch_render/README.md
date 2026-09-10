# SketchUp Batch Render — griglia 3×3 (SketchUp 2017, Windows)

Applicazione grafica per Windows che:

1. carica un file **`.skp`** in **SketchUp 2017**;
2. lo inquadra secondo **9 posizioni** diverse (camera + luci/ombre), definite
   da **9 file JSON**;
3. scatta una **foto `.bmp`** per ogni posizione, salvandole nella cartella di
   output;
4. unisce le 9 foto in un **unico file `.bmp` con griglia 3×3**, in sequenza
   progressiva **da 1 a 9, da sinistra a destra e dall'alto verso il basso**:

   ```
   1  2  3
   4  5  6
   7  8  9
   ```

> Funziona con l'installazione di **SketchUp 2017 già presente** sul PC.
> Il file `.skp` **non viene mai modificato/salvato**: le variazioni di
> camera e ombre restano solo in memoria.

---

## 1. Come funziona (in breve)

L'app è composta da due parti che collaborano:

- **`gui.py`** (interfaccia grafica Python): raccoglie i dati, prepara un
  "job", avvia SketchUp, attende la fine e crea la griglia 3×3.
- **`sketchup_runner.rb`** (script Ruby per SketchUp): viene installato
  automaticamente nella cartella *Plugins* di SketchUp. All'avvio del
  programma controlla se c'è un lavoro da fare, apre il modello, applica le 9
  posizioni e scatta le 9 foto.

La comunicazione avviene tramite piccoli file nella cartella `%TEMP%`
(`skp_batch_job.json` → istruzioni, `skp_batch_status.json` → esito,
`skp_batch_log.txt` → diagnostica).

---

## 2. Creare l'eseguibile `.exe`

Serve **Python 3.8+** installato su Windows (durante l'installazione
selezionare *"Add Python to PATH"*). Poi:

1. Copiare l'intera cartella `sketchup_batch_render` sul PC Windows.
2. Fare **doppio clic su `build.bat`** (oppure eseguirlo dal prompt).
3. Al termine, l'eseguibile è in:
   ```
   dist\SketchUpBatchRender.exe
   ```

L'`.exe` è autonomo: include già lo script Ruby e la libreria di immagini.

> In alternativa, senza creare l'eseguibile, si può avviare direttamente:
> ```
> pip install -r requirements.txt
> python gui.py
> ```

---

## 3. Uso

1. Avviare `SketchUpBatchRender.exe`.
2. **File SketchUp (.skp)** → scegliere il modello.
3. **9 file JSON** → *Aggiungi cartella…* (carica automaticamente i `.json`
   ordinati) oppure *Aggiungi file…*. Verificare che l'ordine in elenco sia
   **1 → 9** (usare *Su*/*Giù* per correggere). L'ordine dell'elenco è quello
   con cui le foto vengono numerate e disposte nella griglia.
4. **Cartella di output** → dove salvare le foto e la griglia finale.
5. **SketchUp.exe** → già preimpostato su
   `C:\Program Files\SketchUp\SketchUp 2017\SketchUp.exe` (modificabile).
6. **Risoluzione** e **unità delle coordinate** (vedi sotto).
7. Premere ***Avvia rendering e crea griglia 3×3***.

Durante l'elaborazione SketchUp si apre da solo, esegue le 9 inquadrature e
viene chiuso automaticamente. I risultati nella cartella di output:

- `pos_01.bmp` … `pos_09.bmp` — le 9 foto singole;
- `montage_3x3.bmp` — **l'immagine finale 3×3**.

> Consiglio: prima dell'avvio **chiudere SketchUp** se è già aperto.

---

## 4. Formato dei file JSON (una posizione per file)

Ogni file descrive **una** posizione. Schema:

```json
{
  "camera": {
    "eye":    [5000, 0, 1600],
    "target": [0, 0, 800],
    "up":     [0, 0, 1],
    "perspective": true,
    "fov": 35
  },
  "shadow": {
    "display_shadows": true,
    "light": 80,
    "dark": 30,
    "north_angle": 0,
    "use_sun_for_shading": true,
    "date": "2024-06-21",
    "time_of_day": "14:00"
  }
}
```

### camera
| Campo         | Tipo        | Descrizione |
|---------------|-------------|-------------|
| `eye`         | `[x, y, z]` | posizione dell'osservatore |
| `target`      | `[x, y, z]` | punto guardato |
| `up`          | `[x, y, z]` | verticale (opz., default `[0,0,1]`) |
| `perspective` | bool        | `true` prospettiva, `false` parallela (opz., default `true`) |
| `fov`         | numero      | angolo di campo in gradi (solo prospettiva, opz.) |
| `height`      | numero      | altezza inquadratura (solo parallela, opz.) |
| `units`       | testo       | unità di *questa* camera; sovrascrive quella globale (opz.) |

Le coordinate `eye`/`target` sono espresse nell'**unità scelta nella GUI**
(mm, cm, m, inch, ft) e convertite internamente. Se usi le coordinate lette
in SketchUp, imposta l'unità di misura del tuo modello.

### shadow (luci e ombre)
| Campo                  | Tipo   | Descrizione |
|------------------------|--------|-------------|
| `display_shadows`      | bool   | mostra le ombre (default `true`) |
| `light`                | 0–100  | intensità luce |
| `dark`                 | 0–100  | intensità zone in ombra |
| `north_angle`          | gradi  | orientamento del nord |
| `use_sun_for_shading`  | bool   | usa il sole per l'illuminazione |
| `date` + `time_of_day` | testo  | data `AAAA-MM-GG` e ora `HH:MM` del sole |
| `time`                 | testo  | in alternativa: `2024-06-21T14:00:00` |
| `latitude`/`longitude` | numero | posizione geografica (opz.) |
| `tz_offset`            | numero | fuso orario in ore (opz.) |
| `display_on_ground`, `display_on_all_faces`, `edges_cast_shadows` | bool | opzioni ombre (opz.) |

Nella cartella [`sample_json/`](sample_json/) trovi **9 file di esempio**
(`pos1.json` … `pos9.json`) già pronti, con una camera che orbita attorno
all'origine e ore del giorno diverse.

---

## 5. Ricomporre solo la griglia (senza SketchUp)

Se hai già le 9 immagini e vuoi solo la griglia 3×3:

```
python compose.py cartella\montage_3x3.bmp pos_01.bmp pos_02.bmp ... pos_09.bmp
```

---

## 6. Risoluzione dei problemi

- **Non succede nulla / nessuna foto**: apri `%TEMP%\skp_batch_log.txt` per
  vedere il dettaglio. Verifica il percorso di `SketchUp.exe`.
- **"Tempo scaduto"**: modelli molto pesanti possono superare i 15 minuti;
  il valore è modificabile in `gui.py` (`RENDER_TIMEOUT`).
- **Coordinate sbagliate/foto "vuote"**: controlla l'**unità di misura**
  selezionata e che `eye` e `target` non coincidano.
- **SketchUp già aperto**: chiudilo prima di avviare, per evitare che il
  nuovo comando venga dirottato sulla finestra esistente.
- Lo script Ruby viene (re)installato in
  `%APPDATA%\SketchUp\SketchUp 2017\SketchUp\Plugins\skp_batch_render.rb`
  a ogni avvio: resta inerte quando non c'è un lavoro in corso.

---

## 7. File del progetto

| File                  | Ruolo |
|-----------------------|-------|
| `gui.py`              | interfaccia grafica e orchestrazione |
| `sketchup_runner.rb`  | script eseguito dentro SketchUp 2017 |
| `compose.py`          | creazione della griglia 3×3 |
| `build.bat`           | crea `SketchUpBatchRender.exe` |
| `requirements.txt`    | dipendenze Python (Pillow) |
| `sample_json/`        | 9 file JSON di esempio |
