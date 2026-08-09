# -*- coding: utf-8 -*-
"""
Configurazione del programma "Stampa Ricevute PEC".

Modifica questi valori se le tue esigenze cambiano: non serve toccare il
codice principale.
"""

# ---------------------------------------------------------------------------
# Indirizzi da ESCLUDERE.
# Le ricevute che risultano "provenienti da" / collegate a questi indirizzi
# non vengono stampate.
# ---------------------------------------------------------------------------
EXCLUDED_ADDRESSES = [
    "dInpsComunica@inps.it",
    "inpscomunica@postacert.inps.gov.it",
]

# Dove cercare gli indirizzi da escludere:
#   "any"    -> mittente, destinatari, oggetto e corpo (default, piu' prudente)
#   "sender" -> solo il mittente della ricevuta
EXCLUSION_SCOPE = "any"

# ---------------------------------------------------------------------------
# Come riconoscere una "ricevuta di consegna" PEC.
# Vengono selezionate le mail il cui OGGETTO inizia con uno di questi prefissi
# (confronto senza distinzione tra maiuscole/minuscole).
# ---------------------------------------------------------------------------
RECEIPT_SUBJECT_PREFIXES = [
    "CONSEGNA:",
]

# ---------------------------------------------------------------------------
# Nome base dei PDF generati.
# Il primo file sara' "bozza ad avv..pdf"; gli eventuali successivi nella
# stessa cartella diventano "bozza ad avv. (2).pdf", "bozza ad avv. (3).pdf" ...
# ---------------------------------------------------------------------------
BASE_FILENAME = "bozza ad avv."

# ---------------------------------------------------------------------------
# Motore di conversione in PDF:
#   "word"   -> usa Microsoft Word per esportare la mail in PDF (consigliato,
#               completamente automatico e offline).
#   "pdf24"  -> usa lo strumento a riga di comando di PDF24 (se installato).
# ---------------------------------------------------------------------------
PDF_ENGINE = "word"

# Percorso dello strumento a riga di comando di PDF24 (usato solo se
# PDF_ENGINE = "pdf24"). Modificalo se PDF24 e' installato altrove.
PDF24_DOCTOOL = r"C:\Program Files\PDF24\pdf24-DocTool.exe"

# ---------------------------------------------------------------------------
# Comportamento apertura cartelle all'avvio.
# ---------------------------------------------------------------------------
OPEN_OUTLOOK_INBOX = True   # apre la Posta in arrivo dentro Outlook
OPEN_CHOSEN_FOLDER = True    # apre la cartella scelta in Esplora risorse
