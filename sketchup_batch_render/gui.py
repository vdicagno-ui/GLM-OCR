"""
SketchUp Batch Render -- GUI (Windows, SketchUp 2017)

Carica un file .skp in SketchUp 2017, applica 9 posizioni di camera/luci/ombre
lette da 9 file JSON, scatta una foto .bmp per ciascuna posizione e le unisce
in un'unica immagine 3x3 (ordine progressivo 1..9, da sinistra a destra e
dall'alto verso il basso).

Avvio da sorgente:   python gui.py
Eseguibile:          vedi build.bat (crea SketchUpBatchRender.exe con PyInstaller)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import threading
import subprocess
import tempfile
import queue
import traceback
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from compose import make_montage


# ---------------------------------------------------------------------------
# Percorsi e costanti
# ---------------------------------------------------------------------------

RUNNER_BASENAME = "sketchup_runner.rb"
PLUGIN_TARGET_NAME = "skp_batch_render.rb"

DEFAULT_SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2017\SketchUp.exe"

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080

# timeout complessivo di attesa del rendering (secondi)
RENDER_TIMEOUT = 900  # 15 minuti


def resource_path(name: str) -> str:
    """Percorso di una risorsa allegata, sia da sorgente sia da .exe (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def temp_dir() -> str:
    """Cartella temporanea, coerente con quella usata dallo script Ruby (%TEMP%)."""
    return os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()


def job_file() -> str:
    return os.path.join(temp_dir(), "skp_batch_job.json")


def status_file() -> str:
    return os.path.join(temp_dir(), "skp_batch_status.json")


def log_file() -> str:
    return os.path.join(temp_dir(), "skp_batch_log.txt")


def sketchup_plugins_dir() -> str:
    """Cartella Plugins utente di SketchUp 2017."""
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "SketchUp", "SketchUp 2017", "SketchUp", "Plugins")


def read_runner_source() -> str:
    path = resource_path(RUNNER_BASENAME)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def natural_key(path: str):
    """Chiave per ordinamento 'naturale' (pos2 < pos10)."""
    name = os.path.basename(path)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def is_sketchup_running() -> bool:
    """Vero se un processo SketchUp.exe risulta gia' in esecuzione."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SketchUp.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        return "SketchUp.exe" in out.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Logica di rendering (eseguita in un thread separato)
# ---------------------------------------------------------------------------

class RenderWorker(threading.Thread):
    def __init__(self, params: dict, msg_queue: "queue.Queue"):
        super().__init__(daemon=True)
        self.p = params
        self.q = msg_queue
        self.proc: Optional[subprocess.Popen] = None

    def emit(self, kind: str, text: str = ""):
        self.q.put((kind, text))

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.emit("error", f"{e}\n\n{traceback.format_exc()}")

    def _run(self):
        skp = self.p["skp"]
        json_files = self.p["json_files"]
        outdir = self.p["output_dir"]
        exe = self.p["sketchup_exe"]
        width = self.p["width"]
        height = self.p["height"]
        units = self.p["units"]

        # 1. leggi e valida le 9 posizioni
        self.emit("status", "Lettura dei file JSON...")
        positions = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as f:
                positions.append(json.load(f))

        os.makedirs(outdir, exist_ok=True)

        # 2. installa lo script Ruby nella cartella Plugins di SketchUp
        self.emit("status", "Installazione dello script in SketchUp...")
        plugins = sketchup_plugins_dir()
        os.makedirs(plugins, exist_ok=True)
        with open(os.path.join(plugins, PLUGIN_TARGET_NAME), "w", encoding="utf-8") as f:
            f.write(read_runner_source())

        # 3. pulisci stato/log precedenti ed eventuale job residuo
        for path in (status_file(), log_file(), job_file()):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

        # 4. scrivi il job file letto dallo script Ruby
        job = {
            "skp": os.path.abspath(skp),
            "output_dir": os.path.abspath(outdir),
            "width": width,
            "height": height,
            "units": units,
            "positions": positions,
        }
        with open(job_file(), "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)

        # 5. avvia SketchUp
        self.emit("status", "Avvio di SketchUp 2017...")
        self.proc = subprocess.Popen([exe])

        # 6. attendi il file di stato prodotto dallo script Ruby
        self.emit("status", "Rendering delle 9 posizioni in corso...")
        status = self._wait_for_status(RENDER_TIMEOUT)

        # 7. chiudi SketchUp senza salvare (termina il processo)
        self._terminate_sketchup()

        if status is None:
            raise TimeoutError(
                "Tempo scaduto in attesa del rendering. "
                f"Controlla il log: {log_file()}"
            )
        if status.get("status") != "done":
            raise RuntimeError(
                "SketchUp ha segnalato un errore:\n"
                + str(status.get("message", "errore sconosciuto"))
            )

        outputs = status.get("outputs", [])
        if len(outputs) != len(json_files):
            self.emit(
                "status",
                f"Attenzione: prodotte {len(outputs)} immagini su {len(json_files)}.",
            )

        # 8. componi la griglia 3x3
        self.emit("status", "Composizione dell'immagine 3x3...")
        montage_path = os.path.join(outdir, "montage_3x3.bmp")
        # ordina le uscite per nome per sicurezza (pos_01..pos_09)
        outputs_sorted = sorted(outputs, key=natural_key)
        make_montage(outputs_sorted, montage_path, cols=3, rows=3)

        self.emit("done", montage_path)

    def _wait_for_status(self, timeout: int) -> Optional[dict]:
        deadline = time.time() + timeout
        sf = status_file()
        while time.time() < deadline:
            if os.path.exists(sf):
                # piccola attesa per garantire la scrittura completa
                time.sleep(0.3)
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (OSError, json.JSONDecodeError):
                    time.sleep(0.3)
                    continue
            time.sleep(0.5)
        return None

    def _terminate_sketchup(self):
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Interfaccia grafica
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SketchUp Batch Render - griglia 3x3 (SketchUp 2017)")
        self.geometry("760x640")
        self.minsize(700, 600)

        self.json_files: List[str] = []
        self.queue: "queue.Queue" = queue.Queue()
        self.worker: Optional[RenderWorker] = None

        self._build_ui()
        self.after(150, self._poll_queue)

    # -- costruzione layout --------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # File SKP
        row = ttk.Frame(main)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="File SketchUp (.skp):", width=22).pack(side="left")
        self.skp_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.skp_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Sfoglia...", command=self._pick_skp).pack(side="left", padx=4)

        # JSON list
        jbox = ttk.LabelFrame(main, text="9 file JSON (posizioni 1..9, dall'alto e da sinistra)")
        jbox.pack(fill="both", expand=True, **pad)

        jtop = ttk.Frame(jbox)
        jtop.pack(fill="x", padx=6, pady=4)
        ttk.Button(jtop, text="Aggiungi cartella...", command=self._add_folder).pack(side="left")
        ttk.Button(jtop, text="Aggiungi file...", command=self._add_files).pack(side="left", padx=4)
        ttk.Button(jtop, text="Rimuovi", command=self._remove_selected).pack(side="left")
        ttk.Button(jtop, text="Su", command=lambda: self._move(-1)).pack(side="left", padx=4)
        ttk.Button(jtop, text="Giu", command=lambda: self._move(1)).pack(side="left")
        ttk.Button(jtop, text="Svuota", command=self._clear_list).pack(side="left", padx=4)

        listwrap = ttk.Frame(jbox)
        listwrap.pack(fill="both", expand=True, padx=6, pady=4)
        self.listbox = tk.Listbox(listwrap, height=9, activestyle="dotbox")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(listwrap, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        # Output + opzioni
        row = ttk.Frame(main)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Cartella di output:", width=22).pack(side="left")
        self.out_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Sfoglia...", command=self._pick_out).pack(side="left", padx=4)

        row = ttk.Frame(main)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="SketchUp.exe:", width=22).pack(side="left")
        self.exe_var = tk.StringVar(value=DEFAULT_SKETCHUP_EXE)
        ttk.Entry(row, textvariable=self.exe_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Sfoglia...", command=self._pick_exe).pack(side="left", padx=4)

        row = ttk.Frame(main)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Risoluzione (px):", width=22).pack(side="left")
        self.w_var = tk.StringVar(value=str(DEFAULT_WIDTH))
        self.h_var = tk.StringVar(value=str(DEFAULT_HEIGHT))
        ttk.Entry(row, textvariable=self.w_var, width=8).pack(side="left")
        ttk.Label(row, text="x").pack(side="left", padx=4)
        ttk.Entry(row, textvariable=self.h_var, width=8).pack(side="left")
        ttk.Label(row, text="   Unita' coordinate:").pack(side="left", padx=(12, 4))
        self.units_var = tk.StringVar(value="inch")
        ttk.Combobox(
            row, textvariable=self.units_var, width=8, state="readonly",
            values=["inch", "mm", "cm", "m", "ft"],
        ).pack(side="left")

        # Azione + stato
        row = ttk.Frame(main)
        row.pack(fill="x", **pad)
        self.run_btn = ttk.Button(row, text="Avvia rendering e crea griglia 3x3", command=self._start)
        self.run_btn.pack(side="left")
        self.progress = ttk.Progressbar(row, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(main, textvariable=self.status_var, foreground="#333").pack(fill="x", **pad)

    # -- gestione lista JSON -------------------------------------------------
    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, p in enumerate(self.json_files, start=1):
            self.listbox.insert(tk.END, f"{i:>2}.  {os.path.basename(p)}")

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Cartella con i file JSON")
        if not folder:
            return
        found = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".json")
        ]
        found.sort(key=natural_key)
        self.json_files = found
        self._refresh_list()
        if len(found) != 9:
            messagebox.showwarning(
                "Attenzione",
                f"Trovati {len(found)} file JSON nella cartella (attesi 9).\n"
                "Puoi aggiungere/rimuovere file e riordinarli manualmente.",
            )

    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="Seleziona i file JSON",
            filetypes=[("JSON", "*.json"), ("Tutti", "*.*")],
        )
        for f in files:
            if f not in self.json_files:
                self.json_files.append(f)
        self._refresh_list()

    def _remove_selected(self):
        sel = list(self.listbox.curselection())
        for idx in reversed(sel):
            del self.json_files[idx]
        self._refresh_list()

    def _clear_list(self):
        self.json_files = []
        self._refresh_list()

    def _move(self, delta: int):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        j = i + delta
        if 0 <= j < len(self.json_files):
            self.json_files[i], self.json_files[j] = self.json_files[j], self.json_files[i]
            self._refresh_list()
            self.listbox.selection_set(j)

    # -- selezione percorsi --------------------------------------------------
    def _pick_skp(self):
        f = filedialog.askopenfilename(
            title="File SketchUp", filetypes=[("SketchUp", "*.skp"), ("Tutti", "*.*")]
        )
        if f:
            self.skp_var.set(f)
            if not self.out_var.get():
                self.out_var.set(os.path.join(os.path.dirname(f), "render_output"))

    def _pick_out(self):
        d = filedialog.askdirectory(title="Cartella di output")
        if d:
            self.out_var.set(d)

    def _pick_exe(self):
        f = filedialog.askopenfilename(
            title="SketchUp.exe", filetypes=[("Eseguibile", "*.exe"), ("Tutti", "*.*")]
        )
        if f:
            self.exe_var.set(f)

    # -- avvio ---------------------------------------------------------------
    def _validate(self) -> Optional[dict]:
        skp = self.skp_var.get().strip()
        if not skp or not os.path.isfile(skp):
            messagebox.showerror("Errore", "Seleziona un file .skp valido.")
            return None
        if len(self.json_files) != 9:
            messagebox.showerror(
                "Errore", f"Servono esattamente 9 file JSON (selezionati: {len(self.json_files)})."
            )
            return None
        for jf in self.json_files:
            if not os.path.isfile(jf):
                messagebox.showerror("Errore", f"File JSON non trovato:\n{jf}")
                return None
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception as e:
                messagebox.showerror("Errore", f"JSON non valido:\n{jf}\n\n{e}")
                return None
        outdir = self.out_var.get().strip()
        if not outdir:
            messagebox.showerror("Errore", "Indica una cartella di output.")
            return None
        exe = self.exe_var.get().strip()
        if not os.path.isfile(exe):
            messagebox.showerror(
                "Errore", f"SketchUp.exe non trovato:\n{exe}"
            )
            return None
        try:
            width = int(self.w_var.get())
            height = int(self.h_var.get())
            if width <= 0 or height <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Errore", "Risoluzione non valida.")
            return None

        return {
            "skp": skp,
            "json_files": list(self.json_files),
            "output_dir": outdir,
            "sketchup_exe": exe,
            "width": width,
            "height": height,
            "units": self.units_var.get(),
        }

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        params = self._validate()
        if not params:
            return

        if is_sketchup_running():
            if not messagebox.askyesno(
                "SketchUp gia' aperto",
                "Sembra che SketchUp sia gia' in esecuzione.\n"
                "Per evitare conflitti conviene chiuderlo prima.\n\n"
                "Vuoi continuare comunque?",
            ):
                return

        self.run_btn.config(state="disabled")
        self.progress.start(12)
        self.worker = RenderWorker(params, self.queue)
        self.worker.start()

    # -- ciclo messaggi dal thread -------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                kind, text = self.queue.get_nowait()
                if kind == "status":
                    self.status_var.set(text)
                elif kind == "done":
                    self._finish_ok(text)
                elif kind == "error":
                    self._finish_err(text)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _finish_ok(self, montage_path: str):
        self.progress.stop()
        self.run_btn.config(state="normal")
        self.status_var.set(f"Completato: {montage_path}")
        if messagebox.askyesno(
            "Fatto",
            f"Immagine 3x3 creata:\n{montage_path}\n\nAprire la cartella di output?",
        ):
            try:
                os.startfile(os.path.dirname(montage_path))  # type: ignore[attr-defined]
            except Exception:
                pass

    def _finish_err(self, msg: str):
        self.progress.stop()
        self.run_btn.config(state="normal")
        self.status_var.set("Errore durante l'elaborazione.")
        messagebox.showerror("Errore", msg)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
