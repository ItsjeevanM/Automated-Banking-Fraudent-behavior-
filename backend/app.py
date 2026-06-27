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

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
