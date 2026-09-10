"""
compose.py -- unisce 9 immagini in un'unica griglia 3x3.

Le immagini vengono disposte in sequenza progressiva da sinistra a destra e
dall'alto verso il basso:

    1  2  3
    4  5  6
    7  8  9

Puo' essere usato dalla GUI oppure da riga di comando:

    python compose.py output_dir/montage_3x3.bmp pos_01.bmp pos_02.bmp ...
"""

from __future__ import annotations

import sys
from typing import List, Sequence, Tuple

from PIL import Image


def make_montage(
    image_paths: Sequence[str],
    out_path: str,
    cols: int = 3,
    rows: int = 3,
    bg: Tuple[int, int, int] = (255, 255, 255),
) -> str:
    """Crea una griglia cols x rows dalle immagini indicate e la salva in out_path.

    Le immagini sono posizionate in ordine di riga (row-major): l'immagine
    all'indice i finisce nella riga i // cols e colonna i % cols.
    """
    if not image_paths:
        raise ValueError("Nessuna immagine fornita per il montaggio.")

    expected = cols * rows
    if len(image_paths) != expected:
        raise ValueError(
            f"Servono esattamente {expected} immagini ({cols}x{rows}), "
            f"ricevute {len(image_paths)}."
        )

    images: List[Image.Image] = [Image.open(p).convert("RGB") for p in image_paths]

    # dimensione della cella = dimensione della prima immagine
    cell_w, cell_h = images[0].size

    canvas = Image.new("RGB", (cell_w * cols, cell_h * rows), bg)

    for i, img in enumerate(images):
        if img.size != (cell_w, cell_h):
            img = img.resize((cell_w, cell_h), Image.LANCZOS)
        row = i // cols
        col = i % cols
        canvas.paste(img, (col * cell_w, row * cell_h))

    # salva nel formato dedotto dall'estensione (.bmp per default)
    fmt = "BMP" if out_path.lower().endswith(".bmp") else None
    canvas.save(out_path, format=fmt)
    return out_path


def _main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out_path = argv[1]
    image_paths = argv[2:]
    make_montage(image_paths, out_path)
    print(f"Creato: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
