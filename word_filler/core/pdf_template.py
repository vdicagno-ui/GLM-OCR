"""Fill fillable PDF forms (AcroForm), keeping the output editable.

A PDF template is a form whose fields are identified either by:
  * the placeholder text held in the field value, e.g. "[da compilare nome e
    cognome]"  (same convention as the Word templates), or
  * the field's own name, e.g. a field named "giudice delegato".

The output keeps the form fields (still editable) with the extracted values
written in, and NeedAppearances set so every PDF viewer renders them.
"""

from __future__ import annotations

from pathlib import Path

from .template import _norm_key, get_pattern


def _field_key(name: str, value, pattern) -> str:
    """Field identifier: from a "[...]" placeholder in the value, else the name."""
    if value:
        m = pattern.search(str(value))
        if m:
            return _norm_key(m.group(1))
    # Fall back to the field's own name (treat _/- as word separators).
    return _norm_key(str(name).replace("_", " ").replace("-", " "))


def _text_fields(reader) -> dict:
    """Return {field_name: field} for the form's fillable fields."""
    fields = reader.get_fields() or {}
    out = {}
    for name, f in fields.items():
        ftype = f.get("/FT")
        # Text fields (/Tx) and, permissively, fields without a declared type.
        if ftype in (None, "/Tx"):
            out[name] = f
    return out


def scan_pdf_fields(template_path: str | Path, preset_or_regex: str) -> list[str]:
    """Return the ordered list of unique field descriptions in a PDF form."""
    from pypdf import PdfReader

    pattern = get_pattern(preset_or_regex)
    reader = PdfReader(str(template_path))
    seen: dict[str, None] = {}
    for name, f in _text_fields(reader).items():
        value = f.get("/V") or f.get("/DV") or ""
        key = _field_key(name, value, pattern)
        if key:
            seen.setdefault(key, None)
    return list(seen.keys())


def fill_pdf_form(
    template_path: str | Path,
    values: dict[str, str],
    output_path: str | Path,
    preset_or_regex: str,
    flatten: bool = False,
) -> dict[str, int]:
    """Fill a PDF form with ``values`` and save to ``output_path``.

    ``values`` maps normalised field descriptions to replacement text. Returns
    {field: number_of_pdf_fields_filled} for reporting. The output stays
    editable unless ``flatten`` is True.
    """
    from pypdf import PdfReader, PdfWriter

    pattern = get_pattern(preset_or_regex)
    reader = PdfReader(str(template_path))

    # Map each PDF field NAME to the value to write, via its normalised key.
    to_set: dict[str, str] = {}
    counts: dict[str, int] = {k: 0 for k in values}
    for name, f in _text_fields(reader).items():
        value = f.get("/V") or f.get("/DV") or ""
        key = _field_key(name, value, pattern)
        if key in values:
            to_set[name] = values[key]
            counts[key] += 1

    writer = PdfWriter()
    writer.append(reader)

    for page in writer.pages:
        try:
            writer.update_page_form_field_values(
                page, to_set, auto_regenerate=False, flatten=flatten
            )
        except TypeError:
            # Older pypdf without the flatten kwarg.
            writer.update_page_form_field_values(page, to_set, auto_regenerate=False)
        except Exception:
            # A page without the target fields raises; ignore and continue.
            pass

    if not flatten:
        # Ask viewers to (re)build field appearances so values are visible.
        try:
            writer.set_need_appearances_writer(True)
        except Exception:
            pass

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        writer.write(fh)
    return counts
