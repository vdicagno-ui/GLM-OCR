"""Motore OCR: invia una foto a GLM-OCR (Ollama) e ne estrae le voci di spesa.

Usa l'API compatibile OpenAI esposta da Ollama (/v1/chat/completions), come il
resto del progetto GLM-OCR. Il prompt è progettato per estrarre coppie
causale/importo in JSON, ignorando esplicitamente le righe di totale.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import List

import httpx

from .config import Config
from .parsing import estrai_voci, Voce

PROMPT_ESTRAZIONE = (
    "Le immagini sono appunti di spese scritti a mano in corsivo. "
    "Ogni riga contiene una CAUSALE (descrizione della spesa) e una CIFRA in euro. "
    "Sono gli unici dati presenti. "
    "Estrai TUTTE le voci e restituisci SOLO un array JSON, senza testo aggiuntivo, "
    "nel formato: "
    '[{"causale": "<descrizione>", "importo": "<cifra come appare>"}]. '
    "Trascrivi l'importo esattamente come scritto (es. \"12,50\"). "
    "NON includere righe di totale/somma: escludi qualsiasi riga la cui causale "
    "sia 'totale', 'totali', 'somma' o simili, e qualsiasi riga che contenga solo "
    "una cifra senza causale. "
    "Se una foto non contiene voci, restituisci []."
)


def _immagine_data_url(image_path: str) -> str:
    mime, _ = mimetypes.guess_type(image_path)
    if mime is None:
        mime = "image/png"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def ocr_immagine_raw(image_path: str, cfg: Config) -> str:
    """Invia l'immagine al modello e restituisce la risposta testuale grezza."""
    data_url = _immagine_data_url(image_path)
    payload = {
        "model": cfg.modello,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": PROMPT_ESTRAZIONE},
                ],
            }
        ],
        "stream": False,
        "temperature": 0,
    }
    url = cfg.ocr_url.rstrip("/") + "/v1/chat/completions"
    with httpx.Client(timeout=cfg.timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def estrai_da_immagine(image_path: str, cfg: Config) -> List[Voce]:
    """OCR + parsing: da percorso immagine a lista di Voci (totali esclusi)."""
    grezzo = ocr_immagine_raw(image_path, cfg)
    return estrai_voci(grezzo, origine=Path(image_path).name)


def verifica_stato(cfg: Config) -> dict:
    """Verifica raggiungibilità dell'endpoint e disponibilità del modello."""
    risultato = {"raggiungibile": False, "modello_disponibile": False, "errore": None}
    try:
        url = cfg.ocr_url.rstrip("/") + "/api/tags"
        with httpx.Client(timeout=5) as client:
            resp = client.get(url)
            resp.raise_for_status()
            risultato["raggiungibile"] = True
            modelli = [m.get("name", "") for m in resp.json().get("models", [])]
            risultato["modello_disponibile"] = any(
                m == cfg.modello or m.startswith(cfg.modello + ":") for m in modelli
            )
    except httpx.ConnectError:
        risultato["errore"] = f"Impossibile connettersi a {cfg.ocr_url}"
    except Exception as exc:  # noqa: BLE001
        risultato["errore"] = str(exc)
    return risultato
