"""Configurazione dell'applicazione (endpoint OCR, modello, default)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

# File di configurazione nella home dell'utente (persistente tra le sessioni).
CONFIG_PATH = Path.home() / ".estrattore_spese.json"


@dataclass
class Config:
    """Parametri configurabili dall'utente."""

    # Endpoint OCR compatibile OpenAI (Ollama espone /v1/chat/completions).
    ocr_url: str = "http://localhost:11434"
    # Nome del modello di visione/OCR (GLM-OCR su Ollama).
    modello: str = "glm-ocr"
    # Timeout richieste in secondi.
    timeout: int = 180
    # Ultimo file Excel usato.
    ultimo_excel: str = str(Path.home() / "spese.xlsx")

    @classmethod
    def carica(cls) -> "Config":
        cfg = cls()
        # Variabili d'ambiente hanno priorità (utile per test/CI).
        cfg.ocr_url = os.environ.get("ESTRATTORE_OCR_URL", cfg.ocr_url)
        cfg.modello = os.environ.get("ESTRATTORE_MODELLO", cfg.modello)
        if CONFIG_PATH.exists():
            try:
                dati = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for k, v in dati.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception:
                pass
        return cfg

    def salva(self) -> None:
        try:
            CONFIG_PATH.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
