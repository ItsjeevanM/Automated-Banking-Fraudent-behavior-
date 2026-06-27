"""
database.py
============================================================
SQLite database for Bank Fraud Detection System.
Keeps your existing transactions table + adds 5 new tables
needed for auth, file uploads, ML jobs, and reports.
============================================================
"""

import sqlite3
import uuid
from datetime import datetime

DATABASE_NAME = "transactions.db"


def get_conn():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row   # lets you access columns by name
    conn.execute("PRAGMA journal_mode=WAL")   # allows concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_database():
    conn = get_conn()
    cursor = conn.cursor()

    # ── EXISTING TABLE (keep as-is) ──────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        debit_credit     TEXT,
        amount           REAL,
        balance          REAL,
        date             TEXT,
        time             TEXT,
        transaction_type TEXT,
        merchant         TEXT
    )
    """)

    # ── NEW: Users ───────────────────────────────────────────
    # Stores registered users. password_hash is bcrypt hash,
    # never the plain password.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id            TEXT PRIMARY KEY,
        email         TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name     TEXT,
        role          TEXT DEFAULT 'user',
        created_at    TEXT DEFAULT (datetime('now'))
    )
    """)

    # ── NEW: JWT Token Blocklist ─────────────────────────────
    # When user logs out, their token JTI goes here.
    # Checked on every protected request.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS token_blocklist (
        jti        TEXT PRIMARY KEY,
        expires_at TEXT NOT NULL
    )
    """)

    # ── NEW: Uploads ─────────────────────────────────────────
    # Every file a user uploads (PDF, CSV, image).
    # file_path = where it's stored on disk.
    # status: pending → processing → done → failed
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS uploads (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        filename    TEXT NOT NULL,
        file_path   TEXT NOT NULL,
        file_type   TEXT NOT NULL,
        file_size   INTEGER,
        status      TEXT DEFAULT 'pending',
        uploaded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # ── NEW: Analysis Jobs ───────────────────────────────────
    # One job per upload. Tracks ML pipeline progress.
    # progress: 0-100 (shown as progress bar in frontend)
    # status: queued → ocr → scoring → llm → done → failed
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analysis_jobs (
        id          TEXT PRIMARY KEY,
        upload_id   TEXT NOT NULL,
        user_id     TEXT NOT NULL,
        status      TEXT DEFAULT 'queued',
        progress    INTEGER DEFAULT 0,
        error_msg   TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        completed_at TEXT,
        FOREIGN KEY (upload_id) REFERENCES uploads(id),
        FOREIGN KEY (user_id)   REFERENCES users(id)
    )
    """)

    # ── NEW: Reports ─────────────────────────────────────────
    # Final output of the ML pipeline stored per job.
    # portfolio_summary and episodes stored as JSON strings.
    # scored_csv_path = path to the scored output CSV.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id                TEXT PRIMARY KEY,
        job_id            TEXT NOT NULL,
        user_id           TEXT NOT NULL,
        total_txns        INTEGER,
        flagged_count     INTEGER,
        avg_risk_score    REAL,
        max_risk_score    REAL,
        amount_at_risk    REAL,
        portfolio_summary TEXT,
        episodes          TEXT,
        llm_report        TEXT,
        scored_csv_path   TEXT,
        created_at        TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (job_id)  REFERENCES analysis_jobs(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # ── NEW: Flagged Transactions ────────────────────────────
    # Individual flagged rows from the ML engine.
    # Stored separately so frontend can paginate/filter them.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flagged_transactions (
        id              TEXT PRIMARY KEY,
        report_id       TEXT NOT NULL,
        user_id         TEXT NOT NULL,
        txn_date        TEXT,
        amount          REAL,
        narration       TEXT,
        final_risk_score REAL,
        risk_category   TEXT,
        dominant_signal TEXT,
        fraud_type      TEXT,
        rule_flags      TEXT,
        combined_reason TEXT,
        ml_score        REAL,
        rule_score      REAL,
        created_at      TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (report_id) REFERENCES reports(id),
        FOREIGN KEY (user_id)   REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()
    print("Database ready.")


# ══════════════════════════════════════════════════════════════
# EXISTING FUNCTIONS (unchanged)
# ══════════════════════════════════════════════════════════════

def add_transaction(debit_credit, amount, balance, date, time, transaction_type, merchant):
    conn = get_conn()
    conn.execute("""
        INSERT INTO transactions
        (debit_credit, amount, balance, date, time, transaction_type, merchant)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (debit_credit, amount, balance, date, time, transaction_type, merchant))
    conn.commit()
    conn.close()


def get_transactions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM transactions").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
# USER FUNCTIONS
# ══════════════════════════════════════════════════════════════

def create_user(email: str, password_hash: str, full_name: str = None) -> str:
    user_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, full_name) VALUES (?, ?, ?, ?)",
        (user_id, email, password_hash, full_name)
    )
    conn.commit()
    conn.close()
    return user_id


def get_user_by_email(email: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════
# TOKEN BLOCKLIST FUNCTIONS
# ══════════════════════════════════════════════════════════════

def blocklist_token(jti: str, expires_at: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO token_blocklist (jti, expires_at) VALUES (?, ?)",
        (jti, expires_at)
    )
    conn.commit()
    conn.close()


def is_token_blocked(jti: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT jti FROM token_blocklist WHERE jti = ?", (jti,)
    ).fetchone()
    conn.close()
    return row is not None


def clean_expired_tokens():
    """Call this periodically to keep blocklist table small."""
    conn = get_conn()
    conn.execute(
        "DELETE FROM token_blocklist WHERE expires_at < datetime('now')"
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════
# UPLOAD FUNCTIONS
# ══════════════════════════════════════════════════════════════

def create_upload(user_id: str, filename: str, file_path: str,
                  file_type: str, file_size: int) -> str:
    upload_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute("""
        INSERT INTO uploads (id, user_id, filename, file_path, file_type, file_size)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (upload_id, user_id, filename, file_path, file_type, file_size))
    conn.commit()
    conn.close()
    return upload_id


def update_upload_status(upload_id: str, status: str):
    conn = get_conn()
    conn.execute("UPDATE uploads SET status = ? WHERE id = ?", (status, upload_id))
    conn.commit()
    conn.close()


def get_user_uploads(user_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM uploads WHERE user_id = ? ORDER BY uploaded_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
# JOB FUNCTIONS
# ══════════════════════════════════════════════════════════════

def create_job(upload_id: str, user_id: str) -> str:
    job_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute("""
        INSERT INTO analysis_jobs (id, upload_id, user_id)
        VALUES (?, ?, ?)
    """, (job_id, upload_id, user_id))
    conn.commit()
    conn.close()
    return job_id


def update_job(job_id: str, status: str, progress: int, error_msg: str = None):
    conn = get_conn()
    completed_at = datetime.utcnow().isoformat() if status in ("done", "failed") else None
    conn.execute("""
        UPDATE analysis_jobs
        SET status = ?, progress = ?, error_msg = ?, completed_at = ?
        WHERE id = ?
    """, (status, progress, error_msg, completed_at, job_id))
    conn.commit()
    conn.close()


def get_job(job_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════
# REPORT FUNCTIONS
# ══════════════════════════════════════════════════════════════

def save_report(job_id: str, user_id: str, result, llm_text: str,
                scored_csv_path: str) -> str:
    """
    result = FraudResult from unified_fraud_engine.quick_run()
    """
    import json
    report_id = str(uuid.uuid4())
    ps = result.portfolio_summary
    conn = get_conn()

    conn.execute("""
        INSERT INTO reports
        (id, job_id, user_id, total_txns, flagged_count, avg_risk_score,
         max_risk_score, amount_at_risk, portfolio_summary, episodes,
         llm_report, scored_csv_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report_id, job_id, user_id,
        ps.get("total_transactions"),
        ps.get("flagged_count"),
        ps.get("avg_final_risk_score"),
        ps.get("max_final_risk_score"),
        ps.get("total_amount_at_risk"),
        json.dumps(ps),
        json.dumps(result.episodes),
        llm_text,
        scored_csv_path
    ))

    # Save individual flagged transactions
    flagged = result.flagged_df
    for _, row in flagged.iterrows():
        conn.execute("""
            INSERT INTO flagged_transactions
            (id, report_id, user_id, txn_date, amount, narration,
             final_risk_score, risk_category, dominant_signal, fraud_type,
             rule_flags, combined_reason, ml_score, rule_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), report_id, user_id,
            str(row.get("date", "")),
            float(row.get("amount", 0)),
            str(row.get("narration", "")),
            float(row.get("final_risk_score", 0)),
            str(row.get("risk_category", "")),
            str(row.get("dominant_signal", "")),
            str(row.get("fraud_type_predicted", "")),
            json.dumps(list(row.get("rule_flags", []))),
            str(row.get("combined_reason", "")),
            float(row.get("ml_score", 0)),
            float(row.get("rule_score", 0)),
        ))

    conn.commit()
    conn.close()
    return report_id


def get_report(report_id: str, user_id: str) -> dict | None:
    import json
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM reports WHERE id = ? AND user_id = ?",
        (report_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    r["portfolio_summary"] = json.loads(r["portfolio_summary"] or "{}")
    r["episodes"] = json.loads(r["episodes"] or "[]")
    return r


def get_flagged_transactions(report_id: str, user_id: str,
                              page: int = 1, limit: int = 50) -> list:
    import json
    offset = (page - 1) * limit
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM flagged_transactions
        WHERE report_id = ? AND user_id = ?
        ORDER BY final_risk_score DESC
        LIMIT ? OFFSET ?
    """, (report_id, user_id, limit, offset)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["rule_flags"] = json.loads(d["rule_flags"] or "[]")
        result.append(d)
    return result


def get_user_reports(user_id: str) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, job_id, total_txns, flagged_count, avg_risk_score,
               amount_at_risk, created_at
        FROM reports
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Run directly to initialise ────────────────────────────────
if __name__ == "__main__":
    create_database()