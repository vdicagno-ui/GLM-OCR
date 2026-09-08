"""High-level orchestration used by the GUI.

Keeps the Tk layer thin: given a template, a guide file and settings, produce
the extracted values (AI or heuristic) and, once approved, the filled output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import extractor, guides, template


@dataclass
class ExtractionResult:
    guide_path: str
    values: dict[str, str] = field(default_factory=dict)
    used_ai: bool = False
    error: str | None = None


def resolve_pattern(cfg: dict) -> str:
    """Return the preset name or the custom regex per current settings."""
    if cfg.get("use_custom_regex") and cfg.get("custom_regex", "").strip():
        return cfg["custom_regex"].strip()
    return cfg.get("preset", template.DEFAULT_PRESET)


def scan_template_fields(template_path: str, cfg: dict) -> list[str]:
    return template.scan_placeholders(template_path, resolve_pattern(cfg))


def extract_for_guide(
    guide_path: str,
    fields: list[str],
    cfg: dict,
) -> ExtractionResult:
    """Read a guide file and extract values for ``fields`` (AI or heuristic)."""
    result = ExtractionResult(guide_path=guide_path)
    try:
        text = guides.read_guide_text(
            guide_path, first_page_only=bool(cfg.get("first_page_only", True))
        )
    except Exception as exc:
        result.error = f"Lettura file guida fallita: {exc}"
        result.values = {f: "" for f in fields}
        return result

    if cfg.get("use_ai"):
        try:
            result.values = extractor.ai_extract(
                base_url=cfg["endpoint"],
                model=cfg.get("model") or "local-model",
                guide_text=text,
                fields=fields,
            )
            result.used_ai = True
        except Exception as exc:
            # AI failed: keep going with the heuristic and report why.
            result.error = str(exc)
            result.values = extractor.heuristic_extract(text, fields)
    else:
        result.values = extractor.heuristic_extract(text, fields)

    # Judge fields (giudice delegato/delegante) are named only by title in some
    # documents; resolve them deterministically from context cues and let the
    # result override the weaker AI/heuristic guess when a name is found.
    if cfg.get("resolve_judges", True):
        result.values = extractor.resolve_judge_fields(text, fields, result.values)

    return result


def build_output_path(guide_path: str, cfg: dict, template_path: str = "") -> Path:
    guide = Path(guide_path)
    suffix = cfg.get("output_suffix") or "_compilato"
    out_dir = cfg.get("output_dir", "").strip()
    base_dir = Path(out_dir) if out_dir else guide.parent
    # Output format follows the template: PDF form -> .pdf, otherwise .docx.
    ext = ".pdf" if template.is_pdf(template_path) else ".docx"
    return base_dir / f"{guide.stem}{suffix}{ext}"


def generate_output(
    template_path: str,
    values: dict[str, str],
    guide_path: str,
    cfg: dict,
) -> Path:
    """Fill the template with ``values`` and write the output document."""
    out_path = build_output_path(guide_path, cfg, template_path)
    template.fill_template(
        template_path=template_path,
        values=values,
        output_path=out_path,
        preset_or_regex=resolve_pattern(cfg),
        flatten=bool(cfg.get("flatten_pdf", False)),
    )
    return out_path
