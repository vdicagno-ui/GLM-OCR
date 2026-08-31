# 3D Style & Camera Replicator

Applicazione Windows (GUI Tkinter) che, partendo da un **set di foto** di un
oggetto 3D scattate da prospettive diverse, **ricostruisce le coordinate delle
telecamere** e le **riapplica a un nuovo oggetto `.obj`**, generando un nuovo set
di immagini con lo **stesso punto di vista, la stessa focale, la stessa
risoluzione e uno stile/colorazione coerente**.

```
Foto (bmp/png)  --[Meshroom: Structure-from-Motion]-->  pose camera (cameras.sfm)
                                                              |
Nuovo oggetto .obj  ---------------------------------[Blender headless]--> nuovo set immagini
```

## Componenti

| File | Ruolo |
|------|-------|
| `gui.py` | GUI (estende lo script `PhotoAlignmentApp`). Orchestrazione a 2 stadi: Meshroom poi Blender, con log in tempo reale e pulsante Interrompi. |
| `blender_render.py` | Script eseguito **dentro** Blender: carica l'.obj, ricrea le camere dalle pose SfM (posa + focale + risoluzione), applica materiale + luce fissa + sfondo campionato, renderizza. |
| `gui.spec` | Configurazione PyInstaller per l'`.exe` Windows. |
| `sample_cameras.csv` | Esempio di file pose generico (`x,y,z`). |
| `requirements.txt` | Dipendenze di sviluppo (solo PyInstaller). |

## Prerequisiti (Windows)

- **Python 3.10+** (tkinter incluso).
- **Blender** installato — l'app auto-rileva `blender.exe` in
  `C:\Program Files\Blender Foundation\...`.
- **Meshroom** (AliceVision) — l'app auto-rileva `meshroom_batch.exe` in
  `C:\Program Files\Meshroom*\`. Scaricabile gratis da alicevision.org.
  *Opzionale*: se hai già un `cameras.sfm`, puoi puntarlo direttamente e saltare
  Meshroom.

## Come funziona

### Stadio 1 — Meshroom (Structure-from-Motion)
Le foto vengono passate a `meshroom_batch`, fermandosi al nodo
`StructureFromMotion` (nessun calcolo denso / niente CUDA richiesta):

```
meshroom_batch --input FOTO --pipeline photogrammetry \
    --toNode StructureFromMotion --output OUT/meshroom/sfm --cache OUT/meshroom/cache
```

Il risultato è un `cameras.sfm` (JSON AliceVision) con, per ogni foto, la posa
della camera (rotazione + centro) e gli intrinseci (focale, sensore, risoluzione).
L'app lo cerca automaticamente nell'output e nella cache.

### Stadio 2 — Blender (render del nuovo oggetto)
Blender viene lanciato headless con lo script custom:

```
blender --background --factory-startup --python blender_render.py -- \
    --obj MODELLO.obj --out OUTPUT --images FOTO --sfm cameras.sfm
```

Per ogni camera stimata lo script:
- ricostruisce la **posa reale** convertendo la convenzione AliceVision
  (X destra, Y giù, Z avanti) in quella di Blender (X destra, Y su, Z indietro);
- imposta **focale e sensore** per riprodurre lo stesso campo visivo;
- renderizza alla **stessa risoluzione** dello scatto originale;
- salva il frame con il **nome della foto sorgente** corrispondente.

**Stile/colorazione coerenti:** materiale Principled BSDF neutro uniforme, luce
`Sun` fissa (ombre ripetibili) e colore di sfondo del mondo campionato dai bordi
di una foto originale.

### Fallback
- Se fornisci un `.sfm`/`images.txt`/CSV al punto 6, Meshroom viene saltato.
- Se non c'è né Meshroom né un file pose, Blender **simula** le camere su un
  anello attorno all'oggetto (una per foto trovata).

## Esecuzione in sviluppo

```bash
python gui.py
```

Compila i campi 1–5 (immagini, obj, output, blender.exe, Meshroom) e premi
**AVVIA REPLICAZIONE STILE**.

## Creare l'.exe con PyInstaller

```bash
pip install -r requirements.txt
pyinstaller gui.spec
```

Eseguibile finale: `dist/OBJRenderer/OBJRenderer.exe`.
`blender_render.py` è incluso nel bundle e ritrovato a runtime via
`resource_path()`. Blender e Meshroom **non** vengono impacchettati: restano
programmi esterni che l'app invoca (l'utente li installa separatamente).

## Note e limiti

- Un buon risultato SfM richiede foto con sufficiente sovrapposizione e texture;
  se Meshroom non registra abbastanza camere, alcune viste possono mancare.
- La conversione della posa assume la convenzione standard AliceVision. Se le
  camere risultassero specchiate/capovolte con la tua versione di Meshroom,
  è il punto da rivedere in `load_alicevision_sfm()` (matrice `conv`).
- La replica dell'illuminazione è uno stile coerente (luce fissa + sfondo
  campionato), non una ricostruzione fisica della luce reale dalle ombre.
