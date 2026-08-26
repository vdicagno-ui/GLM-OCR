"""Interpretazione dell'output OCR in voci di spesa (causale + importo).

Il motore OCR/visione restituisce, idealmente, un JSON strutturato. Questo
modulo è tollerante: se riceve JSON lo usa, altrimenti ripiega su un parsing
riga-per-riga del testo. In entrambi i casi filtra le righe di totale.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from .importi import parse_importo, formatta_importo

# Parole che identificano una riga di TOTALE, da ignorare.
_PAROLE_TOTALE = {
    "totale",
    "totali",
    "total",
    "totale spese",
    "somma",
    "tot",
    "tot.",
}


@dataclass
class Voce:
    """Una voce di spesa estratta da una foto."""

    causale: str
    importo: float  # sempre positivo qui; il segno negativo è applicato in uscita
    origine: str = ""  # nome file/foto di provenienza (per diagnostica)


def is_totale(causale: Optional[str]) -> bool:
    """True se la causale indica un totale (o è vuota) e va quindi ignorata."""
    if causale is None:
        return True
    c = causale.strip().lower()
    if not c:
        return True
    # Rimuove eventuali due punti finali ("totale:")
    c = c.rstrip(":.- ").strip()
    if c in _PAROLE_TOTALE:
        return True
    # "totale ..." all'inizio della causale
    if c.startswith("totale") or c.startswith("totali"):
        return True
    return False


def _pulisci_causale(causale: str) -> str:
    """Normalizza la causale rimuovendo importi residui e spazi superflui."""
    c = causale.strip()
    # Rimuove eventuali simboli di valuta e cifre finali "spesa 12,50"
    c = re.sub(r"[\s:.\-–—]*(?:€|EUR|eur)?\s*[-−]?\d[\d.,\s']*\d?\s*(?:€|EUR|eur)?\s*$", "", c)
    c = c.strip(" :.-–—\t")
    # Comprime spazi multipli
    c = re.sub(r"\s+", " ", c)
    return c


def _voci_da_json(dati, origine: str) -> Optional[List[Voce]]:
    """Prova a costruire le voci da una struttura JSON (lista di dict)."""
    # Accetta sia una lista diretta sia {"voci": [...]} / {"items": [...]}
    if isinstance(dati, dict):
        for chiave in ("voci", "items", "spese", "expenses", "data", "rows"):
            if isinstance(dati.get(chiave), list):
                dati = dati[chiave]
                break
        else:
            return None
    if not isinstance(dati, list):
        return None

    voci: List[Voce] = []
    for elem in dati:
        if not isinstance(elem, dict):
            continue
        causale = None
        for k in ("causale", "descrizione", "voce", "label", "categoria", "causal"):
            if elem.get(k):
                causale = str(elem[k])
                break
        importo_raw = None
        for k in ("importo", "valore", "cifra", "amount", "value", "prezzo"):
            if elem.get(k) is not None and str(elem.get(k)).strip() != "":
                importo_raw = elem[k]
                break

        # Segnalazione esplicita di totale dal modello
        if elem.get("totale") is True or str(elem.get("tipo", "")).lower() in ("totale", "total"):
            continue

        if is_totale(causale):
            continue

        importo = parse_importo(str(importo_raw)) if importo_raw is not None else None
        if importo is None:
            continue

        voci.append(
            Voce(
                causale=_pulisci_causale(causale) or "(senza causale)",
                importo=formatta_importo(importo),
                origine=origine,
            )
        )
    return voci


def _estrai_json(testo: str):
    """Estrae il primo blocco JSON (array o oggetto) da un testo libero."""
    # Prova diretta
    testo_strip = testo.strip()
    if testo_strip.startswith("[") or testo_strip.startswith("{"):
        try:
            return json.loads(testo_strip)
        except json.JSONDecodeError:
            pass
    # Cerca un array o oggetto nel testo (anche dentro ```json ... ```)
    m = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", testo, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\[.*\]|\{.*\})", testo, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _voci_da_testo(testo: str, origine: str) -> List[Voce]:
    """Parsing riga-per-riga: ogni riga = 'causale ... importo'."""
    voci: List[Voce] = []
    for riga in testo.splitlines():
        riga = riga.strip().strip("|").strip()
        if not riga:
            continue
        # Salta separatori di tabella markdown
        if set(riga) <= set("-|: "):
            continue
        importo = parse_importo(riga)
        if importo is None:
            continue
        # La causale è il testo prima dell'importo (o dopo, se in testa).
        causale = _pulisci_causale(riga)
        if is_totale(causale) or is_totale(riga):
            continue
        if not causale:
            # riga con solo un numero e nessuna causale -> probabile totale
            continue
        voci.append(
            Voce(causale=causale, importo=formatta_importo(importo), origine=origine)
        )
    return voci


def estrai_voci(output_ocr: str, origine: str = "") -> List[Voce]:
    """Punto d'ingresso: da output OCR grezzo a lista di Voci valide.

    Prova prima il parsing JSON (più affidabile), poi ripiega sul testo.
    """
    if not output_ocr:
        return []
    dati = _estrai_json(output_ocr)
    if dati is not None:
        voci = _voci_da_json(dati, origine)
        if voci is not None:
            return voci
    return _voci_da_testo(output_ocr, origine)
