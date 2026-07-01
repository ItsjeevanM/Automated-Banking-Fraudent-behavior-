"""
routes/reports.py
============================================================
FastAPI router — Job status + Report access endpoints.

Endpoints
---------
GET /jobs/{job_id}                         — poll analysis job status
GET /reports/                              — list all reports for user
GET /reports/{report_id}                   — full report detail
GET /reports/{report_id}/transactions      — paginated flagged transactions
GET /reports/{report_id}/download          — download scored CSV
============================================================
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from auth import get_current_user
from database import (
    get_flagged_transactions,
    get_job,
    get_report,
    get_user_reports,
)

logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────
# prefix="" so caller mounts this at app root;
# individual paths are /jobs/... and /reports/...
router = APIRouter(prefix="", tags=["reports"])


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _owned_job(job_id: str, user_id: str) -> dict:
    """
    Fetch a job and assert the requesting user owns it.

    Raises
    ------
    404  if the job doesn't exist.
    403  if the job belongs to a different user.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    if job["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job.",
        )
    return job


def _owned_report(report_id: str, user_id: str) -> dict:
    """
    Fetch a report and assert the requesting user owns it.

    Raises
    ------
    404  if the report doesn't exist or belongs to another user
         (get_report already filters by user_id).
    """
    report = get_report(report_id, user_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    return report


# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════

# ── GET /jobs/{job_id} ────────────────────────────────────────
@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Poll the status of an analysis job.

    Returns the progress percentage and current stage so the
    frontend can render a live progress bar.

    Stages: ``queued`` → ``ocr`` → ``scoring`` → ``llm`` → ``done`` | ``failed``
    """
    job = _owned_job(job_id, current_user["id"])

    return {
        "id":         job["id"],
        "status":     job["status"],
        "progress":   job["progress"],
        "error_msg":  job.get("error_msg"),
        "created_at": job["created_at"],
    }


# ── GET /reports/ ─────────────────────────────────────────────
@router.get("/reports/")
async def list_reports(
    current_user: dict = Depends(get_current_user),
):
    """
    List all fraud analysis reports belonging to the authenticated user.

    Returns a lightweight summary per report (no per-transaction data)
    suitable for rendering a report history table.
    """
    reports = get_user_reports(current_user["id"])

    return [
        {
            "id":             r["id"],
            "job_id":         r["job_id"],
            "total_txns":     r["total_txns"],
            "flagged_count":  r["flagged_count"],
            "avg_risk_score": r["avg_risk_score"],
            "amount_at_risk": r["amount_at_risk"],
            "created_at":     r["created_at"],
        }
        for r in reports
    ]


# ── GET /reports/{report_id} ──────────────────────────────────
@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieve the full fraud analysis report.

    Includes:
    - Portfolio-level summary (totals, risk distribution, etc.)
    - Attack episode clusters
    - LLM-generated narrative (or fallback portfolio summary text)
    - Scored CSV path (for the download endpoint)
    """
    report = _owned_report(report_id, current_user["id"])
    return report


# ── GET /reports/{report_id}/transactions ────────────────────
@router.get("/reports/{report_id}/transactions")
async def get_transactions(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=50, ge=1, le=500, description="Rows per page"),
    min_score: float = Query(default=0.0, ge=0.0, le=100.0,
                             description="Only return transactions with final_risk_score >= this value"),
):
    """
    Return paginated flagged transactions for a report.

    Transactions are pre-sorted by ``final_risk_score`` descending in the
    database query.  The ``min_score`` filter is applied after retrieval;
    because the DB query already limits results, pass a generous ``limit``
    if you also want a tight ``min_score`` filter.

    Query params
    ------------
    page      : page number, default 1
    limit     : rows per page, default 50, max 500
    min_score : only include rows with final_risk_score >= this value
    """
    # Ownership check — 404 if report doesn't belong to user
    _owned_report(report_id, current_user["id"])

    transactions = get_flagged_transactions(
        report_id=report_id,
        user_id=current_user["id"],
        page=page,
        limit=limit,
    )

    # Apply optional score filter (cheap, small result set)
    if min_score > 0.0:
        transactions = [
            t for t in transactions
            if (t.get("final_risk_score") or 0.0) >= min_score
        ]

    return {
        "transactions": transactions,
        "page":         page,
        "limit":        limit,
        "total":        len(transactions),
    }


# ── GET /reports/{report_id}/download ────────────────────────
@router.get("/reports/{report_id}/download")
async def download_report_csv(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Download the scored CSV file produced by the analysis pipeline.

    Returns a ``FileResponse`` with ``Content-Disposition: attachment``
    so the browser prompts a Save dialog.

    Raises 404 if the report or the CSV file on disk cannot be found.
    """
    report = _owned_report(report_id, current_user["id"])

    csv_path: str | None = report.get("scored_csv_path")

    if not csv_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No scored CSV is associated with this report.",
        )

    if not os.path.isfile(csv_path):
        logger.warning(
            "Scored CSV missing on disk for report %s — expected at %s",
            report_id, csv_path,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scored CSV file not found on disk.",
        )

    download_filename = f"fraud_report_{report_id[:8]}.csv"

    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename=download_filename,
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"'
        },
    )
