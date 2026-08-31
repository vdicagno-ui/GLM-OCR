"""
Script eseguito DENTRO Blender in modalita' headless.

Viene lanciato dalla GUI (gui.py) con:

    blender --background --factory-startup --python blender_render.py -- \
        --obj MODELLO.obj --out CARTELLA_OUTPUT \
        [--sfm cameras.sfm] [--images CARTELLA_FOTO] \
        [--cameras N] [--engine BLENDER_EEVEE] [--format PNG] [--no-bg-sample]

Cosa fa (replica dello "stile" con rig coerente):
    1. Carica il file .obj indicato.
    2. Configura le telecamere:
         - se viene fornito un file SfM (.sfm/.json AliceVision, o images.txt
           COLMAP, o CSV x,y,z) ricostruisce posa + focale + risoluzione reali
           di ogni scatto originale;
         - altrimenti simula le camere su un anello attorno all'oggetto.
    3. Applica un materiale standard (Principled BSDF neutro) a tutte le mesh e
       una luce fissa (Sun) per ombre e stile ripetibili. Lo sfondo del mondo
       viene campionato dal colore medio delle foto originali (se disponibili),
       cosi' i render nascono su una base cromatica simile.
    4. Renderizza un frame per ogni telecamera, alla stessa risoluzione dello
       scatto originale, salvandolo nella cartella di output con il nome della
       foto sorgente corrispondente.

Usa solo l'API ``bpy``: va eseguito tramite Blender, non con Python normale.
Compatibile con Blender 3.x e 4.x.
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
# Parsing argomenti (tutto cio' che segue "--" nella riga di comando)
# ---------------------------------------------------------------------------

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    p = argparse.ArgumentParser(description="Render OBJ in Blender headless")
    p.add_argument("--obj", required=True, help="Percorso del file .obj")
    p.add_argument("--out", required=True, help="Cartella di output dei render")
    p.add_argument("--sfm", default="", help="File pose fotogrammetria (AliceVision .sfm/.json, COLMAP images.txt, o CSV)")
    p.add_argument("--images", default="", help="Cartella delle foto originali (per fallback e campione sfondo)")
    p.add_argument("--cameras", type=int, default=8, help="N. camere se simulate")
    p.add_argument("--resx", type=int, default=1920, help="Risoluzione X di default (fallback)")
    p.add_argument("--resy", type=int, default=1080, help="Risoluzione Y di default (fallback)")
    p.add_argument("--engine", default="BLENDER_EEVEE")
    p.add_argument("--format", default="PNG")
    p.add_argument("--no-bg-sample", action="store_true", help="Non campionare il colore di sfondo dalle foto")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Pulizia scena
# ---------------------------------------------------------------------------

def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.images):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


# ---------------------------------------------------------------------------
# Import OBJ (compatibile 3.x / 4.x)
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
    return center, max(radius, 1e-3)


# ---------------------------------------------------------------------------
# Camera spec = dizionario che descrive una telecamera da creare
#   { name, location(Vector),
#     matrix(Matrix4 camera-to-world) OPPURE target(Vector),
#     lens(mm|None), sensor_width(mm|None), resx(int|None), resy(int|None) }
# ---------------------------------------------------------------------------

def _to_float(v, default=0.0):
    try:
        if isinstance(v, (list, tuple)):
            v = v[0]
        return float(v)
    except (TypeError, ValueError, IndexError):
        return default


def load_alicevision_sfm(data):
    """Estrae le camere da un dizionario SfM in formato AliceVision (Meshroom).

    Ogni vista collegata a una posa produce una spec con posa reale (matrice
    camera-to-world in convenzione Blender) e intrinseci (focale/sensore/risol.).
    """
    intr = {}
    for it in data.get("intrinsics", []):
        key = it.get("intrinsicId")
        if key is not None:
            intr[str(key)] = it

    poses = {}
    for pz in data.get("poses", []):
        key = pz.get("poseId")
        tr = pz.get("pose", {}).get("transform")
        if key is not None and tr:
            poses[str(key)] = tr

    # Conversione dagli assi camera AliceVision (X destra, Y giu', Z avanti)
    # agli assi camera Blender (X destra, Y su', Z indietro): diag(1,-1,-1).
    conv = mathutils.Matrix(((1, 0, 0), (0, -1, 0), (0, 0, -1)))

    specs = []
    for v in data.get("views", []):
        pid = str(v.get("poseId"))
        if pid not in poses:
            continue
        tr = poses[pid]
        rot = tr.get("rotation")
        cen = tr.get("center")
        if not rot or not cen or len(rot) < 9 or len(cen) < 3:
            continue

        r = [ _to_float(x) for x in rot ]          # row-major, world->camera (R)
        R = mathutils.Matrix(((r[0], r[1], r[2]),
                              (r[3], r[4], r[5]),
                              (r[6], r[7], r[8])))
        C = mathutils.Vector([_to_float(cen[i]) for i in range(3)])
        R_c2w = R.transposed()                     # camera->world
        R_blender = R_c2w @ conv                   # assi Blender
        M = mathutils.Matrix.Translation(C) @ R_blender.to_4x4()

        it = intr.get(str(v.get("intrinsicId")), {})
        width = int(_to_float(v.get("width") or it.get("width") or 1920, 1920))
        height = int(_to_float(v.get("height") or it.get("height") or 1080, 1080))
        sensor_w = _to_float(it.get("sensorWidth"), 36.0) or 36.0

        # Focale in mm: preferisci 'focalLength' (mm); altrimenti da pixel.
        lens = _to_float(it.get("focalLength"), 0.0)
        if lens <= 0:
            pxf = it.get("pxFocalLength") or it.get("pxInitialFocalLength")
            pxf = _to_float(pxf, 0.0)
            if pxf > 0 and width > 0:
                lens = pxf / width * sensor_w
        if lens <= 0:
            lens = 50.0

        name = os.path.basename(str(v.get("path", ""))) or None
        specs.append({
            "name": name,
            "location": C,
            "matrix": M,
            "lens": lens,
            "sensor_width": sensor_w,
            "resx": width,
            "resy": height,
        })
    if specs:
        print(f"[SFM] Ricostruite {len(specs)} camere da AliceVision.")
    return specs


def load_colmap_images_txt(path):
    """COLMAP images.txt -> specs (solo posa; intrinseci non letti qui)."""
    specs = []
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    conv = mathutils.Matrix(((1, 0, 0), (0, -1, 0), (0, 0, -1)))
    for ln in lines[::2]:  # righe dispari = camere
        parts = ln.split()
        if len(parts) < 10:
            continue
        qw, qx, qy, qz = map(float, parts[1:5])
        tx, ty, tz = map(float, parts[5:8])
        name = parts[9]
        q = mathutils.Quaternion((qw, qx, qy, qz))
        R = q.to_matrix()                 # world->camera
        t = mathutils.Vector((tx, ty, tz))
        C = -(R.transposed() @ t)
        R_blender = R.transposed() @ conv
        M = mathutils.Matrix.Translation(C) @ R_blender.to_4x4()
        specs.append({"name": os.path.basename(name), "location": C, "matrix": M,
                      "lens": None, "sensor_width": None, "resx": None, "resy": None})
    if specs:
        print(f"[SFM] Ricostruite {len(specs)} camere da COLMAP images.txt.")
    return specs


def load_csv_positions(path):
    """CSV/TXT 'x,y,z' -> specs con sola posizione (guardano il centro)."""
    specs = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            sep = "," if "," in ln else None
            parts = ln.split(sep)
            if len(parts) >= 3:
                try:
                    loc = mathutils.Vector([float(parts[i]) for i in range(3)])
                except ValueError:
                    continue
                specs.append({"name": None, "location": loc, "target": True,
                              "lens": None, "sensor_width": None, "resx": None, "resy": None})
    if specs:
        print(f"[SFM] Lette {len(specs)} posizioni camera da CSV.")
    return specs


def load_camera_specs(sfm_path):
    """Dispatch in base al contenuto/estensione del file pose."""
    if not sfm_path or not os.path.isfile(sfm_path):
        return []
    base = os.path.basename(sfm_path).lower()
    ext = os.path.splitext(base)[1]
    try:
        if ext in (".sfm", ".json", ".abc.json"):
            with open(sfm_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            specs = load_alicevision_sfm(data)
            if specs:
                return specs
        if base == "images.txt":
            return load_colmap_images_txt(sfm_path)
        # tentativo JSON generico
        if ext in (".sfm", ".json"):
            return []
        return load_csv_positions(sfm_path)
    except Exception as exc:
        print(f"[SFM] Impossibile interpretare '{sfm_path}': {exc}")
        return []


# ---------------------------------------------------------------------------
# Simulazione (fallback)
# ---------------------------------------------------------------------------

def count_images(images_dir):
    if not images_dir or not os.path.isdir(images_dir):
        return []
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tif", "*.tiff")
    hits = []
    for e in exts:
        hits += glob.glob(os.path.join(images_dir, e))
        hits += glob.glob(os.path.join(images_dir, e.upper()))
    return sorted(set(hits))


def simulate_specs(center, radius, count, names=None):
    specs = []
    dist = radius * 3.0
    for i in range(count):
        angle = 2 * math.pi * i / max(count, 1)
        loc = mathutils.Vector((center.x + dist * math.cos(angle),
                                center.y + dist * math.sin(angle),
                                center.z + radius * 1.2))
        name = os.path.basename(names[i]) if names and i < len(names) else None
        specs.append({"name": name, "location": loc, "target": True,
                      "lens": None, "sensor_width": None, "resx": None, "resy": None})
    print(f"[SIM] Simulate {len(specs)} camere su un anello.")
    return specs


# ---------------------------------------------------------------------------
# Creazione telecamere
# ---------------------------------------------------------------------------

def create_cameras(specs, target, default_resx, default_resy):
    cams = []
    for i, spec in enumerate(specs):
        cam_data = bpy.data.cameras.new(name=f"Cam_{i:03d}")
        if spec.get("lens"):
            cam_data.sensor_fit = "HORIZONTAL"
            cam_data.sensor_width = spec.get("sensor_width") or 36.0
            cam_data.lens = spec["lens"]
        cam_obj = bpy.data.objects.new(name=f"Cam_{i:03d}", object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)

        if spec.get("matrix") is not None:
            cam_obj.matrix_world = spec["matrix"]
        else:
            cam_obj.location = spec["location"]
            direction = target - spec["location"]
            cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

        spec["_resx"] = spec.get("resx") or default_resx
        spec["_resy"] = spec.get("resy") or default_resy
        spec["_cam"] = cam_obj
        cams.append(spec)
    print(f"[CAM] Create {len(cams)} telecamere.")
    return cams


# ---------------------------------------------------------------------------
# Materiale standard + luce fissa + sfondo campionato
# ---------------------------------------------------------------------------

def apply_standard_material(meshes):
    mat = bpy.data.materials.new(name="StandardMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
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
    light_data = bpy.data.lights.new(name="KeyLight", type="SUN")
    light_data.energy = 3.0
    if hasattr(light_data, "angle"):
        light_data.angle = math.radians(2.0)
    light_obj = bpy.data.objects.new(name="KeyLight", object_data=light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.location = center + mathutils.Vector((radius * 2, -radius * 2, radius * 3))
    light_obj.rotation_euler = (math.radians(50), 0, math.radians(45))
    print("[LIGHT] Luce fissa (Sun) aggiunta.")


def sample_background_color(images_dir):
    """Colore medio (robusto) campionato dai bordi di una foto sorgente.

    I bordi di uno scatto su fondo uniforme approssimano il colore di sfondo.
    Best-effort: qualsiasi errore -> None (si usa lo sfondo di default).
    """
    paths = count_images(images_dir)
    if not paths:
        return None
    try:
        img = bpy.data.images.load(paths[0], check_existing=True)
        w, h = img.size
        if w == 0 or h == 0 or w * h > 6_000_000:
            return None
        px = list(img.pixels)  # RGBA float [0..1], una sola copia
        ch = img.channels or 4

        def pixel(x, y):
            idx = (y * w + x) * ch
            return px[idx], px[idx + 1], px[idx + 2]

        samples = []
        margin_x = max(1, w // 20)
        margin_y = max(1, h // 20)
        for (x, y) in ((margin_x, margin_y), (w - margin_x - 1, margin_y),
                       (margin_x, h - margin_y - 1), (w - margin_x - 1, h - margin_y - 1)):
            samples.append(pixel(x, y))
        r = sum(s[0] for s in samples) / len(samples)
        g = sum(s[1] for s in samples) / len(samples)
        b = sum(s[2] for s in samples) / len(samples)
        print(f"[BG] Colore di sfondo campionato: ({r:.3f}, {g:.3f}, {b:.3f})")
        return (r, g, b, 1.0)
    except Exception as exc:
        print(f"[BG] Campionamento sfondo non riuscito ({exc}).")
        return None


def configure_world(bg_color):
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = bg_color or (0.05, 0.05, 0.05, 1.0)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def configure_render(args):
    scene = bpy.context.scene
    engine = args.engine
    try:
        scene.render.engine = engine
    except TypeError:
        for fb in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH"):
            try:
                scene.render.engine = fb
                engine = fb
                break
            except TypeError:
                continue
    print(f"[RENDER] Engine: {engine}")
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = args.format


def ext_for_format(fmt):
    return {"PNG": "png", "JPEG": "jpg", "OPEN_EXR": "exr", "TIFF": "tif"}.get(fmt, "png")


def render_all(cams, out_dir, fmt):
    scene = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    ext = ext_for_format(fmt)
    for i, spec in enumerate(cams):
        scene.camera = spec["_cam"]
        scene.render.resolution_x = spec["_resx"]
        scene.render.resolution_y = spec["_resy"]

        if spec.get("name"):
            stem = os.path.splitext(spec["name"])[0]
            fname = f"{stem}.{ext}"
        else:
            fname = f"frame_{i:04d}.{ext}"
        filepath = os.path.join(out_dir, fname)
        scene.render.filepath = filepath
        print(f"[RENDER] ({i + 1}/{len(cams)}) {spec['_resx']}x{spec['_resy']} -> {filepath}")
        bpy.ops.render.render(write_still=True)
    print(f"[DONE] {len(cams)} frame renderizzati in {out_dir}")


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

    # Camere: prima dal file SfM, poi simulazione.
    specs = load_camera_specs(args.sfm)
    if not specs:
        img_paths = count_images(args.images)
        n = len(img_paths) if img_paths else args.cameras
        n = min(max(n, 1), 200)
        if img_paths:
            print(f"[SIM] Nessun SfM valido: {len(img_paths)} foto -> {n} camere simulate.")
        specs = simulate_specs(center, radius, n, names=img_paths or None)

    cams = create_cameras(specs, center, args.resx, args.resy)

    apply_standard_material(meshes)
    add_fixed_light(center, radius)

    bg = None if args.no_bg_sample else sample_background_color(args.images)
    configure_world(bg)

    configure_render(args)
    render_all(cams, args.out, args.format)
    print("Blender headless render - completato")


if __name__ == "__main__":
    main()
