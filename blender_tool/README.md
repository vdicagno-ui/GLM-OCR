# 3D Style & Camera Replicator

GUI Tkinter che avvia **Blender in background** (subprocess, headless) per
renderizzare un modello `.obj` replicando telecamere, materiale e luce a partire
dalle foto originali.

## Componenti

| File | Ruolo |
|------|-------|
| `gui.py` | GUI Tkinter (estende lo script `PhotoAlignmentApp` originale). Lancia Blender come subprocess e mostra il log in tempo reale. |
| `blender_render.py` | Script eseguito **dentro** Blender: carica l'.obj, crea le telecamere, applica materiale + luce, renderizza i frame. |
| `gui.spec` | Configurazione PyInstaller per creare l'`.exe` Windows. |
| `sample_cameras.csv` | Esempio di log di fotogrammetria (formato `x,y,z`). |
| `requirements.txt` | Dipendenze di sviluppo (solo PyInstaller). |

## Prerequisiti

- **Python 3.10+** su Windows (tkinter e' incluso).
- **Blender** installato (l'app cerca `blender.exe`, con auto-rilevamento in
  `C:\Program Files\Blender Foundation\...`).

## Esecuzione in sviluppo

```bash
python gui.py
```

1. Seleziona la cartella delle immagini originali, il file `.obj`, la cartella
   di output e l'eseguibile `blender.exe`.
2. Premi **AVVIA REPLICAZIONE STILE**.
3. La GUI lancia:

   ```
   blender --background --factory-startup --python blender_render.py -- \
       --obj MODELLO.obj --out OUTPUT --images CARTELLA_FOTO
   ```

4. I frame vengono salvati come `frame_0000.png`, `frame_0001.png`, ... nella
   cartella di output.

## Telecamere: log reale o simulazione

Lo script Blender determina le posizioni delle camere così:

1. **Log di fotogrammetria**, se disponibile. Cerca nella cartella immagini
   (o usa il file passato con `--log`):
   - Meshroom: `cameras.sfm` / `*.sfm` / `cameras.json` (usa `pose.transform.center`);
   - COLMAP: `images.txt` (calcola il centro camera da quaternione + traslazione);
   - generico: CSV/TXT con righe `x,y,z` (vedi `sample_cameras.csv`).
2. **Simulazione**, se non trova alcun log: dispone N telecamere su un anello
   attorno all'oggetto (N = numero di foto trovate, con un tetto, altrimenti il
   valore di `--cameras`).

## Materiale e luce

- Materiale **Principled BSDF** neutro applicato a tutte le mesh (stile uniforme).
- Luce **Sun** fissa per ombre ripetibili.

Compatibile con Blender 3.x e 4.x (gestisce le differenze di import OBJ, nomi
engine e nomi degli input del BSDF).

## Creare l'.exe con PyInstaller

```bash
pip install -r requirements.txt
pyinstaller gui.spec
```

L'eseguibile finale:

```
dist/OBJRenderer/OBJRenderer.exe
```

`blender_render.py` viene incluso nel bundle come dato e ritrovato a runtime
tramite `resource_path()` (compatibile con l'estrazione in `sys._MEIPASS`).

> In alternativa, one-file: `pyinstaller --onefile --windowed --add-data "blender_render.py;." gui.py`
> (su Windows il separatore in `--add-data` è `;`).
