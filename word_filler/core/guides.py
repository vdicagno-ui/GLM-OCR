"""Read plain text from the various supported 'guide' file formats.

A guide file is the source document from which field values are extracted.
Supported formats: .docx, .pdf, .txt, .md (and .rtf as best effort).
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = (".docx", ".pdf", ".txt", ".md", ".rtf")


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def read_guide_text(path: str | Path) -> str:
    """Extract all readable text from a guide file.

    Raises ValueError for unsupported formats and RuntimeError when a
    required optional dependency is missing.
    """
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".docx":
        return _read_docx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in (".txt", ".md"):
        return _read_text(path)
    if ext == ".rtf":
        return _read_rtf(path)

    raise ValueError(f"Formato non supportato: {ext}")


def _read_text(path: Path) -> str:
    # Try utf-8 first, then fall back to the common Windows encoding.
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "Manca la libreria python-docx (pip install python-docx)."
        ) from exc

    doc = Document(str(path))
    parts: list[str] = []

    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                parts.append(line)

    # Headers / footers can hold reference numbers, dates, etc.
    for section in doc.sections:
        for container in (section.header, section.footer):
            for para in container.paragraphs:
                if para.text.strip():
                    parts.append(para.text)

    return "\n".join(parts)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "Manca la libreria pypdf (pip install pypdf)."
        ) from exc

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def _read_rtf(path: Path) -> str:
    """Very small RTF-to-text fallback (strips control words)."""
    import re

    raw = path.read_text(encoding="latin-1", errors="replace")
    # Remove RTF groups metadata and control words, keep visible text.
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", raw)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    return text.strip()
