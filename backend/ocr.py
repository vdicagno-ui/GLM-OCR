"""GLM-OCR integration via Ollama's OpenAI-compatible API."""

import base64
import httpx

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "glm-ocr"
OCR_PROMPT = (
    "Convert the image content to Markdown format, preserving original formatting "
    "including tables, headings, lists, and any other structural elements. "
    "Output only the Markdown content."
)


async def ocr_page(image_path: str) -> str:
    """Send a page image to GLM-OCR via Ollama and return the Markdown string."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def check_ollama_status() -> dict:
    """
    Check whether Ollama is reachable and whether glm-ocr is available.
    Returns dict with keys: ollama_reachable (bool), model_available (bool), error (str|None).
    """
    result = {"ollama_reachable": False, "model_available": False, "error": None}

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            result["ollama_reachable"] = True

            tags = resp.json()
            models = [m.get("name", "") for m in tags.get("models", [])]
            # Accept "glm-ocr" or "glm-ocr:latest" etc.
            result["model_available"] = any(
                m == MODEL_NAME or m.startswith(MODEL_NAME + ":") for m in models
            )
    except httpx.ConnectError:
        result["error"] = "Cannot connect to Ollama at " + OLLAMA_URL
    except Exception as exc:
        result["error"] = str(exc)

    return result
