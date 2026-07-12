"""Desktop launcher for GLM-OCR: runs the FastAPI backend in-process and
opens it in a native window via pywebview, so the app behaves like a
regular desktop program instead of a browser-hosted server."""

import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app  # noqa: E402

HOST = "127.0.0.1"
WINDOW_TITLE = "GLM-OCR — PDF to Markdown"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _run_server(port: int) -> None:
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    port = _find_free_port()
    threading.Thread(target=_run_server, args=(port,), daemon=True).start()

    if not _wait_for_server(port):
        raise RuntimeError("GLM-OCR server did not start in time")

    webview.create_window(
        WINDOW_TITLE,
        f"http://{HOST}:{port}",
        width=1280,
        height=860,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
