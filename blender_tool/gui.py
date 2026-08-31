"""
3D Style & Camera Replicator - GUI Tkinter.

Estende lo script originale dell'utente (PhotoAlignmentApp): alla pressione del
pulsante viene avviato un processo in background (subprocess) che esegue Blender
in modalita' headless passandogli lo script custom ``blender_render.py``.

Lo script Blender:
    1. Carica il file .obj selezionato.
    2. Configura una serie di telecamere basate sulle coordinate estratte dalle
       foto (legge un log di fotogrammetria oppure simula le coordinate).
    3. Imposta un materiale standard e una luce fissa (ombre/stile ripetibili).
    4. Renderizza i frame salvandoli nella cartella di output.

Il file e' pensato per essere impacchettato in un .exe con PyInstaller
(vedi ``gui.spec`` e il README).
"""

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
    """Percorso assoluto di una risorsa, compatibile con PyInstaller.

    Quando l'app e' impacchettata, i file aggiunti vengono estratti in
    ``sys._MEIPASS``; in esecuzione normale si usa la cartella dello script.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def default_blender_path() -> str:
    """Prova a individuare blender.exe su Windows (versione piu' recente)."""
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    blender_root = os.path.join(program_files, "Blender Foundation")
    if os.path.isdir(blender_root):
        for name in sorted(os.listdir(blender_root), reverse=True):
            exe = os.path.join(blender_root, name, "blender.exe")
            if os.path.isfile(exe):
                return exe
    return ""


class PhotoAlignmentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("3D Camera Matchmover & Renderer")
        self.root.geometry("640x640")
        self.root.configure(bg="#2b2b2b")

        # Titolo
        self.title_label = tk.Label(root, text="3D Style & Camera Replicator", font=("Helvetica", 16, "bold"), fg="#ffffff", bg="#2b2b2b")
        self.title_label.pack(pady=20)

        # Variabili di percorso
        self.img_dir = tk.StringVar()
        self.obj_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.blender_path = tk.StringVar(value=default_blender_path())

        # Coda log + stato del processo in background
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._worker = None
        self._process = None

        # Frame per i controlli
        self.create_path_selector("1. Cartella Immagini Originali (BMP/PNG):", self.img_dir, select_folder=True)
        self.create_path_selector("2. Nuovo Oggetto 3D (.OBJ):", self.obj_path, select_folder=False, file_type=[("Wavefront OBJ", "*.obj")])
        self.create_path_selector("3. Cartella di Output Render:", self.output_dir, select_folder=True)
        self.create_path_selector("4. Eseguibile Blender (blender.exe):", self.blender_path, select_folder=False, file_type=[("Blender", "blender.exe"), ("Tutti i file", "*.*")])

        # Pulsante di Elaborazione
        self.run_btn = tk.Button(root, text="AVVIA REPLICAZIONE STILE", font=("Helvetica", 12, "bold"), bg="#007acc", fg="#ffffff", padx=20, pady=10, command=self.process_pipeline)
        self.run_btn.pack(pady=(20, 10))

        # Pannello di log in tempo reale
        log_frame = tk.Frame(root, bg="#2b2b2b")
        log_frame.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        tk.Label(log_frame, text="Log Blender:", fg="#aaaaaa", bg="#2b2b2b", anchor="w").pack(fill="x")
        self.log_text = tk.Text(log_frame, height=10, bg="#1e1e1e", fg="#d4d4d4", insertbackground="white", wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

        # Poll periodico della coda di log
        self.root.after(100, self._drain_log_queue)

    def create_path_selector(self, label_text, text_var, select_folder=False, file_type=None):
        frame = tk.Frame(self.root, bg="#2b2b2b")
        frame.pack(fill="x", padx=30, pady=8)

        lbl = tk.Label(frame, text=label_text, fg="#aaaaaa", bg="#2b2b2b", anchor="w")
        lbl.pack(fill="x")

        entry = tk.Entry(frame, textvariable=text_var, bg="#3c3f41", fg="#ffffff", insertbackground="white")
        entry.pack(side="left", fill="x", expand=True, ipady=4, pady=2)

        def browse():
            if select_folder:
                path = filedialog.askdirectory()
            else:
                path = filedialog.askopenfilename(filetypes=file_type)
            if path:
                text_var.set(path)
                # Suggerisci una cartella output accanto all'obj
                if text_var is self.obj_path and not self.output_dir.get():
                    self.output_dir.set(os.path.join(os.path.dirname(path), "render_output"))

        btn = tk.Button(frame, text="Sfoglia...", bg="#4b4b4b", fg="#ffffff", command=browse)
        btn.pack(side="right", padx=(5, 0))

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
            messagebox.showerror("Errore", "Per favore, compila tutti i campi richiesti.")
            return

        blender = self.blender_path.get().strip()
        if not blender or not os.path.isfile(blender):
            messagebox.showerror("Errore", "Percorso di blender.exe non valido. Selezionalo nel campo 4.")
            return
        if not os.path.isfile(self.obj_path.get()):
            messagebox.showerror("Errore", "Il file .obj selezionato non esiste.")
            return

        if self._worker and self._worker.is_alive():
            messagebox.showinfo("In corso", "Un rendering e' gia' in esecuzione.")
            return

        os.makedirs(self.output_dir.get(), exist_ok=True)

        self.run_btn.configure(state="disabled", text="ELABORAZIONE IN CORSO...")
        self._log(">> Avvio pipeline di replicazione stile...\n")
        self._log(f"   Immagini : {self.img_dir.get()}\n")
        self._log(f"   Oggetto  : {self.obj_path.get()}\n")
        self._log(f"   Output   : {self.output_dir.get()}\n\n")

        self._worker = threading.Thread(target=self._run_blender, daemon=True)
        self._worker.start()

    def _build_command(self):
        """Riga di comando per lanciare Blender headless con lo script custom."""
        render_script = resource_path("blender_render.py")
        cmd = [
            self.blender_path.get().strip(),
            "--background",          # nessuna interfaccia grafica
            "--factory-startup",     # ignora addon/preferenze utente
            "--python", render_script,
            "--",                    # gli argomenti successivi vanno allo script
            "--obj", self.obj_path.get().strip(),
            "--out", self.output_dir.get().strip(),
            "--images", self.img_dir.get().strip(),
        ]
        return cmd

    def _run_blender(self):
        cmd = self._build_command()
        self._log(">> Comando:\n   " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n\n")

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:  # pragma: no cover
            self._log(f"!! Impossibile avviare Blender: {exc}\n")
            self._finish(success=False)
            return

        for line in self._process.stdout:
            self._log(line)

        code = self._process.wait()
        self._log(f"\n>> Blender terminato con codice {code}.\n")
        self._finish(success=(code == 0))

    def _finish(self, success):
        def _ui():
            self.run_btn.configure(state="normal", text="AVVIA REPLICAZIONE STILE")
            self._process = None
            if success:
                messagebox.showinfo("Fatto", "Rendering completato.\nControlla la cartella di output.")
            else:
                messagebox.showwarning("Attenzione", "Blender ha restituito un errore. Controlla il log.")
        self.root.after(0, _ui)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoAlignmentApp(root)
    root.mainloop()
