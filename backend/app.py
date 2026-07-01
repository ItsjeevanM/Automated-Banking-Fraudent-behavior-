"""
app.py
============================================================
Main FastAPI application — Bank Fraud Detection API.

Responsibility: create the ASGI app, register middleware,
include routers, handle startup side-effects, and provide
a global safety net for unexpected exceptions.

All business logic lives in the route modules (routes/) and
service modules (services/).

Run with:
    python main.py          (uses uvicorn.run inside main.py)
    uvicorn app:app --reload
============================================================
"""

import io
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── Load .env before anything that reads os.getenv ───────────
load_dotenv()

# ── Application-level logger ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Routers ───────────────────────────────────────────────────
from routes.auth import router as auth_router        # noqa: E402
from routes.upload import router as upload_router    # noqa: E402
from routes.reports import router as reports_router  # noqa: E402

# ── Database helpers (called on startup) ──────────────────────
from database import clean_expired_tokens, create_database  # noqa: E402


# ══════════════════════════════════════════════════════════════
# REQUEST SIZE LIMIT MIDDLEWARE  (50 MB hard cap)
# ══════════════════════════════════════════════════════════════

MAX_REQUEST_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Reject any request whose Content-Length header exceeds
    MAX_REQUEST_SIZE_BYTES before reading the body.

    This is a fast, early-exit guard that prevents the server
    from buffering enormous payloads into memory.
    """

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > MAX_REQUEST_SIZE_BYTES:
                logger.warning(
                    "Request from %s rejected — Content-Length %d bytes exceeds %d-byte limit.",
                    request.client.host if request.client else "unknown",
                    size,
                    MAX_REQUEST_SIZE_BYTES,
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body too large "
                            f"({size / 1_048_576:.1f} MB). "
                            f"Maximum allowed size is 50 MB."
                        )
                    },
                )
        return await call_next(request)


# ══════════════════════════════════════════════════════════════
# LIFESPAN — startup / shutdown events
# ══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once at startup (before serving requests) and once at
    shutdown (after the last request is handled).

    Startup tasks
    -------------
    1. Initialise / migrate SQLite database tables.
    2. Purge expired rows from the token blocklist.
    3. Ensure the uploads/ directory exists on disk.
    """
    # ── Startup ───────────────────────────────────────────────
    logger.info("=== Bank Fraud Detection API — STARTING UP ===")

    # 1. Create all tables (idempotent — safe to call every boot)
    try:
        create_database()
        logger.info("Database initialised.")
    except Exception as exc:
        logger.error("Failed to initialise database: %s", exc)
        raise

    # 2. Purge tokens that have already expired (keep blocklist lean)
    try:
        clean_expired_tokens()
        logger.info("Expired tokens cleaned from blocklist.")
    except Exception as exc:
        logger.warning("Could not clean expired tokens: %s", exc)

    # 3. Ensure uploads directory exists
    upload_dir: str = os.getenv("UPLOAD_DIR", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    logger.info("Upload directory ready: %s", os.path.abspath(upload_dir))

    logger.info("=== Bank Fraud Detection API — READY ===")

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────
    logger.info("=== Bank Fraud Detection API — SHUTTING DOWN ===")


# ══════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Bank Fraud Detection API",
    version="1.0.0",
    description=(
        "REST API for uploading bank statements, running the ML fraud "
        "detection pipeline, and retrieving analysis reports."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ══════════════════════════════════════════════════════════════
# MIDDLEWARE  (order matters — added top-to-bottom, executed inner-to-outer)
# ══════════════════════════════════════════════════════════════

# 1. CORS — must be first so pre-flight OPTIONS requests are handled
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev server
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 2. Request size guard — reject oversized bodies early
app.add_middleware(RequestSizeLimitMiddleware)


# ══════════════════════════════════════════════════════════════
# ROUTERS
# ══════════════════════════════════════════════════════════════

app.include_router(auth_router)     # /auth/register, /auth/login, …
app.include_router(upload_router)   # /upload
app.include_router(reports_router)  # /jobs/{job_id}, /reports/…


# ══════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════

@app.get("/health", tags=["meta"])
async def health_check():
    """
    Lightweight liveness probe.

    Returns ``200 OK`` with a JSON body containing:
    - ``status``    : always ``"ok"``
    - ``timestamp`` : current UTC time in ISO-8601 format
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# GLOBAL EXCEPTION HANDLER
# ══════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for any unhandled exception that escapes a route handler.

    - Logs the full traceback server-side (so it's visible in logs).
    - Returns a generic 500 response to the client so internal details
      are never exposed to the end user.
    """
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


# ══════════════════════════════════════════════════════════════
# POST /api/analyze
# ══════════════════════════════════════════════════════════════

@app.post("/api/analyze", tags=["analysis"])
async def analyze(file: UploadFile = File(...)):
    """
    Accept a CSV bank-statement upload, run the full analytics → risk →
    LLM pipeline, and return a single JSON payload shaped for the
    frontend dashboard.

    Pipeline order
    --------------
    1. pd.read_csv()
    2. normalizer.standardize_dataframe(df)  → standardised DataFrame
    3. analytics.generate_chart_data(df) + generate_analytics_report(df)
    4. risk_engine.RiskEngine(df).run()       (wrapped in try/except)
    5. llm_sender.run(df, merged_report)
    6. cloud_gemini.run(df, merged_report)    (wrapped in try/except)

    Returns the JSON shape the frontend expects exactly.
    """
    # ── Lazy imports (keep module-level clean) ────────────────────────────
    from services import normalizer as normalizer_svc
    from services import analytics as analytics_svc
    from services import risk_engine as risk_engine_svc
    from services import llm_sender as llm_sender_svc
    from services import cloud_gemini as cloud_gemini_svc
    from services import cashflow_predictor as cashflow_predictor_svc

    # ── 1. Ingest file (CSV / PDF / image) ───────────────────────────────
    raw_bytes = await file.read()

    # Detect file type from magic bytes so we never blindly pd.read_csv binary data
    _UPLOAD_TMP = "uploads"
    os.makedirs(_UPLOAD_TMP, exist_ok=True)

    # Magic-byte signatures
    _is_pdf  = raw_bytes[:4] == b"%PDF"
    _is_png  = raw_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    _is_jpeg = raw_bytes[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1")

    try:
        if _is_pdf:
            # Save to a temp file, convert with pdfplumber → CSV, then read
            import tempfile, uuid as _uuid
            from services.pdf_reader import convert as _pdf_to_csv
            with tempfile.NamedTemporaryFile(suffix=".pdf", dir=_UPLOAD_TMP, delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            csv_path = _pdf_to_csv(tmp_path, _UPLOAD_TMP)
            df_raw = pd.read_csv(csv_path)

        elif _is_png or _is_jpeg:
            # Save to a temp file, run Tesseract OCR → CSV, then read
            import tempfile
            from services.ocr_extractor_local import convert as _img_to_csv
            _ext = ".png" if _is_png else ".jpg"
            with tempfile.NamedTemporaryFile(suffix=_ext, dir=_UPLOAD_TMP, delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            csv_path = _img_to_csv(tmp_path, _UPLOAD_TMP)
            df_raw = pd.read_csv(csv_path)

        else:
            # Treat as CSV; try UTF-8 first, fall back to latin-1
            try:
                df_raw = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8")
            except UnicodeDecodeError:
                df_raw = pd.read_csv(io.BytesIO(raw_bytes), encoding="latin-1")

    except Exception as exc:
        logger.error("analyze: file parse failed: %s", exc)
        return JSONResponse(status_code=400, content={"detail": f"Could not parse file: {exc}"})

    # ── 2. Normalise ──────────────────────────────────────────────────────
    records = normalizer_svc.standardize_dataframe(df_raw)
    df = pd.DataFrame(records)

    # ── 3. Analytics ──────────────────────────────────────────────────────
    charts = analytics_svc.generate_chart_data(df)
    analytics_report = analytics_svc.generate_analytics_report(df)
    stats = analytics_report.get("statistics", {})

    # Build partial merged_report so downstream services can read it
    merged_report: dict = {
        "statistics": stats,
        "fraud":      {},
        "cashflow":   {},
        "llm_input":  {},
    }

    # ── 4. Risk engine (graceful degradation) ─────────────────────────────
    risk_result: dict = {"summary": {}, "flagged_transactions": []}
    try:
        engine = risk_engine_svc.RiskEngine(df)
        risk_result = engine.run()

        # ── Compute real fraud aggregate values (Problem 1) ───────────────
        flagged_txns = risk_result.get("flagged_transactions", [])

        # ── Normalize field names so pdf_generator never receives None ────
        # risk_engine produces: risk_score, risk_level, reasons, flags
        # pdf_generator expects: final_risk_score (float), risk_category (str),
        #                        fraud_type (str), combined_reason (str)
        # t.get("final_risk_score", 0) returns None when key exists = None
        # → f"{None:.1f}" crashes; fix by ensuring typed values here.
        for t in flagged_txns:
            # final_risk_score: always a float
            t["final_risk_score"] = float(
                t.get("final_risk_score") or t.get("risk_score") or 0
            )
            # risk_category: always a string (risk_engine uses risk_level)
            if not t.get("risk_category"):
                t["risk_category"] = str(t.get("risk_level") or "Unknown")
            # fraud_type: always a string (fall back to transaction_type)
            if not t.get("fraud_type_predicted") and not t.get("fraud_type"):
                t["fraud_type"] = str(t.get("transaction_type") or "Unknown")
            # combined_reason: always a string
            if not t.get("combined_reason"):
                reasons = t.get("reasons", [])
                t["combined_reason"] = "; ".join(reasons) if isinstance(reasons, list) else str(reasons or "")

        # Total monetary amount across all flagged transactions
        total_amount_at_risk = sum(
            t.get("amount", 0) or 0 for t in flagged_txns
        )

        # Risk distribution by level (from flagged transactions)
        risk_distribution: dict = {}
        for t in flagged_txns:
            level = t.get("risk_level") or t.get("risk_category") or "Unknown"
            risk_distribution[level] = risk_distribution.get(level, 0) + 1

        # Add non-flagged "Very Low" bucket
        total_txn_count = risk_result["summary"].get("total_transactions", len(df))
        flagged_count   = risk_result["summary"].get("flagged_transactions", len(flagged_txns))
        very_low_count  = max(total_txn_count - flagged_count, 0)
        risk_distribution["Very Low"] = very_low_count

        # Expose under "fraud" key so llm_sender can find all needed fields.
        # llm_sender._extract_fraud() reads:
        #   report["fraud"]["summary"]["flagged_count"]
        #   report["fraud"]["summary"]["total_amount_at_risk"]
        #   report["fraud"]["summary"]["risk_distribution"]
        #   report["fraud"]["flagged_transactions"]
        merged_report["fraud"] = {
            "summary": {
                "flagged_count":        flagged_count,
                "total_amount_at_risk": round(total_amount_at_risk, 2),
                "risk_distribution":    risk_distribution,
            },
            "flagged_transactions": flagged_txns,
        }
    except Exception as exc:
        logger.warning("analyze: risk_engine failed, using empty result: %s", exc)

    # ── 5. Cashflow predictor (graceful degradation) ─────────────────────
    cashflow_result: dict = {}
    try:
        cashflow_result = cashflow_predictor_svc.run(df, merged_report)
        merged_report["cashflow"] = cashflow_result
    except Exception as exc:
        logger.warning("analyze: cashflow_predictor failed, skipping: %s", exc)

    # ── 6. LLM sender ─────────────────────────────────────────────────────
    llm_payload = llm_sender_svc.run(df, merged_report)
    merged_report["llm_input"] = llm_payload

    # ── 7. Cloud Gemini (graceful degradation) ────────────────────────────
    gemini_result: dict = {
        "summary": "AI unavailable",
        "status":  "fallback",
    }
    try:
        gemini_result = cloud_gemini_svc.run(df, merged_report)
    except Exception as exc:
        logger.warning("analyze: cloud_gemini failed, returning fallback: %s", exc)

    # ══════════════════════════════════════════════════════════════
    # Shape the response for the frontend
    # ══════════════════════════════════════════════════════════════

    # ── summary ──────────────────────────────────────────────────
    merchant_summary = stats.get("merchant_summary", {})
    top_merchants_list = merchant_summary.get("merchants", [])
    top_merchant_name = top_merchants_list[0]["merchant"] if top_merchants_list else None

    summary_block = {
        "totalTransactions": stats.get("transaction_count", 0),
        "totalDebit":        stats.get("total_debit", 0.0),
        "totalCredit":       stats.get("total_credit", 0.0),
        "topMerchant":       top_merchant_name,
        "avgTransaction":    stats.get("average_transaction"),
        "maxTransaction":    stats.get("largest_debit") or stats.get("max_amount"),
    }

    # ── debitCredit: [{ month, debit, credit }] ───────────────────
    monthly_chart = charts.get("monthly_trends", {})
    monthly_labels = monthly_chart.get("labels", [])
    monthly_series = monthly_chart.get("series", [])
    debit_values  = next((s["values"] for s in monthly_series if s["name"] == "Debit"),  [0] * len(monthly_labels))
    credit_values = next((s["values"] for s in monthly_series if s["name"] == "Credit"), [0] * len(monthly_labels))
    debit_credit_block = [
        {"month": m, "debit": d, "credit": c}
        for m, d, c in zip(monthly_labels, debit_values, credit_values)
    ]

    # ── spendingTrends: [{ month, spend }] ───────────────────────
    spending_chart = charts.get("spending_trend_chart", {})
    spending_labels = spending_chart.get("labels", [])
    spending_values = spending_chart.get("values", [])
    spending_trends_block = [
        {"month": m, "spend": v}
        for m, v in zip(spending_labels, spending_values)
    ]

    # ── merchants: [{ merchant, amount }] ────────────────────────
    tm_chart = charts.get("top_merchants_chart", {})
    tm_labels = tm_chart.get("labels", [])
    tm_values = tm_chart.get("values", [])
    merchants_block = [
        {"merchant": name, "amount": amt}
        for name, amt in zip(tm_labels, tm_values)
    ]

    # ── transactionTypes: [{ name, value }] — value is % int ─────
    txn_chart = charts.get("transaction_type_chart", {})
    txn_labels = txn_chart.get("labels", [])
    txn_counts = txn_chart.get("values", [])
    total_txn  = sum(txn_counts) or 1
    transaction_types_block = [
        {"name": lbl, "value": int(round(cnt / total_txn * 100))}
        for lbl, cnt in zip(txn_labels, txn_counts)
    ]

    # ── risk ─────────────────────────────────────────────────────
    risk_summary   = risk_result.get("summary", {})
    flagged_count  = risk_summary.get("flagged_transactions", 0)
    total_count    = risk_summary.get("total_transactions", stats.get("transaction_count", 0))
    max_score      = risk_summary.get("max_risk_score", 0)

    if max_score >= 60:
        risk_level = "Critical"
    elif max_score >= 40:
        risk_level = "High"
    elif max_score >= 20:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    risk_block = {
        "riskScore":    max_score,
        "riskLevel":    risk_level,
        "flaggedCount": flagged_count,
        "totalCount":   total_count,
    }

    # ── flagged: list (max 100) ───────────────────────────────────
    raw_flagged = risk_result.get("flagged_transactions", [])[:100]
    flagged_block = [
        {
            "id":               t.get("transaction_index"),
            "date":             t.get("date"),
            "merchant":         t.get("merchant"),
            "debit_credit":     t.get("debit_credit"),
            "transaction_type": t.get("transaction_type"),
            "amount":           t.get("amount"),
            "riskPoints":       t.get("risk_score"),
            "reason":           "; ".join(t.get("reasons", [])) or None,
        }
        for t in raw_flagged
    ]

    # ── aiReport ─────────────────────────────────────────────────
    gemini_text = gemini_result.get("summary", "AI unavailable")
    ai_report_block = {
        "executiveSummary": gemini_text,
        "insights":         [],
        "recommendations":  [],
    }

    # ── Persist to app.state for /api/export-pdf ──────────────────
    app.state.last_ai_report    = gemini_text
    app.state.last_risk_level   = risk_level
    app.state.last_stats        = stats
    # Full payload needed by pdf_generator.run()
    app.state.last_df           = df
    app.state.last_merged_report = {
        **merged_report,
        "gemini": gemini_result,
    }

    return {
        "summary":          summary_block,
        "debitCredit":      debit_credit_block,
        "spendingTrends":   spending_trends_block,
        "merchants":        merchants_block,
        "transactionTypes": transaction_types_block,
        "risk":             risk_block,
        "flagged":          flagged_block,
        "aiReport":         ai_report_block,
        "cashflow":         cashflow_result,
    }


# ══════════════════════════════════════════════════════════════
# GET /api/export-pdf
# ══════════════════════════════════════════════════════════════

@app.get("/api/export-pdf", tags=["analysis"])
async def export_pdf():
    """
    Generate a professional PDF forensic report from the last /api/analyze
    run using services/pdf_generator and return it as a streaming download.

    Reads from app.state:
        last_df            — normalised DataFrame from last analysis
        last_merged_report — full analytics + fraud + cashflow + gemini dict

    Returns
    -------
    StreamingResponse
        media_type = "application/pdf"
        Content-Disposition: attachment; filename=fraud_report.pdf
    """
    from services import pdf_generator as pdf_generator_svc  # file: services/pdf_generator.py

    # ── Pull persisted state ──────────────────────────────────────
    df            = getattr(app.state, "last_df",            None)
    merged_report = getattr(app.state, "last_merged_report", None)

    if df is None or merged_report is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "No analysis data found. Please run /api/analyze first."},
        )

    # ── Log merged_report top-level structure for verification ────
    logger.info(
        "export_pdf: merged_report top-level keys = %s  |  "
        "fraud.summary keys = %s  |  "
        "cashflow keys = %s  |  "
        "statistics keys (sample) = %s",
        list(merged_report.keys()),
        list(merged_report.get("fraud", {}).get("summary", {}).keys()),
        list(merged_report.get("cashflow", {}).keys()),
        list(merged_report.get("statistics", {}).keys())[:8],
    )

    # ── Delegate PDF generation to pdf_generator service ─────────
    try:
        result = pdf_generator_svc.run(df, merged_report)
    except Exception as exc:
        logger.error("export_pdf: pdf_generator.run() failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": f"PDF generation failed: {exc}"},
        )

    if not result.get("generated"):
        error_msg = result.get("error", "Unknown error")
        logger.error("export_pdf: pdf_generator reported failure: %s", error_msg)
        return JSONResponse(
            status_code=500,
            content={"detail": f"PDF generation failed: {error_msg}"},
        )

    # ── Read the saved PDF from disk and stream it to frontend ────
    pdf_path = result["pdf_path"]
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except OSError as exc:
        logger.error("export_pdf: could not read generated PDF at %s: %s", pdf_path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Could not read generated PDF: {exc}"},
        )

    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)

    logger.info(
        "export_pdf: streaming %d-byte PDF (%d pages) to client",
        len(pdf_bytes),
        result.get("pages", -1),
    )

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=fraud_report.pdf"
        },
    )
