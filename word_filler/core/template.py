"""Detect and fill placeholders inside a Word (.docx) template.

Two responsibilities:

1. ``scan_placeholders`` — find every fill-in label in the template using a
   configurable regular expression and return the list of unique field
   descriptions (e.g. "nome cognome", "nr. RG", "data di incarico").

2. ``fill_template`` — produce a new document where every placeholder is
   replaced by the value provided for its field.

Replacement is run-aware: a placeholder split across several runs (very common
in Word) is still matched and replaced while keeping the formatting of the
first run of the match.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Placeholder presets
# ---------------------------------------------------------------------------
# Every preset regex MUST expose the human-readable field description in
# capture group 1. Group 0 (the whole match) is what gets replaced.

PRESETS: dict[str, str] = {
    # "da compilare nome cognome"  ->  field = "nome cognome"
    # The label ends at a natural boundary: 2+ spaces, a tab, a newline, a
    # comma/semicolon, a closing bracket, or end of text. It does NOT stop at a
    # single '.' so descriptions like "nr. RG" stay intact; a trailing '.' is
    # trimmed during normalisation.
    "Etichetta «da compilare …»": r"(?i)da\s+compilare[\s:]+(.+?)(?=\s{2,}|\t|\r|\n|[,;)\]}]|$)",
    # "{{nome cognome}}"  ->  field = "nome cognome"
    "Doppia graffa {{campo}}": r"\{\{\s*([^}]+?)\s*\}\}",
    # "[nome cognome]"  ->  field = "nome cognome"
    "Parentesi quadra [campo]": r"\[\s*([^\]\[]+?)\s*\]",
    # "«nome cognome»"  ->  field = "nome cognome"
    "Guillemet «campo»": r"«\s*([^»]+?)\s*»",
}

DEFAULT_PRESET = "Etichetta «da compilare …»"


def get_pattern(preset_or_regex: str) -> re.Pattern:
    """Return a compiled pattern from a preset name or a raw regex string."""
    raw = PRESETS.get(preset_or_regex, preset_or_regex)
    return re.compile(raw)


def _norm_key(text: str) -> str:
    """Normalise a field description so equivalent labels collapse together."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    # Trim trailing sentence punctuation/quotes that isn't part of the label.
    return collapsed.strip(" .,;:\"'»«")


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_placeholders(template_path: str | Path, preset_or_regex: str) -> list[str]:
    """Return the ordered list of unique field descriptions in the template."""
    from docx import Document

    pattern = get_pattern(preset_or_regex)
    doc = Document(str(template_path))

    seen: dict[str, None] = {}
    for text in _iter_all_text(doc):
        for match in pattern.finditer(text):
            field = _norm_key(match.group(1))
            if field:
                seen.setdefault(field, None)

    return list(seen.keys())


def _iter_all_text(doc):
    """Yield the text of every paragraph in body, tables, headers and footers."""
    for para in _iter_paragraphs(doc):
        yield para.text


def _iter_paragraphs(doc):
    """Yield every ``Paragraph`` object anywhere in the document."""
    # Body paragraphs and tables.
    yield from _paragraphs_in_container(doc)
    # Header / footer of every section.
    for section in doc.sections:
        yield from _paragraphs_in_container(section.header)
        yield from _paragraphs_in_container(section.footer)


def _paragraphs_in_container(container):
    for para in getattr(container, "paragraphs", []):
        yield para
    for table in getattr(container, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                # Recurse: cells may contain nested tables.
                yield from _paragraphs_in_container(cell)


# ---------------------------------------------------------------------------
# Filling
# ---------------------------------------------------------------------------

def fill_template(
    template_path: str | Path,
    values: dict[str, str],
    output_path: str | Path,
    preset_or_regex: str,
) -> dict[str, int]:
    """Fill ``template_path`` with ``values`` and save to ``output_path``.

    ``values`` maps normalised field descriptions to their replacement text.
    Returns a dict {field: replacement_count} for reporting.
    """
    from docx import Document

    pattern = get_pattern(preset_or_regex)
    doc = Document(str(template_path))
    counts: dict[str, int] = {k: 0 for k in values}

    def replacer(match: re.Match) -> str:
        field = _norm_key(match.group(1))
        if field in values:
            counts[field] += 1
            return values[field]
        # Unknown placeholder: leave it untouched.
        return match.group(0)

    for para in _iter_paragraphs(doc):
        _replace_in_paragraph(para, pattern, replacer)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return counts


def _replace_in_paragraph(paragraph, pattern: re.Pattern, replacer):
    """Apply ``pattern``/``replacer`` to a paragraph, spanning runs if needed."""
    runs = paragraph.runs
    if not runs:
        return

    full_text = "".join(run.text for run in runs)
    if not pattern.search(full_text):
        return

    new_text = pattern.sub(replacer, full_text)
    if new_text == full_text:
        return

    # Put the whole replaced text in the first run and clear the others.
    # This keeps the first run's formatting for the placeholder region, which
    # is the pragmatic, widely used approach for run-split placeholders.
    runs[0].text = new_text
    for run in runs[1:]:
        run.text = ""
