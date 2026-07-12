"""FastAPI backend for GLM-OCR PDF-to-Markdown web application."""

import asyncio
import json
import os
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.ocr import check_ollama_status, ocr_page
from backend.pdf_utils import convert_single_page, pdf_page_count, pdf_to_images

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JOBS_BASE = Path("/tmp/glm_ocr_jobs")
MAX_UPLOAD_MB = 200

# In-memory job registry  {job_id: {meta}}
JOBS: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="GLM-OCR", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Clean up leftover temp jobs from previous runs."""
    if JOBS_BASE.exists():
        shutil.rmtree(JOBS_BASE)
    JOBS_BASE.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def job_dir(job_id: str) -> Path:
    return JOBS_BASE / job_id


def pages_dir(job_id: str) -> Path:
    return job_dir(job_id) / "pages"


def ocr_dir(job_id: str) -> Path:
    return job_dir(job_id) / "ocr"


def page_image_path(job_id: str, page_num: int) -> Path:
    return pages_dir(job_id) / f"page_{page_num:04d}.png"


def ocr_path(job_id: str, page_num: int) -> Path:
    return ocr_dir(job_id) / f"page_{page_num:04d}.md"


def get_job_or_404(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]


def validate_page(job: dict, page_num: int):
    if page_num < 1 or page_num > job["page_count"]:
        raise HTTPException(
            status_code=400,
            detail=f"Page {page_num} out of range (1–{job['page_count']})",
        )


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    """Check Ollama reachability and glm-ocr model availability."""
    status = await check_ollama_status()
    return status


@app.get("/api/jobs")
async def list_jobs():
    """Return metadata for all recent jobs."""
    return list(JOBS.values())


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accept a PDF upload, convert all pages to preview PNGs, and return job info.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    job_id = str(uuid.uuid4())
    jdir = job_dir(job_id)
    pdir = pages_dir(job_id)
    odir = ocr_dir(job_id)
    jdir.mkdir(parents=True)
    pdir.mkdir()
    odir.mkdir()

    # Save uploaded PDF
    pdf_path = jdir / "original.pdf"
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")
    pdf_path.write_bytes(content)

    # Convert to preview images (150 DPI)
    try:
        image_paths = pdf_to_images(str(pdf_path), str(pdir), dpi=150)
    except Exception as exc:
        shutil.rmtree(jdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"PDF conversion failed: {exc}")

    page_count = len(image_paths)

    job_meta = {
        "job_id": job_id,
        "filename": file.filename,
        "page_count": page_count,
        "created_at": datetime.utcnow().isoformat(),
        "page_status": {str(i): "pending" for i in range(1, page_count + 1)},
    }
    JOBS[job_id] = job_meta

    return {"job_id": job_id, "page_count": page_count, "filename": file.filename}


@app.get("/api/page/{job_id}/{page_num}")
async def get_page_image(job_id: str, page_num: int):
    """Return the preview PNG for a given page."""
    job = get_job_or_404(job_id)
    validate_page(job, page_num)
    img_path = page_image_path(job_id, page_num)
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Page image not found")
    return FileResponse(str(img_path), media_type="image/png")


@app.post("/api/ocr/{job_id}/{page_num}")
async def ocr_single_page(job_id: str, page_num: int):
    """Run GLM-OCR on a single page and return + save the Markdown."""
    job = get_job_or_404(job_id)
    validate_page(job, page_num)

    # Update status
    job["page_status"][str(page_num)] = "processing"

    # Use OCR-quality image (200 DPI). Convert on demand if not yet done.
    jdir = job_dir(job_id)
    pdf_path = jdir / "original.pdf"
    odir = ocr_dir(job_id)

    # High-res image for OCR
    ocr_img_path = jdir / f"ocr_page_{page_num:04d}.png"
    if not ocr_img_path.exists():
        try:
            path = convert_single_page(str(pdf_path), page_num, str(jdir), dpi=200)
            ocr_img_path = Path(path)
        except Exception as exc:
            job["page_status"][str(page_num)] = "error"
            raise HTTPException(status_code=500, detail=f"Image conversion failed: {exc}")

    try:
        markdown = await ocr_page(str(ocr_img_path))
        md_path = ocr_path(job_id, page_num)
        md_path.write_text(markdown, encoding="utf-8")
        job["page_status"][str(page_num)] = "done"
        return {"page_num": page_num, "markdown": markdown}
    except Exception as exc:
        job["page_status"][str(page_num)] = "error"
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}")


@app.put("/api/ocr/{job_id}/{page_num}")
async def save_markdown(job_id: str, page_num: int, body: dict):
    """Save edited markdown for a page back to disk."""
    job = get_job_or_404(job_id)
    validate_page(job, page_num)

    markdown = body.get("markdown", "")
    md_path = ocr_path(job_id, page_num)
    md_path.write_text(markdown, encoding="utf-8")
    job["page_status"][str(page_num)] = "done"
    return {"saved": True, "page_num": page_num}


@app.get("/api/ocr/{job_id}/{page_num}")
async def get_markdown(job_id: str, page_num: int):
    """Return saved markdown for a page, if any."""
    job = get_job_or_404(job_id)
    validate_page(job, page_num)
    md_path = ocr_path(job_id, page_num)
    if not md_path.exists():
        return {"page_num": page_num, "markdown": None}
    return {"page_num": page_num, "markdown": md_path.read_text(encoding="utf-8")}


@app.post("/api/ocr/{job_id}/all")
async def ocr_all_pages(job_id: str):
    """
    Process all pages sequentially and stream progress as Server-Sent Events.
    Each event is a JSON object: {page_num, total, status, markdown?, error?}
    """
    job = get_job_or_404(job_id)
    total = job["page_count"]
    jdir = job_dir(job_id)
    pdf_path = jdir / "original.pdf"

    async def event_generator():
        for page_num in range(1, total + 1):
            job["page_status"][str(page_num)] = "processing"
            yield f"data: {json.dumps({'page_num': page_num, 'total': total, 'status': 'processing'})}\n\n"

            ocr_img_path = jdir / f"ocr_page_{page_num:04d}.png"
            if not ocr_img_path.exists():
                try:
                    path = convert_single_page(str(pdf_path), page_num, str(jdir), dpi=200)
                    ocr_img_path = Path(path)
                except Exception as exc:
                    job["page_status"][str(page_num)] = "error"
                    yield f"data: {json.dumps({'page_num': page_num, 'total': total, 'status': 'error', 'error': str(exc)})}\n\n"
                    continue

            try:
                markdown = await ocr_page(str(ocr_img_path))
                md_path = ocr_path(job_id, page_num)
                md_path.write_text(markdown, encoding="utf-8")
                job["page_status"][str(page_num)] = "done"
                yield f"data: {json.dumps({'page_num': page_num, 'total': total, 'status': 'done', 'markdown': markdown})}\n\n"
            except Exception as exc:
                job["page_status"][str(page_num)] = "error"
                yield f"data: {json.dumps({'page_num': page_num, 'total': total, 'status': 'error', 'error': str(exc)})}\n\n"

        yield f"data: {json.dumps({'page_num': 0, 'total': total, 'status': 'complete'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Remove a job and its files."""
    get_job_or_404(job_id)
    shutil.rmtree(job_dir(job_id), ignore_errors=True)
    del JOBS[job_id]
    return {"deleted": True, "job_id": job_id}


# ---------------------------------------------------------------------------
# Static frontend — must be mounted LAST so API routes take priority
# ---------------------------------------------------------------------------

_base_dir = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent
_frontend_dir = _base_dir / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
