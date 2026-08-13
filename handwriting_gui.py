#!/usr/bin/env python3
"""
handwriting_gui.py — Trascrittore di documenti manoscritti con interfaccia grafica.

Applicazione desktop (Tkinter) che usa un LLM locale con capacità visive
(di default Gemma 3 via Ollama) come esperto grafologo per trascrivere testo
manoscritto in corsivo, rispettando tassativamente le regole di trascrizione.

Può essere eseguita direttamente:
    python3 handwriting_gui.py

Oppure impacchettata in un eseguibile standalone con PyInstaller
(vedi build_executable.sh / build_executable.bat).

Requisiti a runtime:
    - Ollama in esecuzione in locale (https://ollama.com)
    - Un modello vision, es.:  ollama pull gemma3:4b
"""

import base64
import mimetypes
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import httpx

# Pillow è opzionale: serve solo per l'anteprima dell'immagine.
try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("HANDWRITING_MODEL", "gemma3:4b")

SYSTEM_PROMPT = (
    "Sei un esperto grafologo e specialista nella trascrizione di documenti "
    "manoscritti. Il tuo unico compito è trascrivere accuratamente il testo in "
    "corsivo presente nell'immagine.\n\n"
    "Devi seguire tassativamente queste regole:\n"
    "1. Trascrizione letterale: trascrivi parola per parola, esattamente come "
    "scritto. Non correggere la grammatica, l'ortografia o la punteggiatura.\n"
    "2. Parole illeggibili: se una parola è del tutto indecifrabile, "
    "sostituiscila con il tag [illeggibile]. Non inventare e non indovinare il "
    "contesto.\n"
    "3. Nessun commento: fornisci esclusivamente il testo trascritto. Non "
    "aggiungere introduzioni (es. \"Ecco la trascrizione:\"), non aggiungere "
    "spiegazioni e non inserire note alla fine.\n"
    "4. Formattazione: mantieni i capoversi e la struttura originale delle "
    "righe, se possibile."
)

USER_PROMPT = (
    "Trascrivi il testo manoscritto in corsivo presente in questa immagine, "
    "rispettando tassativamente le regole indicate."
)

IMAGE_TYPES = [
    ("Immagini", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
    ("Tutti i file", "*.*"),
]


def data_uri(path: str, img_b64: str) -> str:
    """Costruisce un data URI con il MIME type corretto per l'immagine."""
    mime, _ = mimetypes.guess_type(path)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{img_b64}"


def transcribe(image_path: str, model: str, ollama_url: str, timeout: float) -> str:
    """Invia l'immagine al modello locale e restituisce la sola trascrizione."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri(image_path, img_b64)},
                    },
                    {"type": "text", "text": USER_PROMPT},
                ],
            },
        ],
        "temperature": 0,
        "stream": False,
    }

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{ollama_url}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class HandwritingApp(tk.Tk):
    """Finestra principale dell'applicazione."""

    def __init__(self):
        super().__init__()
        self.title("Trascrittore Manoscritti — Gemma 3 (locale)")
        self.geometry("1000x680")
        self.minsize(820, 560)

        self.image_path = None
        self._preview_img = None  # riferimento per evitare il garbage collector
        self._result_queue = queue.Queue()

        self._build_ui()
        self.after(120, self._poll_result_queue)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Barra dei parametri (modello + URL Ollama)
        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")

        ttk.Label(top, text="Modello:").pack(side="left")
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Entry(top, textvariable=self.model_var, width=16).pack(
            side="left", padx=(4, 16)
        )

        ttk.Label(top, text="Ollama URL:").pack(side="left")
        self.url_var = tk.StringVar(value=DEFAULT_OLLAMA_URL)
        ttk.Entry(top, textvariable=self.url_var, width=26).pack(side="left", padx=4)

        # Corpo diviso: sinistra (immagine) / destra (trascrizione)
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left = ttk.Frame(body, padding=6)
        right = ttk.Frame(body, padding=6)
        body.add(left, weight=1)
        body.add(right, weight=1)

        # --- Colonna sinistra: selezione e anteprima immagine
        btns = ttk.Frame(left)
        btns.pack(fill="x")
        ttk.Button(btns, text="Apri immagine…", command=self.open_image).pack(
            side="left"
        )
        self.file_label = ttk.Label(btns, text="Nessun file selezionato", foreground="#666")
        self.file_label.pack(side="left", padx=8)

        self.preview = tk.Label(
            left,
            text="Anteprima immagine",
            relief="groove",
            background="#f4f4f4",
            foreground="#888",
        )
        self.preview.pack(fill="both", expand=True, pady=(8, 0))

        # --- Colonna destra: trascrizione
        ttk.Label(right, text="Trascrizione:").pack(anchor="w")
        self.output = scrolledtext.ScrolledText(
            right, wrap="word", font=("TkDefaultFont", 11)
        )
        self.output.pack(fill="both", expand=True, pady=(4, 8))

        out_btns = ttk.Frame(right)
        out_btns.pack(fill="x")
        ttk.Button(out_btns, text="Copia", command=self.copy_text).pack(side="left")
        ttk.Button(out_btns, text="Salva su file…", command=self.save_text).pack(
            side="left", padx=6
        )
        ttk.Button(out_btns, text="Pulisci", command=self.clear_text).pack(side="left")

        # Barra inferiore: azione principale + stato
        bottom = ttk.Frame(self, padding=(12, 4, 12, 10))
        bottom.pack(fill="x")

        self.transcribe_btn = ttk.Button(
            bottom, text="Trascrivi", command=self.start_transcription
        )
        self.transcribe_btn.pack(side="left")

        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=160)

        self.status = ttk.Label(bottom, text="Pronto.", foreground="#444")
        self.status.pack(side="right")

    # ------------------------------------------------------------- Azioni
    def open_image(self):
        path = filedialog.askopenfilename(
            title="Seleziona un'immagine", filetypes=IMAGE_TYPES
        )
        if not path:
            return
        self.image_path = path
        self.file_label.config(text=os.path.basename(path), foreground="#222")
        self._show_preview(path)
        self.set_status(f"Immagine caricata: {os.path.basename(path)}")

    def _show_preview(self, path: str):
        if not HAS_PIL:
            self.preview.config(
                text=f"{os.path.basename(path)}\n(anteprima non disponibile: manca Pillow)",
                image="",
            )
            return
        try:
            img = Image.open(path)
            img.thumbnail((460, 560))
            self._preview_img = ImageTk.PhotoImage(img)
            self.preview.config(image=self._preview_img, text="")
        except Exception as exc:  # noqa: BLE001
            self.preview.config(text=f"Impossibile aprire l'anteprima:\n{exc}", image="")

    def start_transcription(self):
        if not self.image_path:
            messagebox.showwarning(
                "Nessuna immagine", "Seleziona prima un'immagine da trascrivere."
            )
            return

        model = self.model_var.get().strip() or DEFAULT_MODEL
        url = self.url_var.get().strip().rstrip("/") or DEFAULT_OLLAMA_URL

        self.transcribe_btn.config(state="disabled")
        self.progress.pack(side="left", padx=12)
        self.progress.start(12)
        self.set_status(f"Trascrizione in corso con «{model}»…")

        thread = threading.Thread(
            target=self._worker,
            args=(self.image_path, model, url),
            daemon=True,
        )
        thread.start()

    def _worker(self, path, model, url):
        """Esegue la richiesta in un thread separato per non bloccare la GUI."""
        try:
            text = transcribe(path, model, url, timeout=300.0)
            self._result_queue.put(("ok", text))
        except httpx.ConnectError:
            self._result_queue.put(
                (
                    "error",
                    f"Impossibile connettersi a Ollama su {url}.\n\n"
                    "Verifica che Ollama sia in esecuzione e che il modello sia "
                    f"disponibile:\n    ollama pull {model}",
                )
            )
        except httpx.HTTPStatusError as exc:
            self._result_queue.put(
                (
                    "error",
                    f"Errore dal server Ollama ({exc.response.status_code}):\n"
                    f"{exc.response.text}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._result_queue.put(("error", f"Errore durante la trascrizione:\n{exc}"))

    def _poll_result_queue(self):
        """Controlla periodicamente la coda dei risultati dal thread di lavoro."""
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.transcribe_btn.config(state="normal")

            if kind == "ok":
                self.output.delete("1.0", "end")
                self.output.insert("1.0", payload)
                self.set_status("Trascrizione completata.")
            else:
                self.set_status("Errore.")
                messagebox.showerror("Errore", payload)
        finally:
            self.after(120, self._poll_result_queue)

    # ------------------------------------------------------------- Output
    def copy_text(self):
        text = self.output.get("1.0", "end").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status("Testo copiato negli appunti.")

    def save_text(self):
        text = self.output.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Niente da salvare", "La trascrizione è vuota.")
            return
        path = filedialog.asksaveasfilename(
            title="Salva trascrizione",
            defaultextension=".txt",
            filetypes=[("File di testo", "*.txt"), ("Tutti i file", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        self.set_status(f"Salvato in: {os.path.basename(path)}")

    def clear_text(self):
        self.output.delete("1.0", "end")
        self.set_status("Pronto.")

    def set_status(self, msg: str):
        self.status.config(text=msg)


def main():
    app = HandwritingApp()
    app.mainloop()


if __name__ == "__main__":
    main()
