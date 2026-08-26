"""Orchestrazione: da un elenco di foto al file Excel finale.

Espone una funzione con callback di avanzamento, così la GUI può mostrare la
progressione senza conoscere i dettagli interni.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional

from .aggregate import RigaAggregata, aggrega_per_causale
from .config import Config
from .excel_writer import scrivi_righe
from .ocr_backend import estrai_da_immagine
from .parsing import Voce


@dataclass
class Risultato:
    """Esito complessivo dell'elaborazione."""

    voci: List[Voce] = field(default_factory=list)
    righe: List[RigaAggregata] = field(default_factory=list)
    errori: List[str] = field(default_factory=list)
    righe_scritte: int = 0


# Callback: (indice_corrente, totale, nome_file, messaggio)
ProgressCb = Optional[Callable[[int, int, str, str], None]]


def elabora_foto(
    percorsi_immagini: List[str],
    cfg: Config,
    progress: ProgressCb = None,
) -> Risultato:
    """Esegue OCR su tutte le foto e restituisce voci + aggregazione.

    Non scrive su Excel: separare l'estrazione dalla scrittura permette alla GUI
    di mostrare un'anteprima e far confermare l'utente.
    """
    risultato = Risultato()
    totale = len(percorsi_immagini)
    for i, percorso in enumerate(percorsi_immagini, start=1):
        nome = percorso.split("/")[-1].split("\\")[-1]
        if progress:
            progress(i, totale, nome, "OCR in corso…")
        try:
            voci = estrai_da_immagine(percorso, cfg)
            risultato.voci.extend(voci)
            if progress:
                progress(i, totale, nome, f"{len(voci)} voci estratte")
        except Exception as exc:  # noqa: BLE001
            msg = f"{nome}: {exc}"
            risultato.errori.append(msg)
            if progress:
                progress(i, totale, nome, f"Errore: {exc}")

    risultato.righe = aggrega_per_causale(risultato.voci)
    return risultato


def salva_su_excel(
    righe: List[RigaAggregata],
    percorso_excel: str,
    data_inserimento: Optional[date] = None,
) -> int:
    """Scrive le righe aggregate su Excel e restituisce il numero di righe."""
    scritte = scrivi_righe(percorso_excel, righe, data_inserimento)
    return scritte
