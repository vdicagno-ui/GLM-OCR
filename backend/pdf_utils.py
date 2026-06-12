"""PDF to image conversion utilities using pdf2image (poppler)."""

import os
from pathlib import Path
from typing import List

from pdf2image import convert_from_path
from PIL import Image


PREVIEW_DPI = 150
OCR_DPI = 200


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = PREVIEW_DPI) -> List[str]:
    """
    Convert all pages of a PDF to PNG images.

    Returns a list of absolute paths to the saved PNG files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = convert_from_path(pdf_path, dpi=dpi)
    paths = []

    for i, img in enumerate(images, start=1):
        out_path = output_dir / f"page_{i:04d}.png"
        img.save(str(out_path), "PNG")
        paths.append(str(out_path))

    return paths


def pdf_page_count(pdf_path: str) -> int:
    """Return the number of pages in a PDF without converting all of them."""
    from pdf2image.pdf2image import pdfinfo_from_path
    info = pdfinfo_from_path(pdf_path)
    return info["Pages"]


def convert_single_page(pdf_path: str, page_num: int, output_dir: str, dpi: int = OCR_DPI) -> str:
    """
    Convert a single page (1-indexed) of a PDF to PNG at the given DPI.
    Returns the path to the saved PNG.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = convert_from_path(pdf_path, dpi=dpi, first_page=page_num, last_page=page_num)
    if not images:
        raise ValueError(f"Could not convert page {page_num}")

    out_path = output_dir / f"ocr_page_{page_num:04d}.png"
    images[0].save(str(out_path), "PNG")
    return str(out_path)
