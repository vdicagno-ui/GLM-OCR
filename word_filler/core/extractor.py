"""Extract field values from a guide document using a LOCAL AI model.

Talks to any OpenAI-compatible ``/v1/chat/completions`` endpoint, which covers
the two most common offline setups:

* LM Studio            -> http://localhost:1234/v1
* Ollama               -> http://localhost:11434/v1

Everything stays on the machine: no data ever leaves the local network.

There is also a dependency-free heuristic fallback (``heuristic_extract``) for
when no AI server is available, so the tool still produces a best-effort result
that the user can correct in the review step.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

DEFAULT_ENDPOINTS = {
    "LM Studio (localhost:1234)": "http://localhost:1234/v1",
    "Ollama (localhost:11434)": "http://localhost:11434/v1",
}

SYSTEM_PROMPT = (
    "Sei un assistente che estrae dati da un documento, in ambito giuridico. "
    "Ricevi il testo di un documento guida e un elenco di campi da compilare. "
    "Per ogni campo, individua nel documento il valore corrispondente, "
    "leggendo TUTTO il testo, anche in fondo. "
    "Attenzione ai campi con nomi molto simili: trattali come DISTINTI e non "
    "confonderli (per esempio «giudice delegato» e «giudice delegante», oppure "
    "«ricorrente» e «resistente»); assegna a ciascuno il valore giusto. "
    "Considera le abbreviazioni comuni (es. «G.D.» = giudice delegato, "
    "«Dott.»/«Dott.ssa» davanti a un nome, «R.G.» = numero di ruolo generale). "
    "Non inventare dati: se nel documento è indicato un unico giudice senza "
    "delega, valorizza solo il campo del giudice effettivamente presente e "
    "lascia vuoto l'altro. "
    "Rispondi ESCLUSIVAMENTE con un oggetto JSON valido che mappa il nome "
    "esatto di ogni campo (come fornito) al valore estratto (stringa). "
    "Se un valore non è davvero presente nel documento, usa una stringa vuota. "
    "Non aggiungere spiegazioni, commenti o testo fuori dal JSON."
)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Local calls must bypass any system proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_connection(base_url: str, timeout: int = 8) -> tuple[bool, str, list[str]]:
    """Return (ok, message, model_names) for an OpenAI-compatible server."""
    base_url = base_url.rstrip("/")
    try:
        data = _get_json(f"{base_url}/models", timeout=timeout)
        models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        if models:
            return True, f"Connesso. Modelli disponibili: {len(models)}.", models
        return True, "Connesso, ma nessun modello caricato.", []
    except urllib.error.URLError as exc:
        return False, f"Impossibile connettersi a {base_url}: {exc.reason}", []
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Errore: {exc}", []


# ---------------------------------------------------------------------------
# AI extraction
# ---------------------------------------------------------------------------

def ai_extract(
    base_url: str,
    model: str,
    guide_text: str,
    fields: list[str],
    timeout: int = 180,
    max_chars: int = 40000,
) -> dict[str, str]:
    """Ask the local model to extract ``fields`` from ``guide_text``.

    Returns a dict {field: value}. Missing fields come back as empty strings.
    Raises RuntimeError on transport / parsing problems so the caller can fall
    back or surface the error.
    """
    base_url = base_url.rstrip("/")
    # Guard against oversized context. Identifying data (names, judges, dates)
    # can appear either at the top OR at the very end of a decree, so when the
    # document is too long we keep both the head and the tail rather than only
    # the beginning.
    text = guide_text.strip()
    if len(text) > max_chars:
        head = text[: int(max_chars * 0.7)]
        tail = text[-int(max_chars * 0.3):]
        text = f"{head}\n[...]\n{tail}"

    fields_block = "\n".join(f"- {f}" for f in fields)
    user_prompt = (
        f"CAMPI DA ESTRARRE:\n{fields_block}\n\n"
        f"DOCUMENTO GUIDA:\n\"\"\"\n{text}\n\"\"\"\n\n"
        "Restituisci solo il JSON con i campi elencati sopra come chiavi."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "stream": False,
    }

    try:
        resp = _post_json(f"{base_url}/chat/completions", payload, timeout=timeout)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connessione AI fallita: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Chiamata AI fallita: {exc}") from exc

    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Risposta AI non valida: {resp}") from exc

    parsed = _parse_json_object(content)
    # Normalise: guarantee every requested field is present.
    result: dict[str, str] = {}
    for field in fields:
        value = parsed.get(field, "")
        result[field] = "" if value is None else str(value).strip()
    return result


def _parse_json_object(content: str) -> dict:
    """Extract the first JSON object from a model reply, tolerating extra text."""
    content = content.strip()
    # Strip common ```json ... ``` fences.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, re.DOTALL)
    if fence:
        content = fence.group(1).strip()

    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Fallback: grab the outermost {...} block.
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(content[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    raise RuntimeError("La risposta AI non contiene un JSON valido.")


# ---------------------------------------------------------------------------
# Offline heuristic fallback (no AI)
# ---------------------------------------------------------------------------

def heuristic_extract(guide_text: str, fields: list[str]) -> dict[str, str]:
    """Best-effort extraction without AI: look for 'label: value' style lines.

    For each field it searches for a line whose start resembles the field name
    and returns the text after the ':' separator. Always returns every field
    (empty string when nothing is found) so the review table stays complete.
    """
    lines = [ln.strip() for ln in guide_text.splitlines() if ln.strip()]
    result: dict[str, str] = {f: "" for f in fields}

    for field in fields:
        # Build a loose token set from the field description.
        tokens = [t for t in re.split(r"\s+", field.lower()) if len(t) > 1]
        if not tokens:
            continue
        best = ""
        for line in lines:
            low = line.lower()
            if all(tok in low for tok in tokens) and ":" in line:
                candidate = line.split(":", 1)[1].strip()
                if candidate:
                    best = candidate
                    break
        result[field] = best

    return result
