"""Parsing di importi monetari scritti a mano/corsivo, in formato italiano.

Gestisce i casi tipici degli appunti di spesa:
    "12,50"      -> 12.50
    "1.234,56"   -> 1234.56
    "€ 45"       -> 45.00
    "45.00"      -> 45.00   (punto usato come separatore decimale)
    "1.234"      -> 1234.00 (punto come separatore delle migliaia)
    "-30,00"     -> 30.00   (il segno viene ignorato: le spese sono sempre negative)

Restituisce sempre un valore POSITIVO (il segno negativo viene applicato a
valle, in fase di scrittura, perché per specifica i valori sono sempre spese).
"""

from __future__ import annotations

import re
from typing import Optional

# Sequenza di cifre con separatori . , e spazi, opzionalmente con simbolo €/EUR.
_AMOUNT_RE = re.compile(
    r"""
    (?P<sign>[-−–—]?)          # eventuale segno (anche trattini unicode)
    \s*
    (?:€|EUR|eur)?             # eventuale valuta prima
    \s*
    (?P<num>\d[\d.,\s']*\d|\d) # cifre con separatori . , spazio o apice
    \s*
    (?:€|EUR|eur)?             # eventuale valuta dopo
    """,
    re.VERBOSE,
)


def _normalizza_numero(grezzo: str) -> Optional[float]:
    """Converte una stringa numerica (formato IT o EN) in float positivo."""
    s = grezzo.strip().replace(" ", "").replace("'", "").replace(" ", "")
    if not s:
        return None

    ha_virgola = "," in s
    ha_punto = "." in s

    if ha_virgola and ha_punto:
        # Il separatore decimale è quello più a destra.
        if s.rfind(",") > s.rfind("."):
            # formato italiano: punto = migliaia, virgola = decimali
            s = s.replace(".", "").replace(",", ".")
        else:
            # formato inglese: virgola = migliaia, punto = decimali
            s = s.replace(",", "")
    elif ha_virgola:
        # Solo virgola: separatore decimale (caso italiano tipico).
        # Se ci sono più virgole, tutte tranne l'ultima sono migliaia.
        parti = s.split(",")
        if len(parti) > 2:
            s = "".join(parti[:-1]) + "." + parti[-1]
        else:
            s = s.replace(",", ".")
    elif ha_punto:
        # Solo punto: potrebbe essere decimale o separatore migliaia.
        parti = s.split(".")
        if len(parti) == 2 and len(parti[1]) != 3:
            # es. "45.5" o "45.50" -> decimale
            s = s  # già corretto
        elif len(parti) == 2 and len(parti[1]) == 3 and len(parti[0]) <= 3:
            # ambiguo "1.234": trattato come migliaia
            s = s.replace(".", "")
        elif len(parti) > 2:
            # più punti -> tutti migliaia
            s = "".join(parti)
        # altrimenti lascio invariato (decimale a 3+ cifre poco probabile)

    try:
        val = float(s)
    except ValueError:
        return None
    return abs(val)


def parse_importo(testo: str) -> Optional[float]:
    """Estrae il primo importo valido da una stringa, come float positivo.

    Restituisce None se nessun importo è riconoscibile.
    """
    if testo is None:
        return None
    m = _AMOUNT_RE.search(str(testo))
    if not m:
        return None
    return _normalizza_numero(m.group("num"))


def formatta_importo(valore: float) -> float:
    """Arrotonda un importo a 2 decimali (evita errori di virgola mobile)."""
    return round(float(valore), 2)
