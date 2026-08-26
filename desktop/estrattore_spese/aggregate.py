"""Aggregazione delle voci di spesa per causale."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, List

from .importi import formatta_importo
from .parsing import Voce


@dataclass
class RigaAggregata:
    """Risultato dell'aggregazione: una causale con il totale sommato."""

    causale: str
    totale: float  # positivo; il segno negativo è applicato in fase di scrittura
    numero_voci: int


def _chiave_causale(causale: str) -> str:
    """Chiave normalizzata per raggruppare causali equivalenti."""
    return " ".join(causale.strip().lower().split())


def aggrega_per_causale(voci: Iterable[Voce]) -> List[RigaAggregata]:
    """Somma gli importi raggruppandoli per causale (case/spazi-insensitive).

    Mantiene l'ordine di prima apparizione delle causali e usa come etichetta
    la prima forma incontrata della causale.
    """
    gruppi: "OrderedDict[str, RigaAggregata]" = OrderedDict()
    for v in voci:
        chiave = _chiave_causale(v.causale)
        if chiave in gruppi:
            r = gruppi[chiave]
            r.totale = formatta_importo(r.totale + v.importo)
            r.numero_voci += 1
        else:
            gruppi[chiave] = RigaAggregata(
                causale=v.causale.strip(),
                totale=formatta_importo(v.importo),
                numero_voci=1,
            )
    return list(gruppi.values())
