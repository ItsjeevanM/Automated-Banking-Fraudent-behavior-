"""
standardizer.py
---------------
Accepts bank statement CSV files from different banks/formats,
detects column names via synonym mapping, and converts all datasets
into one standardized schema ready for SQLite insertion via FastAPI.

Standardized output schema:
    {
        "debit_credit":       str   | None,
        "amount":             float | None,
        "balance":            float | None,
        "date":               str   | None,   # YYYY-MM-DD
        "time":               str   | None,   # HH:MM:SS
        "transaction_type":   str   | None,
        "merchant":           str   | None,
    }
"""

import pandas as pd
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Synonym map: canonical field → list of raw column names (lowercased,
# stripped) that might represent it in the wild.
# ---------------------------------------------------------------------------
SYNONYM_MAP: dict[str, list[str]] = {
    "debit_credit": [
        "debit_credit", "drcr", "drcr", "drcr",
        "type", "transaction_direction", "dr_cr", "dr/cr",
    ],
    "amount": [
        "amount", "txn_amount", "transaction_amount", "amt",
        "transaction amount", "transactionamount",
    ],
    "balance": [
        "balance", "currentbalance", "running_balance",
        "current_balance", "closing_balance",
    ],
    "date": [
        "date", "value_date", "transaction_date",
        "valuedate", "trans_date",
    ],
    "time": [
        "time", "transaction_time", "timestamp",
        "datetime", "transactiontimestamp",
    ],
    "transaction_type": [
        "mode", "transaction_type", "payment_mode",
        "txn_type", "trans_type", "transaction type", "transactiontype",
    ],
    "merchant": [
        "merchant", "narration", "name", "payee",
        "beneficiary", "description", "particulars",
    ],
}

# Columns that carry a combined date+time value and must be split
DATETIME_SYNONYMS = {
    "transactiontimestamp", "datetime", "timestamp",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(col: str) -> str:
    """Lowercase + strip a column name for fuzzy matching."""
    return col.lower().strip().replace(" ", "").replace("-", "_")


def _build_column_map(raw_columns: list[str]) -> dict[str, str]:
    """
    Given the raw CSV column names, return a mapping
    { canonical_field: raw_column_name } for every field we can detect.
    Fields not found in the CSV are absent from the returned dict.
    """
    # Pre-normalise raw names once
    normalised = {col: _normalize(col) for col in raw_columns}

    col_map: dict[str, str] = {}
    for canonical, synonyms in SYNONYM_MAP.items():
        for raw_col, norm in normalised.items():
            if norm in synonyms:
                # First match wins; earlier synonyms = higher priority
                if canonical not in col_map:
                    col_map[canonical] = raw_col
    return col_map


def _safe_float(value) -> Optional[float]:
    """Convert a value to float; return None on failure."""
    if pd.isna(value):
        return None
    try:
        # Strip currency symbols / commas if the value is a string
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _safe_str(value) -> Optional[str]:
    """Convert a value to stripped string; return None for blanks / NaN."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def _parse_date(value) -> Optional[str]:
    """
    Parse a date-like value and return 'YYYY-MM-DD' string.
    Tries common formats; returns None on failure.
    """
    if pd.isna(value):
        return None
    raw = str(value).strip()
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
        "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y", "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Handles ISO 8601 with timezone offset e.g. "2023-06-27T09:40:19+05:30"
    try:
        return pd.to_datetime(raw, utc=False).strftime("%Y-%m-%d")
    except Exception:
        pass
    # Last resort: let pandas infer
    try:
        return pd.to_datetime(raw, infer_datetime_format=True).strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_time(value) -> Optional[str]:
    """
    Parse a time or datetime-like value and return 'HH:MM:SS' string.
    Returns None on failure.
    """
    if pd.isna(value):
        return None
    raw = str(value).strip()
    formats_with_time = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        "%H:%M:%S", "%H:%M",
    ]
    for fmt in formats_with_time:
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    # Handles ISO 8601 with timezone offset e.g. "2023-06-27T09:40:19+05:30"
    try:
        dt = pd.to_datetime(raw, utc=False)
        return dt.strftime("%H:%M:%S")
    except Exception:
        pass
    try:
        dt = pd.to_datetime(raw, infer_datetime_format=True)
        if dt.hour or dt.minute or dt.second:
            return dt.strftime("%H:%M:%S")
    except Exception:
        pass
    return None


def _normalise_debit_credit(value) -> Optional[str]:
    """
    Normalise free-form debit/credit indicators to 'Debit' or 'Credit'.
    e.g. 'DEBIT', 'Dr', 'Db', 'D' → 'Debit'
         'CREDIT', 'Cr', 'C'      → 'Credit'
    """
    if pd.isna(value):
        return None
    raw = str(value).strip().upper()
    debit_indicators  = {"DEBIT", "DR", "DB", "D", "DEBI", "WITHDRAWAL"}
    credit_indicators = {"CREDIT", "CR", "C", "CRED", "DEPOSIT"}
    if raw in debit_indicators:
        return "Debit"
    if raw in credit_indicators:
        return "Credit"
    # Return as-is for unknown values so no data is silently lost
    return str(value).strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def standardize(filepath: str) -> list[dict]:
    """
    Read a bank-statement CSV from *filepath*, detect its columns via
    synonym mapping, and return a list of standardised transaction dicts
    ready for direct insertion into a SQLite ``transactions`` table.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the CSV file.

    Returns
    -------
    list[dict]
        Each dict has exactly these keys (values may be None if the
        source CSV lacks the corresponding information):
            debit_credit, amount, balance, date, time,
            transaction_type, merchant
    """
    # 1. Load CSV
    df = pd.read_csv(filepath)

    # 2. Detect which raw columns map to which canonical fields
    col_map = _build_column_map(list(df.columns))

    # 3. Determine whether the 'time' column is really a combined
    #    datetime column that should also supply the 'date'.
    time_raw_col = col_map.get("time")
    is_combined_datetime = (
        time_raw_col is not None
        and _normalize(time_raw_col) in DATETIME_SYNONYMS
    )

    # 4. If there is a dedicated 'date' column AND a datetime column for
    #    'time', keep them separate.  If only a datetime column exists,
    #    extract both date and time from it.
    records: list[dict] = []

    for _, row in df.iterrows():
        record: dict = {
            "debit_credit":     None,
            "amount":           None,
            "balance":          None,
            "date":             None,
            "time":             None,
            "transaction_type": None,
            "merchant":         None,
        }

        # -- debit_credit --
        if "debit_credit" in col_map:
            record["debit_credit"] = _normalise_debit_credit(
                row[col_map["debit_credit"]]
            )

        # -- amount --
        if "amount" in col_map:
            record["amount"] = _safe_float(row[col_map["amount"]])

        # -- balance --
        if "balance" in col_map:
            record["balance"] = _safe_float(row[col_map["balance"]])

        # -- date / time --
        if is_combined_datetime and "date" not in col_map:
            # No dedicated date column — extract both from the datetime field
            dt_val = row[time_raw_col]
            record["date"] = _parse_date(dt_val)
            record["time"] = _parse_time(dt_val)
        else:
            # Dedicated date column present (or no datetime col at all)
            if "date" in col_map:
                record["date"] = _parse_date(row[col_map["date"]])
            # Time comes from the datetime column (time-part only) or a
            # standalone time column
            if is_combined_datetime:
                record["time"] = _parse_time(row[time_raw_col])
            elif "time" in col_map:
                record["time"] = _parse_time(row[col_map["time"]])

        # -- transaction_type --
        if "transaction_type" in col_map:
            record["transaction_type"] = _safe_str(
                row[col_map["transaction_type"]]
            )

        # -- merchant --
        if "merchant" in col_map:
            record["merchant"] = _safe_str(row[col_map["merchant"]])

        records.append(record)

    return records


def standardize_dataframe(df: pd.DataFrame) -> list[dict]:
    """
    Convenience overload: accept an already-loaded DataFrame instead of
    a file path.  Useful when the CSV bytes arrive in memory (e.g. via
    FastAPI's ``UploadFile``).

    Parameters
    ----------
    df : pd.DataFrame
        A DataFrame whose columns come from a bank-statement CSV.

    Returns
    -------
    list[dict]
        Same standardised schema as :func:`standardize`.
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = tmp.name
    try:
        return standardize(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Example / quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys

    # Accept an optional file path from the command line, otherwise demo
    path = sys.argv[1] if len(sys.argv) > 1 else None

    if path:
        results = standardize(path)
        print(f"\n[{path}] → {len(results)} records")
        print(json.dumps(results[:3], indent=2, default=str))
    else:
        print("Usage: python standardizer.py <path/to/bank_statement.csv>")
        print("\nRunning built-in demo with all 3 sample files…\n")
        sample_files = [
            "bank_statements.csv",
            "bankstatements.csv",
            "transaction_data.csv",
        ]
        for fname in sample_files:
            try:
                rows = standardize(fname)
                print(f"=== {fname} ({len(rows)} rows) ===")
                print(json.dumps(rows[:2], indent=2, default=str))
                print()
            except FileNotFoundError:
                print(f"  (skipped — {fname} not found)\n")
