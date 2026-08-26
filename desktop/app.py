"""Estrattore Spese — applicazione desktop (Windows) con interfaccia grafica.

Flusso d'uso:
    1. L'utente sceglie una o più foto (o un'intera cartella).
    2. L'app esegue l'OCR (GLM-OCR via Ollama) su ciascuna foto ed estrae le
       coppie causale/importo, ignorando i totali.
    3. Mostra un'anteprima delle voci aggregate per causale.
    4. Su conferma, scrive/accoda i dati nel file Excel scelto, su 3 colonne:
       Data inserimento | Causale | Valore (negativo).

Avvio:   python app.py
Build:   vedere build.bat (PyInstaller) per generare l'eseguibile .exe
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    Tk,
    StringVar,
    X,
    Y,
    filedialog,
    messagebox,
    ttk,
)

from estrattore_spese.config import Config
from estrattore_spese.ocr_backend import verifica_stato
from estrattore_spese.pipeline import elabora_foto, salva_su_excel

ESTENSIONI_IMMAGINI = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".heic",
)


class App:
    def __init__(self, root: Tk):
        self.root = root
        self.cfg = Config.carica()
        self.percorsi: list[str] = []
        self.ultimo_risultato = None

        root.title("Estrattore Spese — GLM-OCR")
        root.geometry("820x620")
        root.minsize(720, 520)

        self._costruisci_ui()
        self._verifica_stato_async()

    # ------------------------------------------------------------------ UI --
    def _costruisci_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- Riga configurazione OCR ---
        cfg_frame = ttk.LabelFrame(self.root, text="Motore OCR (GLM-OCR / Ollama)")
        cfg_frame.pack(fill=X, padx=10, pady=(10, 4))

        ttk.Label(cfg_frame, text="Endpoint:").grid(row=0, column=0, sticky="w", **pad)
        self.var_url = StringVar(value=self.cfg.ocr_url)
        ttk.Entry(cfg_frame, textvariable=self.var_url, width=32).grid(
            row=0, column=1, sticky="w", **pad
        )
        ttk.Label(cfg_frame, text="Modello:").grid(row=0, column=2, sticky="w", **pad)
        self.var_modello = StringVar(value=self.cfg.modello)
        ttk.Entry(cfg_frame, textvariable=self.var_modello, width=18).grid(
            row=0, column=3, sticky="w", **pad
        )
        self.lbl_stato = ttk.Label(cfg_frame, text="Verifica stato…", foreground="gray")
        self.lbl_stato.grid(row=0, column=4, sticky="w", **pad)

        # --- Selezione foto ---
        sel_frame = ttk.LabelFrame(self.root, text="1. Foto da elaborare")
        sel_frame.pack(fill=X, padx=10, pady=4)

        btns = ttk.Frame(sel_frame)
        btns.pack(fill=X, **pad)
        ttk.Button(btns, text="Aggiungi foto…", command=self._scegli_foto).pack(
            side=LEFT, padx=(0, 6)
        )
        ttk.Button(btns, text="Aggiungi cartella…", command=self._scegli_cartella).pack(
            side=LEFT, padx=6
        )
        ttk.Button(btns, text="Svuota elenco", command=self._svuota).pack(side=LEFT, padx=6)
        self.lbl_conteggio = ttk.Label(btns, text="0 foto selezionate")
        self.lbl_conteggio.pack(side=RIGHT)

        self.lista = ttk.Treeview(sel_frame, columns=("file",), show="headings", height=5)
        self.lista.heading("file", text="File")
        self.lista.pack(fill=X, padx=8, pady=(0, 8))

        # --- File Excel di destinazione ---
        xls_frame = ttk.LabelFrame(self.root, text="2. File Excel di destinazione")
        xls_frame.pack(fill=X, padx=10, pady=4)
        self.var_excel = StringVar(value=self.cfg.ultimo_excel)
        ttk.Entry(xls_frame, textvariable=self.var_excel).pack(
            side=LEFT, fill=X, expand=True, **pad
        )
        ttk.Button(xls_frame, text="Sfoglia…", command=self._scegli_excel).pack(
            side=LEFT, **pad
        )

        # --- Azioni ---
        act_frame = ttk.Frame(self.root)
        act_frame.pack(fill=X, padx=10, pady=6)
        self.btn_elabora = ttk.Button(
            act_frame, text="▶ Elabora foto", command=self._avvia_elaborazione
        )
        self.btn_elabora.pack(side=LEFT)
        self.btn_salva = ttk.Button(
            act_frame, text="💾 Salva su Excel", command=self._salva, state="disabled"
        )
        self.btn_salva.pack(side=LEFT, padx=8)
        self.progress = ttk.Progressbar(act_frame, mode="determinate")
        self.progress.pack(side=LEFT, fill=X, expand=True, padx=8)

        # --- Anteprima risultati ---
        prev_frame = ttk.LabelFrame(self.root, text="3. Anteprima (aggregato per causale)")
        prev_frame.pack(fill=BOTH, expand=True, padx=10, pady=(4, 4))
        self.tabella = ttk.Treeview(
            prev_frame,
            columns=("causale", "valore", "n"),
            show="headings",
        )
        self.tabella.heading("causale", text="Causale")
        self.tabella.heading("valore", text="Valore (€)")
        self.tabella.heading("n", text="N. voci")
        self.tabella.column("causale", width=440)
        self.tabella.column("valore", width=120, anchor="e")
        self.tabella.column("n", width=80, anchor="center")
        self.tabella.pack(fill=BOTH, expand=True, padx=8, pady=8)

        # --- Log/stato ---
        self.var_log = StringVar(value="Pronto.")
        ttk.Label(self.root, textvariable=self.var_log, foreground="gray").pack(
            fill=X, padx=12, pady=(0, 8)
        )

    # ------------------------------------------------------------- Azioni --
    def _log(self, testo: str):
        self.var_log.set(testo)
        self.root.update_idletasks()

    def _scegli_foto(self):
        percorsi = filedialog.askopenfilenames(
            title="Seleziona le foto",
            filetypes=[
                ("Immagini", " ".join(f"*{e}" for e in ESTENSIONI_IMMAGINI)),
                ("Tutti i file", "*.*"),
            ],
        )
        self._aggiungi(percorsi)

    def _scegli_cartella(self):
        cartella = filedialog.askdirectory(title="Seleziona una cartella di foto")
        if not cartella:
            return
        trovate = [
            str(p)
            for p in sorted(Path(cartella).iterdir())
            if p.suffix.lower() in ESTENSIONI_IMMAGINI
        ]
        self._aggiungi(trovate)

    def _aggiungi(self, percorsi):
        for p in percorsi:
            if p and p not in self.percorsi:
                self.percorsi.append(p)
                self.lista.insert("", END, values=(Path(p).name,))
        self._aggiorna_conteggio()

    def _svuota(self):
        self.percorsi.clear()
        for item in self.lista.get_children():
            self.lista.delete(item)
        self._aggiorna_conteggio()

    def _aggiorna_conteggio(self):
        self.lbl_conteggio.config(text=f"{len(self.percorsi)} foto selezionate")

    def _scegli_excel(self):
        percorso = filedialog.asksaveasfilename(
            title="File Excel di destinazione",
            defaultextension=".xlsx",
            filetypes=[("Foglio Excel", "*.xlsx")],
            initialfile=Path(self.var_excel.get()).name or "spese.xlsx",
        )
        if percorso:
            self.var_excel.set(percorso)

    def _cfg_corrente(self) -> Config:
        self.cfg.ocr_url = self.var_url.get().strip()
        self.cfg.modello = self.var_modello.get().strip()
        self.cfg.ultimo_excel = self.var_excel.get().strip()
        self.cfg.salva()
        return self.cfg

    # --------------------------------------------------------- Stato OCR --
    def _verifica_stato_async(self):
        def worker():
            stato = verifica_stato(self._cfg_corrente())
            self.root.after(0, lambda: self._mostra_stato(stato))

        threading.Thread(target=worker, daemon=True).start()

    def _mostra_stato(self, stato: dict):
        if not stato["raggiungibile"]:
            self.lbl_stato.config(text="● Non raggiungibile", foreground="#c0392b")
        elif not stato["modello_disponibile"]:
            self.lbl_stato.config(
                text="● Modello mancante", foreground="#e67e22"
            )
        else:
            self.lbl_stato.config(text="● Pronto", foreground="#27ae60")

    # ---------------------------------------------------- Elaborazione --
    def _avvia_elaborazione(self):
        if not self.percorsi:
            messagebox.showwarning("Nessuna foto", "Aggiungi almeno una foto.")
            return
        self.btn_elabora.config(state="disabled")
        self.btn_salva.config(state="disabled")
        self.progress.config(maximum=len(self.percorsi), value=0)
        for item in self.tabella.get_children():
            self.tabella.delete(item)

        cfg = self._cfg_corrente()
        percorsi = list(self.percorsi)

        def worker():
            def progress(i, tot, nome, msg):
                self.root.after(0, lambda: self._on_progress(i, tot, nome, msg))

            risultato = elabora_foto(percorsi, cfg, progress)
            self.root.after(0, lambda: self._on_fine(risultato))

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, i, tot, nome, msg):
        self.progress.config(value=i)
        self._log(f"[{i}/{tot}] {nome} — {msg}")

    def _on_fine(self, risultato):
        self.ultimo_risultato = risultato
        for r in risultato.righe:
            self.tabella.insert(
                "",
                END,
                values=(r.causale, f"-{r.totale:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), r.numero_voci),
            )
        tot = sum(r.totale for r in risultato.righe)
        self.btn_elabora.config(state="normal")
        if risultato.righe:
            self.btn_salva.config(state="normal")
        msg = (
            f"Estratte {len(risultato.voci)} voci → {len(risultato.righe)} causali. "
            f"Totale: -{tot:,.2f} €"
        )
        if risultato.errori:
            msg += f"  ({len(risultato.errori)} errori)"
        self._log(msg)
        if risultato.errori and not risultato.righe:
            messagebox.showerror(
                "Errore OCR",
                "Nessuna voce estratta.\n\n" + "\n".join(risultato.errori[:5]),
            )

    def _salva(self):
        if not self.ultimo_risultato or not self.ultimo_risultato.righe:
            return
        percorso = self.var_excel.get().strip()
        if not percorso:
            messagebox.showwarning("File mancante", "Scegli un file Excel di destinazione.")
            return
        try:
            n = salva_su_excel(self.ultimo_risultato.righe, percorso)
            self._cfg_corrente()
            self._log(f"Salvate {n} righe in {percorso}")
            messagebox.showinfo(
                "Salvataggio completato",
                f"Scritte {n} righe nel file:\n{percorso}",
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Errore di salvataggio", str(exc))


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
