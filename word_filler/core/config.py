"""Persist user settings between runs in a small JSON file."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".word_filler"
CONFIG_PATH = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "endpoint": "http://localhost:1234/v1",
    "model": "",
    "preset": "Parentesi quadra [campo]",
    "custom_regex": "",
    "use_custom_regex": False,
    "use_ai": True,
    "first_page_only": True,
    "resolve_judges": True,
    "output_dir": "",
    "output_suffix": "_compilato",
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except Exception:
        pass  # Corrupt config: fall back to defaults silently.
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        clean = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
        CONFIG_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    except Exception:
        pass  # Never let a settings write crash the app.
