"""
3D Style & Camera Replicator - GUI Tkinter.

Pipeline (Windows, con Python gia' installato):

    Foto (bmp/png)  --[Meshroom SfM]-->  pose camera (cameras.sfm)
                                              |
    Nuovo oggetto .obj  -------------------[Blender headless]--> nuovo set immagini

Estende lo script originale dell'utente (PhotoAlignmentApp). Alla pressione del
pulsante avvia processi in background (subprocess):

  Stadio 1 (opzionale, default ON): meshroom_batch stima le coordinate della
           camera di ogni foto (Structure-from-Motion) e produce un cameras.sfm.
  Stadio 2: Blender carica il nuovo .obj, ricrea quelle camere (posa + focale +
           risoluzione), applica materiale standard + luce fissa + sfondo
           campionato dalle foto, e renderizza il nuovo set di immagini.

Se l'utente fornisce direttamente un .sfm esistente, Meshroom viene saltato.
Se non c'e' ne' Meshroom ne' .sfm, Blender simula le camere su un anello.

Pensato per essere impacchettato in un .exe con PyInstaller (vedi gui.spec).
"""

import glob
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox


# ---------------------------------------------------------------------------
# Utilita'
# ---------------------------------------------------------------------------

def resource_path(relative: str) -> str:
    """Percorso assoluto di una risorsa, compatibile con PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def default_blender_path() -> str:
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    root = os.path.join(program_files, "Blender Foundation")
    if os.path.isdir(root):
        for name in sorted(os.listdir(root), reverse=True):
            exe = os.path.join(root, name, "blender.exe")
            if os.path.isfile(exe):
                return exe
    return ""


def default_meshroom_batch() -> str:
    """Cerca meshroom_batch.exe in percorsi tipici su Windows."""
    candidates = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 r"C:\\"):
        if base and os.path.isdir(base):
            candidates += glob.glob(os.path.join(base, "Meshroom*", "meshroom_batch.exe"))
            candidates += glob.glob(os.path.join(base, "Meshroom*", "*", "meshroom_batch.exe"))
    return candidates[0] if candidates else ""


def resolve_meshroom_batch(path: str) -> str:
    """Accetta sia il file meshroom_batch.exe sia la cartella che lo contiene."""
    if not path:
        return ""
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        cand = os.path.join(path, "meshroom_batch.exe")
        if os.path.isfile(cand):
            return cand
        hits = glob.glob(os.path.join(path, "**", "meshroom_batch.exe"), recursive=True)
        if hits:
            return hits[0]
    return ""


def find_sfm(search_dirs):
    """Cerca ricorsivamente un cameras.sfm (o *.sfm) nelle cartelle date."""
    best = ""
    best_mtime = -1.0
    for d in search_dirs:
        if not d or not os.path.isdir(d):
            continue
        hits = glob.glob(os.path.join(d, "**", "cameras.sfm"), recursive=True)
        if not hits:
            hits = glob.glob(os.path.join(d, "**", "*.sfm"), recursive=True)
        for h in hits:
            try:
                m = os.path.getmtime(h)
            except OSError:
                continue
            if m > best_mtime:
                best, best_mtime = h, m
    return best


# ---------------------------------------------------------------------------
# Applicazione
# ---------------------------------------------------------------------------

class PhotoAlignmentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("3D Camera Matchmover & Renderer")
        self.root.geometry("720x760")
        self.root.configure(bg="#2b2b2b")

        self.title_label = tk.Label(root, text="3D Style & Camera Replicator", font=("Helvetica", 16, "bold"), fg="#ffffff", bg="#2b2b2b")
        self.title_label.pack(pady=(16, 8))

        # Variabili di percorso
        self.img_dir = tk.StringVar()
        self.obj_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.blender_path = tk.StringVar(value=default_blender_path())
        self.meshroom_path = tk.StringVar(value=default_meshroom_batch())
        self.sfm_path = tk.StringVar()
        self.use_meshroom = tk.BooleanVar(value=True)

        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._worker = None
        self._process = None
        self._cancel = False

        # Selettori
        self.create_path_selector("1. Cartella Immagini Originali (BMP/PNG):", self.img_dir, select_folder=True)
        self.create_path_selector("2. Nuovo Oggetto 3D (.OBJ):", self.obj_path, select_folder=False, file_type=[("Wavefront OBJ", "*.obj")])
        self.create_path_selector("3. Cartella di Output Render:", self.output_dir, select_folder=True)
        self.create_path_selector("4. Eseguibile Blender (blender.exe):", self.blender_path, select_folder=False, file_type=[("Blender", "blender.exe"), ("Tutti i file", "*.*")])
        self.create_path_selector("5. Meshroom (cartella o meshroom_batch.exe):", self.meshroom_path, select_folder=False, file_type=[("Meshroom batch", "meshroom_batch.exe"), ("Tutti i file", "*.*")])
        self.create_path_selector("6. (Opz.) File pose gia' calcolato (.sfm):", self.sfm_path, select_folder=False, file_type=[("AliceVision SfM", "*.sfm *.json"), ("COLMAP", "images.txt"), ("Tutti i file", "*.*")])

        # Checkbox Meshroom
        chk = tk.Checkbutton(root, text="Calcola le pose camera con Meshroom (deseleziona se usi il file al punto 6)",
                             variable=self.use_meshroom, fg="#dddddd", bg="#2b2b2b",
                             activebackground="#2b2b2b", activeforeground="#ffffff",
                             selectcolor="#2b2b2b", anchor="w")
        chk.pack(fill="x", padx=30)

        # Pulsanti
        btns = tk.Frame(root, bg="#2b2b2b")
        btns.pack(pady=(14, 8))
        self.run_btn = tk.Button(btns, text="AVVIA REPLICAZIONE STILE", font=("Helvetica", 12, "bold"), bg="#007acc", fg="#ffffff", padx=20, pady=10, command=self.process_pipeline)
        self.run_btn.pack(side="left")
        self.cancel_btn = tk.Button(btns, text="Interrompi", bg="#7a2b2b", fg="#ffffff", padx=12, pady=10, state="disabled", command=self._on_cancel)
        self.cancel_btn.pack(side="left", padx=8)

        # Log
        log_frame = tk.Frame(root, bg="#2b2b2b")
        log_frame.pack(fill="both", expand=True, padx=30, pady=(4, 18))
        tk.Label(log_frame, text="Log:", fg="#aaaaaa", bg="#2b2b2b", anchor="w").pack(fill="x")
        self.log_text = tk.Text(log_frame, height=12, bg="#1e1e1e", fg="#d4d4d4", insertbackground="white", wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

        self.root.after(100, self._drain_log_queue)

    def create_path_selector(self, label_text, text_var, select_folder=False, file_type=None):
        frame = tk.Frame(self.root, bg="#2b2b2b")
        frame.pack(fill="x", padx=30, pady=5)

        tk.Label(frame, text=label_text, fg="#aaaaaa", bg="#2b2b2b", anchor="w").pack(fill="x")

        entry = tk.Entry(frame, textvariable=text_var, bg="#3c3f41", fg="#ffffff", insertbackground="white")
        entry.pack(side="left", fill="x", expand=True, ipady=4, pady=2)

        def browse():
            if select_folder:
                path = filedialog.askdirectory()
            else:
                path = filedialog.askopenfilename(filetypes=file_type)
            if path:
                text_var.set(path)
                if text_var is self.obj_path and not self.output_dir.get():
                    self.output_dir.set(os.path.join(os.path.dirname(path), "render_output"))

        tk.Button(frame, text="Sfoglia...", bg="#4b4b4b", fg="#ffffff", command=browse).pack(side="right", padx=(5, 0))

    # ------------------------------------------------------------- logging --
    def _log(self, text: str):
        self._log_queue.put(text)

    def _drain_log_queue(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line)
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    # ------------------------------------------------------------- pipeline --
    def process_pipeline(self):
        if not self.img_dir.get() or not self.obj_path.get() or not self.output_dir.get():
            messagebox.showerror("Errore", "Compila i campi 1, 2 e 3 (immagini, oggetto, output).")
            return
        if not os.path.isdir(self.img_dir.get()):
            messagebox.showerror("Errore", "La cartella immagini non esiste.")
            return
        if not os.path.isfile(self.obj_path.get()):
            messagebox.showerror("Errore", "Il file .obj selezionato non esiste.")
            return

        blender = self.blender_path.get().strip()
        if not blender or not os.path.isfile(blender):
            messagebox.showerror("Errore", "Percorso di blender.exe non valido (campo 4).")
            return

        # Meshroom richiesto solo se attivo e senza .sfm gia' fornito.
        self._resolved_meshroom = ""
        if self.use_meshroom.get() and not self.sfm_path.get().strip():
            mb = resolve_meshroom_batch(self.meshroom_path.get().strip())
            if not mb:
                if not messagebox.askyesno(
                    "Meshroom non trovato",
                    "meshroom_batch.exe non trovato (campo 5).\n\n"
                    "Vuoi proseguire senza fotogrammetria? Le camere verranno SIMULATE "
                    "su un anello attorno all'oggetto.",
                ):
                    return
            self._resolved_meshroom = mb

        if self._worker and self._worker.is_alive():
            messagebox.showinfo("In corso", "Un'elaborazione e' gia' in esecuzione.")
            return

        os.makedirs(self.output_dir.get(), exist_ok=True)
        self._cancel = False
        self.run_btn.configure(state="disabled", text="ELABORAZIONE IN CORSO...")
        self.cancel_btn.configure(state="normal")

        self._worker = threading.Thread(target=self._run_pipeline, daemon=True)
        self._worker.start()

    # ------------------------------------------------------- subprocess run --
    def _run_process(self, cmd) -> int:
        """Esegue un comando streammando l'output nel log. Ritorna il codice."""
        self._log(">> " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n\n")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, creationflags=creationflags,
            )
        except Exception as exc:  # pragma: no cover
            self._log(f"!! Impossibile avviare il processo: {exc}\n")
            return -1
        for line in self._process.stdout:
            if self._cancel:
                self._process.terminate()
                self._log("\n>> Interruzione richiesta dall'utente.\n")
                break
            self._log(line)
        code = self._process.wait()
        self._process = None
        return code

    def _run_pipeline(self):
        try:
            sfm = self.sfm_path.get().strip()

            # -------- Stadio 1: Meshroom (se necessario) --------
            if not sfm and self._resolved_meshroom and self.use_meshroom.get():
                self._log("=== STADIO 1/2: Meshroom (Structure-from-Motion) ===\n")
                mesh_out = os.path.join(self.output_dir.get(), "meshroom", "sfm")
                mesh_cache = os.path.join(self.output_dir.get(), "meshroom", "cache")
                os.makedirs(mesh_out, exist_ok=True)
                os.makedirs(mesh_cache, exist_ok=True)
                cmd = [
                    self._resolved_meshroom,
                    "--input", self.img_dir.get().strip(),
                    "--pipeline", "photogrammetry",
                    "--toNode", "StructureFromMotion",
                    "--output", mesh_out,
                    "--cache", mesh_cache,
                ]
                code = self._run_process(cmd)
                if self._cancel:
                    return self._finish(success=False)
                # Anche con exit != 0 il cameras.sfm potrebbe esistere: cerchiamo.
                sfm = find_sfm([mesh_out, mesh_cache])
                if sfm:
                    self._log(f"\n>> Pose trovate: {sfm}\n\n")
                else:
                    self._log(f"\n!! Meshroom terminato (codice {code}) ma nessun .sfm trovato.\n"
                              ">> Proseguo con camere SIMULATE.\n\n")

            elif sfm:
                self._log(f"=== Uso file pose fornito: {sfm} ===\n\n")
            else:
                self._log("=== Nessuna fotogrammetria: camere SIMULATE ===\n\n")

            # -------- Stadio 2: Blender --------
            self._log("=== STADIO 2/2: Blender (render del nuovo oggetto) ===\n")
            cmd = self._build_blender_command(sfm)
            code = self._run_process(cmd)
            if self._cancel:
                return self._finish(success=False)
            self._log(f"\n>> Blender terminato con codice {code}.\n")
            self._finish(success=(code == 0))
        except Exception as exc:  # pragma: no cover
            self._log(f"!! Errore nel pipeline: {exc}\n")
            self._finish(success=False)

    def _build_blender_command(self, sfm):
        render_script = resource_path("blender_render.py")
        cmd = [
            self.blender_path.get().strip(),
            "--background", "--factory-startup",
            "--python", render_script,
            "--",
            "--obj", self.obj_path.get().strip(),
            "--out", self.output_dir.get().strip(),
            "--images", self.img_dir.get().strip(),
        ]
        if sfm:
            cmd += ["--sfm", sfm]
        return cmd

    def _finish(self, success):
        def _ui():
            self.run_btn.configure(state="normal", text="AVVIA REPLICAZIONE STILE")
            self.cancel_btn.configure(state="disabled")
            if success:
                messagebox.showinfo("Fatto", "Nuovo set di immagini generato.\nControlla la cartella di output.")
            elif self._cancel:
                messagebox.showinfo("Interrotto", "Elaborazione interrotta.")
            else:
                messagebox.showwarning("Attenzione", "L'elaborazione ha restituito un errore. Controlla il log.")
        self.root.after(0, _ui)

    def _on_cancel(self):
        self._cancel = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoAlignmentApp(root)
    root.mainloop()
