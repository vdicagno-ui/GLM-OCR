#!/usr/bin/env python3
"""
transcribe_handwriting.py — Trascrittore di documenti manoscritti in corsivo.

Utilizza un LLM locale con capacità visive (di default Gemma 3, es. `gemma3:4b`)
servito da Ollama. Il modello agisce come esperto grafologo e specialista nella
trascrizione di documenti manoscritti.

Uso:
    ./transcribe_handwriting.py immagine.jpg
    ./transcribe_handwriting.py pagina1.png pagina2.png
    ./transcribe_handwriting.py --model gemma3:12b lettera.jpg
    ./transcribe_handwriting.py --output trascrizione.txt scansione.png

Requisiti:
    - Ollama in esecuzione in locale (https://ollama.com)
    - Un modello vision, es.:  ollama pull gemma3:4b
    - pip install httpx
"""

import argparse
import base64
import mimetypes
import os
import sys

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("HANDWRITING_MODEL", "gemma3:4b")

# Le regole tassative da rispettare, fornite al modello come system prompt.
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


def encode_image(path: str) -> str:
    """Legge un'immagine dal disco e la codifica in base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def data_uri(path: str, img_b64: str) -> str:
    """Costruisce un data URI con il MIME type corretto per l'immagine."""
    mime, _ = mimetypes.guess_type(path)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{img_b64}"


def transcribe(image_path: str, model: str, timeout: float) -> str:
    """Invia l'immagine al modello locale e restituisce la sola trascrizione."""
    img_b64 = encode_image(image_path)

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
        # Temperatura bassa per massimizzare la fedeltà ed evitare invenzioni.
        "temperature": 0,
        "stream": False,
    }

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Trascrive testo manoscritto in corsivo da immagini usando un LLM "
            "locale (Gemma 3 via Ollama)."
        )
    )
    parser.add_argument(
        "images",
        nargs="+",
        help="Uno o più percorsi di file immagine da trascrivere.",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_MODEL,
        help=f"Nome del modello Ollama vision (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Percorso del file su cui salvare la trascrizione (default: stdout).",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=300.0,
        help="Timeout in secondi per la richiesta al modello (default: 300).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Verifica preliminare che i file esistano.
    for path in args.images:
        if not os.path.isfile(path):
            print(f"Errore: file non trovato: {path}", file=sys.stderr)
            return 1

    results = []
    multiple = len(args.images) > 1

    for path in args.images:
        try:
            text = transcribe(path, args.model, args.timeout)
        except httpx.ConnectError:
            print(
                f"Errore: impossibile connettersi a Ollama su {OLLAMA_URL}.\n"
                "Assicurati che Ollama sia in esecuzione e che il modello sia "
                f"disponibile (es. `ollama pull {args.model}`).",
                file=sys.stderr,
            )
            return 2
        except httpx.HTTPStatusError as exc:
            print(
                f"Errore dal server Ollama ({exc.response.status_code}): "
                f"{exc.response.text}",
                file=sys.stderr,
            )
            return 3
        except Exception as exc:  # noqa: BLE001
            print(f"Errore durante la trascrizione di {path}: {exc}", file=sys.stderr)
            return 4

        if multiple:
            # Separatore discreto per distinguere più pagine.
            results.append(f"===== {os.path.basename(path)} =====\n{text}")
        else:
            results.append(text)

    output = "\n\n".join(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Trascrizione salvata in: {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
