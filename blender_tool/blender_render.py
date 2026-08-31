"""
Script eseguito DENTRO Blender in modalita' headless.

Viene lanciato dalla GUI (gui.py) con:

    blender --background --factory-startup --python blender_render.py -- \
        --obj MODELLO.obj --out CARTELLA_OUTPUT --images CARTELLA_FOTO \
        [--log FILE_LOG] [--cameras N] [--resx 1920] [--resy 1080] \
        [--engine BLENDER_EEVEE] [--format PNG]

Cosa fa:
    1. Carica il file .obj indicato.
    2. Configura una serie di telecamere:
         - se viene fornito un log di fotogrammetria (o ne trova uno nella
           cartella immagini) legge da li' le coordinate delle camere;
         - altrimenti simula le coordinate disponendo le camere su un anello
           attorno all'oggetto.
    3. Imposta un materiale standard (Principled BSDF) su tutte le mesh e una
       luce fissa (Sun) per ombre e stile ripetibili.
    4. Renderizza un frame per ogni telecamera salvandolo nella cartella output.

Nota: usa solo l'API ``bpy`` di Blender, quindi va eseguito tramite Blender e
non con un interprete Python normale. E' compatibile sia con Blender 3.x sia
con 4.x (import .obj e nomi engine differiscono tra le versioni).
"""

import argparse
import glob
import json
import math
import os
import sys

import bpy
import mathutils


# ---------------------------------------------------------------------------
# Parsing degli argomenti (tutto cio' che segue "--" nella riga di comando)
# ---------------------------------------------------------------------------

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser(description="Render OBJ in Blender headless")
    parser.add_argument("--obj", required=True, help="Percorso del file .obj")
    parser.add_argument("--out", required=True, help="Cartella di output dei render")
    parser.add_argument("--images", default="", help="Cartella delle foto originali")
    parser.add_argument("--log", default="", help="File di log di fotogrammetria")
    parser.add_argument("--cameras", type=int, default=8, help="N. camere se simulate")
    parser.add_argument("--resx", type=int, default=1920)
    parser.add_argument("--resy", type=int, default=1080)
    parser.add_argument("--engine", default="BLENDER_EEVEE")
    parser.add_argument("--format", default="PNG")
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Pulizia della scena
# ---------------------------------------------------------------------------

def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    # Rimuovi eventuali dati orfani
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


# ---------------------------------------------------------------------------
# Import dell'OBJ (compatibile 3.x / 4.x)
# ---------------------------------------------------------------------------

def import_obj(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File OBJ non trovato: {path}")

    before = set(bpy.data.objects)
    if hasattr(bpy.ops.wm, "obj_import"):        # Blender >= 4.0
        bpy.ops.wm.obj_import(filepath=path)
    elif hasattr(bpy.ops.import_scene, "obj"):    # Blender 3.x
        bpy.ops.import_scene.obj(filepath=path)
    else:
        raise RuntimeError("Nessun operatore di import OBJ disponibile in questo Blender.")

    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("L'import OBJ non ha prodotto alcuna mesh.")
    print(f"[OBJ] Importate {len(meshes)} mesh.")
    return meshes


# ---------------------------------------------------------------------------
# Bounding box / centro / raggio dell'insieme di mesh
# ---------------------------------------------------------------------------

def scene_bounds(meshes):
    coords = []
    for obj in meshes:
        for corner in obj.bound_box:
            coords.append(obj.matrix_world @ mathutils.Vector(corner))
    xs = [c.x for c in coords]
    ys = [c.y for c in coords]
    zs = [c.z for c in coords]
    center = mathutils.Vector(((min(xs) + max(xs)) / 2,
                               (min(ys) + max(ys)) / 2,
                               (min(zs) + max(zs)) / 2))
    radius = max((max(xs) - min(xs)), (max(ys) - min(ys)), (max(zs) - min(zs))) / 2
    radius = max(radius, 1e-3)
    return center, radius


# ---------------------------------------------------------------------------
# Estrazione delle coordinate camera dal log di fotogrammetria
# ---------------------------------------------------------------------------

def find_log(images_dir, explicit_log):
    """Restituisce il percorso di un log di fotogrammetria, se disponibile."""
    if explicit_log and os.path.isfile(explicit_log):
        return explicit_log
    if images_dir and os.path.isdir(images_dir):
        # Nomi tipici prodotti da Meshroom / COLMAP.
        for pattern in ("cameras.sfm", "*.sfm", "cameras.json", "images.txt"):
            hits = sorted(glob.glob(os.path.join(images_dir, "**", pattern), recursive=True))
            if hits:
                return hits[0]
    return ""


def load_camera_positions(log_path):
    """Legge le posizioni (x, y, z) delle camere dal log.

    Supporta formati semplici:
      - Meshroom .sfm / .json  -> chiave "poses" con "center" del trasformo.
      - COLMAP images.txt      -> righe con quaternione + traslazione.
      - CSV/TXT generico       -> righe "x,y,z" (una per camera).
    Restituisce una lista di mathutils.Vector, oppure [] se non interpretabile.
    """
    positions = []
    ext = os.path.splitext(log_path)[1].lower()
    try:
        if ext in (".sfm", ".json"):
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for pose in data.get("poses", []):
                tr = pose.get("pose", {}).get("transform", {})
                center = tr.get("center")
                if center and len(center) == 3:
                    positions.append(mathutils.Vector([float(v) for v in center]))
        elif os.path.basename(log_path).lower() == "images.txt":
            # COLMAP: righe dispari = camere. Formato:
            # IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME
            with open(log_path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
            for ln in lines[::2]:
                parts = ln.split()
                if len(parts) >= 8:
                    qw, qx, qy, qz = map(float, parts[1:5])
                    tx, ty, tz = map(float, parts[5:8])
                    # Centro camera C = -R^T * t
                    q = mathutils.Quaternion((qw, qx, qy, qz))
                    R = q.to_matrix()
                    t = mathutils.Vector((tx, ty, tz))
                    positions.append(-(R.transposed() @ t))
        else:
            # CSV/TXT generico "x,y,z"
            with open(log_path, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln or ln.startswith("#"):
                        continue
                    sep = "," if "," in ln else None
                    parts = ln.split(sep)
                    if len(parts) >= 3:
                        try:
                            positions.append(mathutils.Vector([float(parts[i]) for i in range(3)]))
                        except ValueError:
                            continue
    except Exception as exc:
        print(f"[LOG] Impossibile interpretare il log ({exc}); si passa alla simulazione.")
        return []

    if positions:
        print(f"[LOG] Estratte {len(positions)} posizioni camera da {os.path.basename(log_path)}.")
    return positions


def simulate_positions(center, radius, count):
    """Dispone ``count`` camere su un anello inclinato attorno all'oggetto."""
    positions = []
    dist = radius * 3.0
    for i in range(count):
        angle = 2 * math.pi * i / max(count, 1)
        x = center.x + dist * math.cos(angle)
        y = center.y + dist * math.sin(angle)
        z = center.z + radius * 1.2  # leggermente dall'alto
        positions.append(mathutils.Vector((x, y, z)))
    print(f"[SIM] Simulate {len(positions)} posizioni camera su un anello.")
    return positions


def count_images(images_dir):
    if not images_dir or not os.path.isdir(images_dir):
        return 0
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff")
    total = 0
    for e in exts:
        total += len(glob.glob(os.path.join(images_dir, e)))
        total += len(glob.glob(os.path.join(images_dir, e.upper())))
    return total


# ---------------------------------------------------------------------------
# Creazione telecamere che puntano al centro dell'oggetto
# ---------------------------------------------------------------------------

def create_cameras(positions, target):
    cams = []
    for i, pos in enumerate(positions):
        cam_data = bpy.data.cameras.new(name=f"Cam_{i:03d}")
        cam_obj = bpy.data.objects.new(name=f"Cam_{i:03d}", object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)
        cam_obj.location = pos
        # Orienta la camera verso il target: -Z guarda il soggetto, +Y in alto.
        direction = (target - pos)
        cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        cams.append(cam_obj)
    print(f"[CAM] Create {len(cams)} telecamere.")
    return cams


# ---------------------------------------------------------------------------
# Materiale standard + luce fissa
# ---------------------------------------------------------------------------

def apply_standard_material(meshes):
    """Applica un Principled BSDF neutro a tutte le mesh (stile uniforme)."""
    mat = bpy.data.materials.new(name="StandardMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
        # "Roughness" esiste in tutte le versioni; "Specular" cambia nome in 4.x.
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.5
        for spec_name in ("Specular IOR Level", "Specular"):
            if spec_name in bsdf.inputs:
                bsdf.inputs[spec_name].default_value = 0.3
                break
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    print("[MAT] Materiale standard applicato a tutte le mesh.")


def add_fixed_light(center, radius):
    """Aggiunge una luce Sun fissa per ombre e stile ripetibili."""
    light_data = bpy.data.lights.new(name="KeyLight", type="SUN")
    light_data.energy = 3.0
    if hasattr(light_data, "angle"):
        light_data.angle = math.radians(2.0)  # ombre leggermente morbide
    light_obj = bpy.data.objects.new(name="KeyLight", object_data=light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.location = center + mathutils.Vector((radius * 2, -radius * 2, radius * 3))
    light_obj.rotation_euler = (math.radians(50), 0, math.radians(45))
    print("[LIGHT] Luce fissa (Sun) aggiunta.")


# ---------------------------------------------------------------------------
# Impostazioni di render
# ---------------------------------------------------------------------------

def configure_render(args):
    scene = bpy.context.scene

    # Engine: se il nome richiesto non esiste in questa versione, usa un fallback.
    engine = args.engine
    try:
        scene.render.engine = engine
    except TypeError:
        # Blender 4.2+ ha rinominato EEVEE in BLENDER_EEVEE_NEXT.
        for fallback in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH"):
            try:
                scene.render.engine = fallback
                engine = fallback
                break
            except TypeError:
                continue
    print(f"[RENDER] Engine: {engine}")

    scene.render.resolution_x = args.resx
    scene.render.resolution_y = args.resy
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = args.format

    # Sfondo neutro
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)


def ext_for_format(fmt):
    return {
        "PNG": "png",
        "JPEG": "jpg",
        "OPEN_EXR": "exr",
        "TIFF": "tif",
    }.get(fmt, "png")


def render_all(cameras, out_dir, fmt):
    scene = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    ext = ext_for_format(fmt)
    for i, cam in enumerate(cameras):
        scene.camera = cam
        filepath = os.path.join(out_dir, f"frame_{i:04d}.{ext}")
        scene.render.filepath = filepath
        print(f"[RENDER] ({i + 1}/{len(cameras)}) -> {filepath}")
        bpy.ops.render.render(write_still=True)
    print(f"[DONE] {len(cameras)} frame renderizzati in {out_dir}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    print("=" * 60)
    print("Blender headless render - avvio")
    print("=" * 60)

    reset_scene()
    meshes = import_obj(args.obj)
    center, radius = scene_bounds(meshes)
    print(f"[SCENE] Centro={tuple(round(v, 3) for v in center)} Raggio={radius:.3f}")

    # 2) Telecamere: prima prova dal log, poi simula.
    log_path = find_log(args.images, args.log)
    positions = load_camera_positions(log_path) if log_path else []
    if not positions:
        n = args.cameras
        img_count = count_images(args.images)
        if img_count:
            n = min(max(img_count, 1), 72)  # una camera per foto, con un tetto
            print(f"[SIM] Trovate {img_count} foto: uso {n} telecamere simulate.")
        positions = simulate_positions(center, radius, n)

    cameras = create_cameras(positions, center)

    # 3) Materiale + luce
    apply_standard_material(meshes)
    add_fixed_light(center, radius)

    # 4) Render
    configure_render(args)
    render_all(cameras, args.out, args.format)

    print("Blender headless render - completato")


if __name__ == "__main__":
    main()
