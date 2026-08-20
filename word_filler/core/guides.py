"""Read plain text from the various supported 'guide' file formats.

A guide file is the source document from which field values are extracted.
Supported formats: .docx, .pdf, .txt, .md (and .rtf as best effort).
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = (".docx", ".pdf", ".txt", ".md", ".rtf")

# When "first page only" is requested but the format has no real page concept
# (docx/txt without an explicit page break), fall back to this many characters,
# which comfortably covers a heading plus the lines right below it.
FIRST_PAGE_CHAR_CAP = 3500


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def read_guide_text(path: str | Path, first_page_only: bool = False) -> str:
    """Extract readable text from a guide file.

    When ``first_page_only`` is True, only the first page is returned (page 1
    for PDFs; up to the first page break — or a character cap — for the other
    formats). This is useful when the relevant data always sits at the top of a
    long document.

    Raises ValueError for unsupported formats and RuntimeError when a
    required optional dependency is missing.
    """
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".docx":
        text = _read_docx(path, first_page_only)
    elif ext == ".pdf":
        text = _read_pdf(path, first_page_only)
    elif ext in (".txt", ".md"):
        text = _read_text(path)
    elif ext == ".rtf":
        text = _read_rtf(path)
    else:
        raise ValueError(f"Formato non supportato: {ext}")

    if first_page_only:
        text = _first_page_fallback(text)
    return text


def _first_page_fallback(text: str) -> str:
    """Cut ``text`` at the first form-feed page break or the character cap."""
    if "\f" in text:
        text = text.split("\f", 1)[0]
    if len(text) > FIRST_PAGE_CHAR_CAP:
        text = text[:FIRST_PAGE_CHAR_CAP]
    return text


def _read_text(path: Path) -> str:
    # Try utf-8 first, then fall back to the common Windows encoding.
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def _read_docx(path: Path, first_page_only: bool = False) -> str:
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
        # Stop at the first page break so we only keep page 1.
        if first_page_only and _para_has_page_break(para):
            return "\n".join(parts)

    if not first_page_only:
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


def _para_has_page_break(para) -> bool:
    """True if the paragraph contains an explicit or rendered page break."""
    try:
        xml = para._p.xml
    except Exception:
        return False
    return 'w:type="page"' in xml or "lastRenderedPageBreak" in xml


def _read_pdf(path: Path, first_page_only: bool = False) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "Manca la libreria pypdf (pip install pypdf)."
        ) from exc

    reader = PdfReader(str(path))
    pages = reader.pages[:1] if first_page_only else reader.pages
    parts: list[str] = []
    for page in pages:
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
