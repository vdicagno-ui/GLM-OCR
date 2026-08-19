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
        text = guides.read_guide_text(guide_path)
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
            return result
        except Exception as exc:
            # AI failed: keep going with the heuristic and report why.
            result.error = str(exc)

    result.values = extractor.heuristic_extract(text, fields)
    return result


def build_output_path(guide_path: str, cfg: dict) -> Path:
    guide = Path(guide_path)
    suffix = cfg.get("output_suffix") or "_compilato"
    out_dir = cfg.get("output_dir", "").strip()
    base_dir = Path(out_dir) if out_dir else guide.parent
    return base_dir / f"{guide.stem}{suffix}.docx"


def generate_output(
    template_path: str,
    values: dict[str, str],
    guide_path: str,
    cfg: dict,
) -> Path:
    """Fill the template with ``values`` and write the output document."""
    out_path = build_output_path(guide_path, cfg)
    template.fill_template(
        template_path=template_path,
        values=values,
        output_path=out_path,
        preset_or_regex=resolve_pattern(cfg),
    )
    return out_path
