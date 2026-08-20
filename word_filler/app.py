"""Compilatore di template Word — applicazione desktop offline.

Interfaccia grafica (tkinter) che:
  1. carica un template Word con segnaposto (etichette "da compilare …");
  2. carica uno o più file guida;
  3. estrae i dati da OGNI file guida (con AI locale LM Studio/Ollama, oppure
     con un'euristica offline) — ciascun output usa i dati di UN SOLO file;
  4. permette di rivedere/correggere i valori estratti;
  5. genera un documento Word compilato per ogni file guida.

Tutto funziona in locale: nessun dato lascia il computer.
"""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Import the core package so it works in every launch mode:
#  * "python app.py"          -> the script dir is on sys.path, "core" imports
#  * a PyInstaller .exe        -> the bundle root is on sys.path, "core" imports
#  * "python -m word_filler.app" (from repo root) -> relative import works
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

try:
    from core import config, extractor, pipeline, template
except ImportError:  # pragma: no cover - package-style execution
    from word_filler.core import config, extractor, pipeline, template


APP_TITLE = "Compilatore Template Word — Offline"


class WordFillerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1024x760")
        self.root.minsize(900, 640)

        self.cfg = config.load_config()

        # State -------------------------------------------------------------
        self.template_path: str | None = None
        self.guide_paths: list[str] = []
        self.fields: list[str] = []
        # {guide_path: {field: value}}
        self.extracted: dict[str, dict[str, str]] = {}
        # {guide_path: {field: Entry widget}} for the review area
        self._review_entries: dict[str, dict[str, tk.Entry]] = {}

        self._msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self._busy = False

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        self.tab_setup = ttk.Frame(notebook, padding=10)
        self.tab_review = ttk.Frame(notebook, padding=10)
        notebook.add(self.tab_setup, text="  1 · Configurazione  ")
        notebook.add(self.tab_review, text="  2 · Revisione e generazione  ")
        self.notebook = notebook

        # Fixed action bar at the bottom of the setup tab: the primary button
        # stays visible even if the form above is scrolled.
        setup_bar = ttk.Frame(self.tab_setup, padding=(0, 6, 0, 0))
        setup_bar.pack(side="bottom", fill="x")
        self.extract_btn = ttk.Button(
            setup_bar, text="▶  Estrai dati dai file guida", command=self._start_extraction
        )
        self.extract_btn.pack(side="right")
        self.setup_hint = ttk.Label(
            setup_bar, text="Compila i campi qui sopra, poi premi «Estrai dati».",
            foreground="#555",
        )
        self.setup_hint.pack(side="left")

        # The setup tab holds a lot of content: make it scrollable so nothing
        # is ever clipped off the bottom.
        setup_inner = self._make_scrollable(self.tab_setup)
        self._build_setup_tab(setup_inner)
        self._build_review_tab(self.tab_review)

        # Log ---------------------------------------------------------------
        log_frame = ttk.LabelFrame(outer, text="Registro attività", padding=6)
        log_frame.pack(fill="x", pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=6, wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _make_scrollable(self, parent):
        """Wrap ``parent`` with a vertical scrollbar; return the inner frame
        into which content should be packed."""
        canvas = tk.Canvas(parent, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(parent, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll.set)

        inner = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window, width=e.width),
        )

        # Mouse-wheel scrolling while the pointer is over the canvas.
        def _on_wheel(event):
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
            if getattr(event, "num", None) == 4:  # Linux scroll up
                delta = -1
            elif getattr(event, "num", None) == 5:  # Linux scroll down
                delta = 1
            canvas.yview_scroll(delta, "units")

        def _bind_wheel(_):
            canvas.bind_all("<MouseWheel>", _on_wheel)
            canvas.bind_all("<Button-4>", _on_wheel)
            canvas.bind_all("<Button-5>", _on_wheel)

        def _unbind_wheel(_):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)
        return inner

    def _build_setup_tab(self, parent):
        # --- Template ------------------------------------------------------
        tpl = ttk.LabelFrame(parent, text="Template Word (.docx)", padding=8)
        tpl.pack(fill="x")
        self.template_var = tk.StringVar()
        ttk.Entry(tpl, textvariable=self.template_var).pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        ttk.Button(tpl, text="Sfoglia…", command=self._choose_template).pack(side="left")

        # --- Placeholder preset -------------------------------------------
        ph = ttk.LabelFrame(parent, text="Riconoscimento segnaposto", padding=8)
        ph.pack(fill="x", pady=(8, 0))

        ttk.Label(ph, text="Formato etichette:").grid(row=0, column=0, sticky="w")
        self.preset_var = tk.StringVar(value=self.cfg.get("preset", template.DEFAULT_PRESET))
        preset_combo = ttk.Combobox(
            ph, textvariable=self.preset_var, state="readonly",
            values=list(template.PRESETS.keys()), width=34,
        )
        preset_combo.grid(row=0, column=1, sticky="w", padx=6)

        self.use_custom_regex_var = tk.BooleanVar(value=self.cfg.get("use_custom_regex", False))
        ttk.Checkbutton(
            ph, text="Usa espressione regolare personalizzata",
            variable=self.use_custom_regex_var, command=self._toggle_regex,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.custom_regex_var = tk.StringVar(value=self.cfg.get("custom_regex", ""))
        self.custom_regex_entry = ttk.Entry(ph, textvariable=self.custom_regex_var, width=60)
        self.custom_regex_entry.grid(row=2, column=0, columnspan=2, sticky="we", pady=(4, 0))
        ttk.Label(
            ph, text="(il gruppo 1 deve catturare il nome del campo)",
            foreground="#666",
        ).grid(row=3, column=0, columnspan=2, sticky="w")
        ph.columnconfigure(1, weight=1)

        ttk.Button(parent, text="🔍  Analizza template", command=self._analyze_template).pack(
            anchor="w", pady=(8, 0)
        )
        self.fields_label = ttk.Label(parent, text="Nessun campo rilevato.", foreground="#444")
        self.fields_label.pack(anchor="w", pady=(4, 0))

        # --- Guide files ---------------------------------------------------
        gf = ttk.LabelFrame(parent, text="File guida (uno o più) — un output per file", padding=8)
        gf.pack(fill="both", expand=True, pady=(8, 0))

        list_wrap = ttk.Frame(gf)
        list_wrap.pack(fill="both", expand=True)
        self.guides_list = tk.Listbox(list_wrap, selectmode="extended", height=6)
        self.guides_list.pack(side="left", fill="both", expand=True)
        gl_scroll = ttk.Scrollbar(list_wrap, command=self.guides_list.yview)
        gl_scroll.pack(side="right", fill="y")
        self.guides_list.configure(yscrollcommand=gl_scroll.set)

        gbtns = ttk.Frame(gf)
        gbtns.pack(fill="x", pady=(6, 0))
        ttk.Button(gbtns, text="Aggiungi…", command=self._add_guides).pack(side="left")
        ttk.Button(gbtns, text="Rimuovi selezionati", command=self._remove_guides).pack(side="left", padx=6)
        ttk.Button(gbtns, text="Svuota", command=self._clear_guides).pack(side="left")

        self.first_page_only_var = tk.BooleanVar(value=self.cfg.get("first_page_only", True))
        ttk.Checkbutton(
            gf,
            text="Leggi solo la prima pagina del file guida (consigliato per documenti lunghi)",
            variable=self.first_page_only_var,
        ).pack(anchor="w", pady=(6, 0))

        # --- Output --------------------------------------------------------
        out = ttk.LabelFrame(parent, text="Output", padding=8)
        out.pack(fill="x", pady=(8, 0))
        ttk.Label(out, text="Cartella (vuoto = accanto al file guida):").grid(row=0, column=0, sticky="w")
        self.output_dir_var = tk.StringVar(value=self.cfg.get("output_dir", ""))
        ttk.Entry(out, textvariable=self.output_dir_var).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(out, text="Sfoglia…", command=self._choose_output_dir).grid(row=0, column=2)
        ttk.Label(out, text="Suffisso nome file:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.suffix_var = tk.StringVar(value=self.cfg.get("output_suffix", "_compilato"))
        ttk.Entry(out, textvariable=self.suffix_var, width=24).grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        out.columnconfigure(1, weight=1)

        # --- AI settings ---------------------------------------------------
        ai = ttk.LabelFrame(parent, text="AI locale (LM Studio / Ollama)", padding=8)
        ai.pack(fill="x", pady=(8, 0))

        self.use_ai_var = tk.BooleanVar(value=self.cfg.get("use_ai", True))
        ttk.Checkbutton(
            ai, text="Usa AI locale per l'estrazione (consigliato)",
            variable=self.use_ai_var,
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(ai, text="Endpoint:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.endpoint_var = tk.StringVar(value=self.cfg.get("endpoint", "http://localhost:1234/v1"))
        endpoint_combo = ttk.Combobox(
            ai, textvariable=self.endpoint_var,
            values=list(extractor.DEFAULT_ENDPOINTS.values()), width=40,
        )
        endpoint_combo.grid(row=1, column=1, sticky="we", padx=6, pady=(6, 0))
        ttk.Button(ai, text="Prova connessione", command=self._test_connection).grid(row=1, column=2, pady=(6, 0))

        ttk.Label(ai, text="Modello:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.model_var = tk.StringVar(value=self.cfg.get("model", ""))
        self.model_combo = ttk.Combobox(ai, textvariable=self.model_var, width=40)
        self.model_combo.grid(row=2, column=1, sticky="we", padx=6, pady=(6, 0))
        ttk.Label(
            ai, text="(vuoto = modello attualmente caricato)", foreground="#666",
        ).grid(row=2, column=2, sticky="w", pady=(6, 0))

        self.ai_status = ttk.Label(ai, text="", foreground="#444")
        self.ai_status.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ai.columnconfigure(1, weight=1)

        self._toggle_regex()

    def _build_review_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x")
        ttk.Label(top, text="File guida:").pack(side="left")
        self.review_guide_var = tk.StringVar()
        self.review_combo = ttk.Combobox(
            top, textvariable=self.review_guide_var, state="readonly", width=60
        )
        self.review_combo.pack(side="left", padx=6)
        self.review_combo.bind("<<ComboboxSelected>>", lambda e: self._show_review_for_selected())

        ttk.Label(
            parent,
            text="Controlla e correggi i valori estratti, poi genera i documenti.",
            foreground="#444",
        ).pack(anchor="w", pady=(6, 4))

        # Scrollable area of field/value entries.
        canvas_wrap = ttk.Frame(parent)
        canvas_wrap.pack(fill="both", expand=True)
        self.review_canvas = tk.Canvas(canvas_wrap, highlightthickness=0)
        self.review_canvas.pack(side="left", fill="both", expand=True)
        rev_scroll = ttk.Scrollbar(canvas_wrap, command=self.review_canvas.yview)
        rev_scroll.pack(side="right", fill="y")
        self.review_canvas.configure(yscrollcommand=rev_scroll.set)
        self.review_inner = ttk.Frame(self.review_canvas)
        self._review_window = self.review_canvas.create_window(
            (0, 0), window=self.review_inner, anchor="nw"
        )
        self.review_inner.bind(
            "<Configure>",
            lambda e: self.review_canvas.configure(scrollregion=self.review_canvas.bbox("all")),
        )
        self.review_canvas.bind(
            "<Configure>",
            lambda e: self.review_canvas.itemconfigure(self._review_window, width=e.width),
        )

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(8, 0))
        self.generate_btn = ttk.Button(
            actions, text="💾  Genera tutti i documenti", command=self._start_generation
        )
        self.generate_btn.pack(side="left")
        ttk.Button(actions, text="Apri cartella output", command=self._open_output_dir).pack(side="left", padx=6)

    # ------------------------------------------------------------ file pickers
    def _choose_template(self):
        path = filedialog.askopenfilename(
            title="Seleziona il template Word",
            filetypes=[("Documenti Word", "*.docx"), ("Tutti i file", "*.*")],
        )
        if path:
            self.template_path = path
            self.template_var.set(path)

    def _add_guides(self):
        paths = filedialog.askopenfilenames(
            title="Seleziona uno o più file guida",
            filetypes=[
                ("File guida", "*.docx *.pdf *.txt *.md *.rtf"),
                ("Word", "*.docx"), ("PDF", "*.pdf"),
                ("Testo", "*.txt *.md"), ("Tutti i file", "*.*"),
            ],
        )
        for p in paths:
            if p not in self.guide_paths:
                self.guide_paths.append(p)
                self.guides_list.insert("end", Path(p).name)

    def _remove_guides(self):
        for idx in reversed(self.guides_list.curselection()):
            self.guides_list.delete(idx)
            del self.guide_paths[idx]

    def _clear_guides(self):
        self.guides_list.delete(0, "end")
        self.guide_paths.clear()

    def _choose_output_dir(self):
        path = filedialog.askdirectory(title="Cartella di output")
        if path:
            self.output_dir_var.set(path)

    def _open_output_dir(self):
        import os
        import subprocess
        import sys

        cfg = self._collect_cfg()
        out = cfg.get("output_dir", "").strip()
        if not out and self.guide_paths:
            out = str(Path(self.guide_paths[0]).parent)
        if not out or not Path(out).exists():
            messagebox.showinfo(APP_TITLE, "Nessuna cartella di output disponibile.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(out)  # noqa: S606 - intended on Windows
            elif sys.platform == "darwin":
                subprocess.Popen(["open", out])
            else:
                subprocess.Popen(["xdg-open", out])
        except Exception as exc:
            messagebox.showinfo(APP_TITLE, f"Impossibile aprire la cartella: {exc}")

    # ------------------------------------------------------------- settings
    def _toggle_regex(self):
        state = "normal" if self.use_custom_regex_var.get() else "disabled"
        self.custom_regex_entry.configure(state=state)

    def _collect_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update({
            "endpoint": self.endpoint_var.get().strip(),
            "model": self.model_var.get().strip(),
            "preset": self.preset_var.get(),
            "custom_regex": self.custom_regex_var.get().strip(),
            "use_custom_regex": bool(self.use_custom_regex_var.get()),
            "use_ai": bool(self.use_ai_var.get()),
            "first_page_only": bool(self.first_page_only_var.get()),
            "output_dir": self.output_dir_var.get().strip(),
            "output_suffix": self.suffix_var.get().strip() or "_compilato",
        })
        return cfg

    def _persist(self):
        self.cfg = self._collect_cfg()
        config.save_config(self.cfg)

    # ------------------------------------------------------------- AI test
    def _test_connection(self):
        endpoint = self.endpoint_var.get().strip()
        self.ai_status.configure(text="Connessione in corso…", foreground="#444")
        self.root.update_idletasks()

        def work():
            ok, msg, models = extractor.test_connection(endpoint)
            self._msg_queue.put(("conn_result", ok, msg, models))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------- template scan
    def _analyze_template(self):
        if not self.template_path:
            messagebox.showwarning(APP_TITLE, "Seleziona prima un template Word.")
            return
        cfg = self._collect_cfg()
        try:
            self.fields = pipeline.scan_template_fields(self.template_path, cfg)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Analisi fallita:\n{exc}")
            self._log(f"Errore analisi template: {exc}")
            return

        if not self.fields:
            self.fields_label.configure(
                text="Nessun campo rilevato. Controlla il formato delle etichette.",
                foreground="#a00",
            )
        else:
            preview = ", ".join(self.fields[:8])
            more = "…" if len(self.fields) > 8 else ""
            self.fields_label.configure(
                text=f"{len(self.fields)} campi rilevati: {preview}{more}",
                foreground="#070",
            )
        self._log(f"Template analizzato: {len(self.fields)} campi.")

    # -------------------------------------------------------- extraction
    def _start_extraction(self):
        if self._busy:
            return
        if not self.template_path:
            messagebox.showwarning(APP_TITLE, "Seleziona un template Word.")
            return
        if not self.guide_paths:
            messagebox.showwarning(APP_TITLE, "Aggiungi almeno un file guida.")
            return
        if not self.fields:
            self._analyze_template()
            if not self.fields:
                messagebox.showwarning(
                    APP_TITLE,
                    "Nessun campo rilevato nel template: impossibile procedere.",
                )
                return

        self._persist()
        cfg = self._collect_cfg()
        guides_snapshot = list(self.guide_paths)
        fields_snapshot = list(self.fields)

        self._set_busy(True, self.extract_btn)
        self._log(f"Avvio estrazione su {len(guides_snapshot)} file guida…")

        def work():
            results = {}
            for gp in guides_snapshot:
                self._msg_queue.put(("log", f"  • {Path(gp).name}…"))
                res = pipeline.extract_for_guide(gp, fields_snapshot, cfg)
                results[gp] = res
                if res.error:
                    mode = "AI non riuscita, uso euristica" if res.values else "errore"
                    self._msg_queue.put(("log", f"    {mode}: {res.error}"))
                else:
                    mode = "AI" if res.used_ai else "euristica"
                    self._msg_queue.put(("log", f"    estratto ({mode})."))
            self._msg_queue.put(("extraction_done", results, fields_snapshot))

        threading.Thread(target=work, daemon=True).start()

    def _on_extraction_done(self, results: dict, fields: list[str]):
        self.extracted = {gp: res.values for gp, res in results.items()}
        self._set_busy(False, self.extract_btn)
        self._log("Estrazione completata. Passa alla scheda «Revisione».")
        self._populate_review(fields)
        self.notebook.select(self.tab_review)

    # ---------------------------------------------------------- review UI
    def _populate_review(self, fields: list[str]):
        names = [Path(p).name for p in self.guide_paths if p in self.extracted]
        self._review_name_to_path = {
            Path(p).name: p for p in self.guide_paths if p in self.extracted
        }
        self.review_combo.configure(values=names)
        if names:
            self.review_guide_var.set(names[0])
            self._show_review_for_selected()

    def _show_review_for_selected(self):
        name = self.review_guide_var.get()
        path = getattr(self, "_review_name_to_path", {}).get(name)
        if not path:
            return

        for child in self.review_inner.winfo_children():
            child.destroy()

        entries: dict[str, tk.Entry] = {}
        values = self.extracted.get(path, {})
        ttk.Label(self.review_inner, text="Campo", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=4
        )
        ttk.Label(self.review_inner, text="Valore", font=("", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=4, pady=4
        )
        for i, field_name in enumerate(self.fields, start=1):
            ttk.Label(self.review_inner, text=field_name, wraplength=260).grid(
                row=i, column=0, sticky="nw", padx=4, pady=3
            )
            var = tk.StringVar(value=values.get(field_name, ""))
            entry = ttk.Entry(self.review_inner, textvariable=var)
            entry.grid(row=i, column=1, sticky="we", padx=4, pady=3)
            entry._var = var  # keep a reference
            entries[field_name] = entry
        self.review_inner.columnconfigure(1, weight=1)
        self._review_entries[path] = entries

    def _sync_review_entries(self):
        """Copy current entry values back into ``self.extracted``."""
        for path, entries in self._review_entries.items():
            store = self.extracted.setdefault(path, {})
            for field_name, entry in entries.items():
                store[field_name] = entry.get()

    # -------------------------------------------------------- generation
    def _start_generation(self):
        if self._busy:
            return
        if not self.extracted:
            messagebox.showwarning(APP_TITLE, "Esegui prima l'estrazione dei dati.")
            return
        self._sync_review_entries()
        self._persist()
        cfg = self._collect_cfg()
        template_path = self.template_path
        data_snapshot = {gp: dict(vals) for gp, vals in self.extracted.items()}

        self._set_busy(True, self.generate_btn)
        self._log("Generazione documenti…")

        def work():
            ok, fail = 0, 0
            last_dir = None
            for gp, values in data_snapshot.items():
                try:
                    out = pipeline.generate_output(template_path, values, gp, cfg)
                    last_dir = str(out.parent)
                    ok += 1
                    self._msg_queue.put(("log", f"  ✔ {out.name}"))
                except Exception as exc:
                    fail += 1
                    self._msg_queue.put(("log", f"  ✘ {Path(gp).name}: {exc}"))
            self._msg_queue.put(("generation_done", ok, fail, last_dir))

        threading.Thread(target=work, daemon=True).start()

    def _on_generation_done(self, ok: int, fail: int, last_dir: str | None):
        self._set_busy(False, self.generate_btn)
        msg = f"Generati {ok} documenti."
        if fail:
            msg += f" {fail} non riusciti (vedi registro)."
        self._log(msg)
        messagebox.showinfo(APP_TITLE, msg + (f"\n\nCartella:\n{last_dir}" if last_dir else ""))

    # --------------------------------------------------------------- misc
    def _set_busy(self, busy: bool, *buttons):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.extract_btn, self.generate_btn):
            b.configure(state=state)
        if busy:
            self.root.configure(cursor="watch")
        else:
            self.root.configure(cursor="")

    def _log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1])
                elif kind == "conn_result":
                    _, ok, text, models = msg
                    color = "#070" if ok else "#a00"
                    self.ai_status.configure(text=text, foreground=color)
                    if models:
                        self.model_combo.configure(values=models)
                    self._log(text)
                elif kind == "extraction_done":
                    self._on_extraction_done(msg[1], msg[2])
                elif kind == "generation_done":
                    self._on_generation_done(msg[1], msg[2], msg[3])
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)


def main():
    root = tk.Tk()
    app = WordFillerApp(root)

    def on_close():
        try:
            app._persist()
        except Exception:
            traceback.print_exc()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
