"""
routes/upload.py
============================================================
FastAPI router — File upload + background analysis pipeline.

Endpoints
---------
POST /upload   — upload a bank statement (PDF/CSV/image),
                 trigger async fraud analysis, return job_id
============================================================
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from auth import get_current_user
from database import (
    create_job,
    create_upload,
    save_report,
    update_job,
    update_upload_status,
)

logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────
router = APIRouter(prefix="/upload", tags=["upload"])

# ── Upload constraints ────────────────────────────────────────
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "text/csv",
    "image/png",
    "image/jpeg",
}

# Extension derived from MIME (used for renaming the saved file)
MIME_TO_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    "text/csv":        "csv",
    "image/png":       "png",
    "image/jpeg":      "jpg",
}

MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

# Base directory for all uploads (relative to backend root)
UPLOAD_BASE_DIR: str = "uploads"


# ══════════════════════════════════════════════════════════════
# LAZY IMPORTS — optional heavy dependencies
# These are imported inside the background task so that the
# server still starts even if OCR / ML libs are not installed.
# ══════════════════════════════════════════════════════════════

def _import_quick_run():
    """Return the quick_run function from the unified fraud engine."""
    from services.unified_fraud_engine import quick_run  # noqa: PLC0415
    return quick_run


def _import_llm_summarizer():
    """
    Return LLMSummarizer if available, otherwise return None.
    Falls back to llm_sender.build_llm_payload for the text.
    """
    try:
        # pyrefly: ignore [missing-import]
        from llm_summarizer import LLMSummarizer  # noqa: PLC0415
        return LLMSummarizer
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════
# BACKGROUND TASK
# ══════════════════════════════════════════════════════════════

async def run_analysis(
    job_id: str,
    upload_id: str,
    user_id: str,
    file_path: str,
    file_type: str,
) -> None:
    """
    Full ML analysis pipeline executed as a FastAPI BackgroundTask.

    Stages
    ------
    1.  OCR / CSV ingestion     → DataFrame          (progress 10%)
    2.  Fraud scoring           → FraudResult        (progress 40%)
    3.  LLM narrative           → str                (progress 75%)
    4.  Save report + CSV       → report_id          (progress 100%)

    Any unhandled exception marks the job as "failed".
    """
    try:
        # ── Stage 1: ingest ──────────────────────────────────
        update_job(job_id, "ocr", 10)

        loop = asyncio.get_event_loop()

        if file_type == "pdf":
            # Convert PDF → CSV via pdfplumber, then load the CSV
            from services.pdf_reader import convert as pdf_to_csv  # noqa: PLC0415
            csv_path_from_pdf = await loop.run_in_executor(
                None, lambda: pdf_to_csv(file_path, UPLOAD_BASE_DIR)
            )
            df: pd.DataFrame = await loop.run_in_executor(
                None, lambda: pd.read_csv(csv_path_from_pdf)
            )

        elif file_type in ("png", "jpg", "jpeg"):
            # Convert image → CSV via Tesseract OCR, then load the CSV
            from services.ocr_extractor_local import convert as img_to_csv  # noqa: PLC0415
            csv_path_from_img = await loop.run_in_executor(
                None, lambda: img_to_csv(file_path, UPLOAD_BASE_DIR)
            )
            df = await loop.run_in_executor(
                None, lambda: pd.read_csv(csv_path_from_img)
            )

        else:
            # Plain CSV — read directly
            df = await loop.run_in_executor(
                None, lambda: pd.read_csv(file_path, encoding="utf-8", encoding_errors="replace")
            )

        # ── Stage 2: fraud scoring ────────────────────────────
        update_job(job_id, "scoring", 40)

        quick_run = _import_quick_run()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: quick_run(df))

        # ── Stage 3: LLM narrative ────────────────────────────
        update_job(job_id, "llm", 75)

        llm_text: str = ""
        LLMSummarizer = _import_llm_summarizer()

        if LLMSummarizer is not None:
            try:
                llm_text = await loop.run_in_executor(
                    None,
                    lambda: LLMSummarizer().generate_report(
                        result.llm_prompt, result.portfolio_summary
                    ),
                )
            except Exception as llm_err:
                logger.warning("LLM summarizer failed, using portfolio summary: %s", llm_err)
                llm_text = str(result.portfolio_summary)
        else:
            # Graceful fallback: stringify the portfolio summary
            llm_text = str(result.portfolio_summary)

        # ── Stage 4: persist results ──────────────────────────
        os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)
        csv_path = os.path.join(UPLOAD_BASE_DIR, f"{job_id}_scored.csv")

        await loop.run_in_executor(
            None, lambda: result.scored_df.to_csv(csv_path, index=False)
        )

        save_report(job_id, user_id, result, llm_text, csv_path)
        update_job(job_id, "done", 100)
        update_upload_status(upload_id, "done")

        logger.info("Job %s completed successfully.", job_id)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        update_job(job_id, "failed", 0, str(exc))
        update_upload_status(upload_id, "failed")


# ══════════════════════════════════════════════════════════════
# UPLOAD ENDPOINT
# ══════════════════════════════════════════════════════════════

@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a bank statement file and kick off the fraud analysis pipeline.

    **Allowed types**: PDF, CSV, PNG, JPEG  
    **Max size**: 50 MB  
    MIME type is validated from the ``Content-Type`` header, not the file
    extension, to prevent trivial bypass.

    Returns **202 Accepted** immediately; poll ``GET /jobs/{job_id}``
    for progress.
    """
    user_id: str = current_user["id"]

    # ── MIME validation ───────────────────────────────────────
    content_type: str = file.content_type or ""
    # Strip optional parameters (e.g. "text/csv; charset=utf-8" → "text/csv")
    mime_base = content_type.split(";")[0].strip().lower()

    if mime_base not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type '{mime_base}' is not supported. "
                f"Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
            ),
        )

    # ── Read file into memory for size check ──────────────────
    file_bytes: bytes = await file.read()
    file_size: int = len(file_bytes)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 50 MB limit ({file_size / 1_048_576:.1f} MB received).",
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # ── Build save path ───────────────────────────────────────
    ext: str = MIME_TO_EXT[mime_base]
    new_filename: str = f"{uuid.uuid4()}.{ext}"
    user_upload_dir: str = os.path.join(UPLOAD_BASE_DIR, user_id)

    os.makedirs(user_upload_dir, exist_ok=True)
    saved_path: str = os.path.join(user_upload_dir, new_filename)

    # ── Write to disk ─────────────────────────────────────────
    try:
        with open(saved_path, "wb") as fh:
            fh.write(file_bytes)
    except OSError as exc:
        logger.error("Failed to write upload to disk: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the uploaded file. Please try again.",
        )

    # ── Database records ──────────────────────────────────────
    original_filename: str = file.filename or new_filename

    upload_id: str = create_upload(
        user_id=user_id,
        filename=original_filename,
        file_path=saved_path,
        file_type=mime_base,
        file_size=file_size,
    )

    job_id: str = create_job(upload_id=upload_id, user_id=user_id)

    # ── Kick off background analysis ──────────────────────────
    background_tasks.add_task(
        run_analysis,
        job_id=job_id,
        upload_id=upload_id,
        user_id=user_id,
        file_path=saved_path,
        file_type=ext,          # "pdf" | "csv" | "png" | "jpg"
    )

    logger.info(
        "Upload accepted — user=%s upload_id=%s job_id=%s file=%s size=%d bytes",
        user_id, upload_id, job_id, original_filename, file_size,
    )

    return {
        "job_id": job_id,
        "upload_id": upload_id,
        "message": "File uploaded, analysis started",
    }
