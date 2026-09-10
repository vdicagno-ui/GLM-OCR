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

Ogni file descrive **una** posizione. È supportato **direttamente il formato
nativo di SketchUp** (quello che ottieni esportando `camera` e `shadow_info`
dall'API), quindi puoi usare i tuoi file così come sono:

```json
{
  "camera": {
    "eye":    [0.6177856469, 0.9434952391, 1.0924834337],
    "target": [-1.3631206782, 0.9761944310, 0.0949077388],
    "up":     [-0.4496707065, 0.0074227986, 0.8931635672],
    "perspective": true,
    "fov": 35.0,
    "image_width": 0.0
  },
  "shadows": {
    "DisplayShadows": true,
    "UseSunForAllShading": true,
    "Light": 61,
    "Dark": 13,
    "TZOffset": -7.0,
    "Latitude": 40.018309,
    "Longitude": -105.242139,
    "ShadowTime": 1780316400,
    "ShadowDate": 0
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
| `image_width` | numero      | larghezza immagine SketchUp in pollici; `0` = non impostata (opz.) |
| `height`      | numero      | altezza inquadratura (solo parallela, opz.) |
| `units`       | testo       | unità di *questa* camera; sovrascrive quella globale (opz.) |

> **Unità delle coordinate (importante).** Le coordinate `eye`/`target`
> devono essere nella stessa scala della geometria del modello, altrimenti la
> camera "punta" fuori dall'oggetto e le foto mostrano solo lo sfondo.
> Per questo la GUI è preimpostata su **`auto`**: il programma misura la
> dimensione reale del modello aperto e sceglie da solo l'unità (mm/cm/m/inch/ft)
> che inquadra correttamente l'oggetto. La scelta viene annotata nel log
> (`%TEMP%\skp_batch_log.txt`). Se preferisci, puoi forzare manualmente
> l'unità dal menu a tendina.

### shadows (luci e ombre) — chiavi native di SketchUp
| Chiave                 | Tipo    | Descrizione |
|------------------------|---------|-------------|
| `DisplayShadows`       | bool    | mostra le ombre |
| `UseSunForAllShading`  | bool    | usa il sole per l'illuminazione |
| `Light`                | 0–100   | intensità luce |
| `Dark`                 | 0–100   | intensità zone in ombra |
| `NorthAngle`           | gradi   | orientamento del nord |
| `TZOffset`             | ore     | fuso orario |
| `Latitude`/`Longitude` | numero  | posizione geografica |
| `ShadowTime`           | intero  | data+ora del sole come **timestamp Unix** (time_t) |
| `ShadowDate`           | —       | ignorato (la data è già dentro `ShadowTime`) |

Qualsiasi altra chiave nativa valida di `ShadowInfo` viene passata così com'è;
una chiave non riconosciuta viene semplicemente saltata e annotata nel log.

<details>
<summary>Alias "amichevoli" alternativi (facoltativi)</summary>

Al posto delle chiavi native puoi usare, se preferisci, questi nomi minuscoli
(usati nulla di obbligatorio): `display_shadows`, `light`, `dark`,
`north_angle`, `use_sun_for_shading`, `latitude`, `longitude`, `tz_offset`,
`display_on_ground`, `display_on_all_faces`, `edges_cast_shadows`, e per l'ora
del sole `date` + `time_of_day` (`"2024-06-21"` + `"14:00"`) oppure
`time` (`"2024-06-21T14:00:00"`). Anche il blocco camera accetta la chiave
singolare `shadow` invece di `shadows`.
</details>

Nella cartella [`sample_json/`](sample_json/) trovi **9 file di esempio**
(`pos1.json` … `pos9.json`) già pronti, nel formato nativo, con la camera che
orbita attorno al soggetto e l'ora del sole che avanza di posizione in posizione.

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
- **Le foto mostrano solo lo sfondo (oggetto fuori campo)**: è quasi sempre
  un problema di **scala/unità**. Lascia l'unità su **`auto`**; se ancora non
  va, apri `%TEMP%\skp_batch_log.txt` e guarda la riga *"Auto-unità"* (mostra
  la diagonale del modello e l'unità scelta) e le righe *"camera eye/target"*.
  Se i valori camera sono molto più piccoli/grandi della diagonale del modello,
  forza manualmente l'unità corretta (di solito `m` se le coordinate sono ~1).
- **"Il modello sembra vuoto o non caricato"**: il file `.skp` non è stato
  aperto (percorso errato) o non contiene geometria visibile. Verifica il file.
- **Aggiornare lo script senza ricompilare l'exe**: metti una copia di
  `sketchup_runner.rb` **nella stessa cartella** dell'eseguibile: la GUI usa
  quella al posto di quella interna.
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
