"""
Bank Statement PDF → CSV Converter

Extracts transactions from bank-statement PDFs across multiple bank
layouts (IDFC FIRST, Bandhan Bank, flat tabular exports, and the
original Standard Chartered "page-collapsed" layout).

WHY THIS VERSION IS DIFFERENT FROM THE ORIGINAL
-------------------------------------------------
The original parser hardcoded column indices (description@2, balance@6)
and hardcoded page-pixel x-coordinates, tuned to exactly one bank's PDF
layout, where pdfplumber collapses an entire page of transactions into
ONE table row per column (needing a balance-delta trick to recover
debit/credit and a y-coordinate trick to recover per-transaction dates).

Testing against real statements from IDFC FIRST Bank, Bandhan Bank, and
a flat tabular export showed pdfplumber actually returns ONE ROW PER
TRANSACTION for these layouts, with separate Debit/Credit columns
already split out. Hardcoded indices silently misread the wrong column
(e.g. reading the cheque-number column as the description) rather than
crashing, which is worse than a crash.

This version is header-driven instead of index-driven:
  1. Every table's header row is read and column purpose (date,
     description, debit, credit, balance, cheque no) is matched by
     keyword, not by fixed position. This adapts to each bank's column
     order/count automatically.
  2. Per-transaction rows are read directly (debit/credit taken straight
     from their columns) when the table has one row per transaction.
  3. A legacy "page-collapsed" extraction path (the original
     balance-delta + y-coordinate technique) is kept and used
     automatically ONLY when a table is detected to have that shape
     (i.e. a single row whose balance cell contains many newline-
     separated values) — this preserves support for the original
     Standard Chartered-style PDFs.
  4. Multi-line description cells that pdfplumber sometimes splits into
     a trailing "continuation row" (mostly-empty row with only a
     description fragment) are detected and merged into the previous
     transaction instead of being misread as new, broken transactions.
  5. Every table/row is validated before use; malformed or non-
     transaction tables (summaries, headers, footers, abbreviation
     lists) are skipped, logged, and counted — never crash the parser.

Output columns (unchanged):
  id, debit_credit, amount, balance, date, time, transaction_type, merchant

Usage:
    python pdf_to_csv.py <input.pdf> [output.csv]

Requires:
    pip install pdfplumber
"""
import re
import csv
import sys
import logging
import uuid
from pathlib import Path
from collections import defaultdict

import pdfplumber

# ── logging ─────────────────────────────────────────────────────────────────
# Silent by default so importing this module doesn't clobber a host app's
# logging config. Enable with logging.basicConfig(level=logging.DEBUG) to
# see per-row skip/merge decisions during development.
logger = logging.getLogger(__name__)

# ── header keyword catalogue ───────────────────────────────────────────────
# Order matters within each list only for readability; matching below picks
# the most specific match (checks VALUE_DATE before DATE, for example, so
# "Value Date" isn't mis-tagged as the transaction date).
HEADER_KEYWORDS = {
    "value_date":  ["value date", "value\ndate"],
    "date":        ["trans date", "transaction date", "tran_date", "trans_date", "date"],
    "description": ["transaction details", "description", "narration", "particulars", "details"],
    "cheque":      ["cheque", "chq", "instrument"],
    "debit":       ["debit", "dr_amt", "dr amt", "withdrawal"],
    "credit":      ["credit", "cr_amt", "cr amt", "deposit"],
    "balance":     ["balance"],
    "txn_id":      ["tran_id", "txn_id", "transaction id"],
}
# Categories required for a row to be accepted as a genuine header row.
REQUIRED_HEADER_CATEGORIES = ("date", "balance")

OPENING_BALANCE_MARKERS = {
    "opening balance", "balance forward", "b/f", "b/f ...", "opening bal", "b/f...",
}

# ── generic safe access helpers ────────────────────────────────────────────
def safe_col(row, i, default=""):
    """
    Return row[i] as a safe value, or `default` if the row is missing,
    too short, or the cell is None. The single accessor every part of
    the parser should use instead of raw row[i].
    """
    if not row or i < 0 or i >= len(row):
        return default
    val = row[i]
    return val if val is not None else default


def norm_header(cell):
    """Normalize a header cell for keyword matching: collapse newlines/whitespace, lowercase."""
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", str(cell).replace("\n", " ")).strip().lower()


def norm_cell(cell):
    """Normalize a data cell: collapse newlines to spaces, strip."""
    if cell is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(cell).replace("\n", " ")).strip()


def row_is_blank(row):
    """True if every cell in the row is None/empty/whitespace."""
    if not row:
        return True
    return all(not (c and str(c).strip()) for c in row)


# ── header detection & dynamic column mapping ──────────────────────────────
def match_header_category(header_text):
    """Return the best-matching category name for a single normalized header cell, or None."""
    # value_date checked before date so "value date" isn't captured as the txn date.
    for category in ("value_date", "date", "description", "cheque", "debit", "credit", "balance", "txn_id"):
        for kw in HEADER_KEYWORDS[category]:
            if kw in header_text:
                return category
    return None


def build_column_map(row):
    """
    Given a candidate header row, return {category: column_index} for every
    recognized column, or None if the row doesn't look like a real
    transaction-table header (missing required categories).
    """
    if not row:
        return None
    col_map = {}
    for idx, cell in enumerate(row):
        text = norm_header(cell)
        if not text:
            continue
        category = match_header_category(text)
        # First match wins per category (avoids a later stray column
        # overwriting the real one, e.g. a narration cell that happens to
        # contain the word "date").
        if category and category not in col_map:
            col_map[category] = idx

    if all(cat in col_map for cat in REQUIRED_HEADER_CATEGORIES) and (
        "description" in col_map or "debit" in col_map or "credit" in col_map
    ):
        return col_map
    return None


def find_header(table, max_rows_to_scan=3):
    """Scan the first few rows of a table for a header row. Returns (header_idx, col_map) or (None, None)."""
    for idx, row in enumerate(table[:max_rows_to_scan]):
        col_map = build_column_map(row)
        if col_map:
            return idx, col_map
    return None, None


# ── amount / date parsing ──────────────────────────────────────────────────
_AMOUNT_SUFFIX_RE = re.compile(r"\s*(cr|dr)\s*$", re.IGNORECASE)

def parse_amount(text):
    """
    Parse a currency-ish string into a float. Handles thousands separators
    and a trailing Cr/Dr suffix (Dr => negative). Returns None if there's
    nothing usable to parse.
    """
    if text is None:
        return None
    s = norm_cell(text)
    if not s:
        return None
    sign = 1
    m = _AMOUNT_SUFFIX_RE.search(s)
    if m:
        if m.group(1).lower() == "dr":
            sign = -1
        s = s[: m.start()].strip()
    s = s.replace(",", "").replace("₹", "").strip()
    if not s:
        return None
    try:
        return round(sign * float(s), 2)
    except ValueError:
        return None


_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
_DATE_FORMATS = [
    "%d/%m/%y", "%d/%m/%Y",
    "%d-%m-%y", "%d-%m-%Y",
    "%d-%b-%y", "%d-%b-%Y",
    "%d %b %y", "%d %b %Y",
    "%d.%m.%y", "%d.%m.%Y",
]

def parse_date_time(text):
    """
    Parse a date cell (which may also contain an embedded time) into
    (date_str, time_str). date_str is normalized to YYYY-MM-DD when a
    known format matches; otherwise the original cleaned text is kept so
    no information is silently dropped.
    """
    from datetime import datetime

    s = norm_cell(text)
    if not s:
        return "", ""

    time_str = ""
    tm = _TIME_RE.search(s)
    if tm:
        time_str = tm.group(1)
        s = (s[: tm.start()] + s[tm.end():]).strip()

    # Some PDFs wrap a date across lines (e.g. "23-FEB-\n2025"); after
    # norm_cell() turns the newline into a space this leaves stray spaces
    # around the separator ("23-FEB- 2025"). Collapse those before parsing.
    date_part = re.sub(r"\s*-\s*", "-", s.strip())
    date_part = re.sub(r"\s*/\s*", "/", date_part)
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_part, fmt)
            # 2-digit years: assume 2000s (all sample statements are recent)
            return dt.strftime("%Y-%m-%d"), time_str
        except ValueError:
            continue

    # Unknown format — keep the raw text rather than silently dropping it.
    return date_part, time_str


def extract_time(description):
    m = re.search(r"\b(\d{2}:\d{2}:\d{2})\b", description)
    return m.group(1) if m else ""


# ── transaction-type / merchant heuristics (broadened for multi-bank text) ─
_TYPE_RULES = [
    ("ATM_WITHDRAWAL", ("ATM WITHDRAWAL", "ATM-NFS", "CARDLESS CASH", "CCW/")),
    ("UPI",             ("UPI/", "UPI ")),
    ("IMPS",            ("IMPS/", "IMPS-", "MMT/IMPS")),
    ("RTGS",            ("RTGS/", "RTGS ", "RTGS-", "BLKRTGS")),
    ("NEFT",            ("NEFT/", "NEFT ", "NEFT-", "BLKNEFT")),
    ("IFT",             ("IFT/", "BLKIFT")),
    ("PURCHASE",        ("PURCHASE",)),
    ("CHEQUE",          ("CHQ", "CHEQUE", "CLG/")),
    ("INTEREST",        ("CREDIT OF INTEREST", "INTEREST"),),
    ("REVERSAL",        ("FAILED", "RETURN-", "REV_", "/REV/", "RVSL")),
    ("CHARGES",         ("NON SCB ATM", "ATM USAGE", "CHARGES", "SETUPCHARGES", "ECSRTNCHG", "SC FOR")),
    ("TAX",             ("CGST", "SGST", "GST")),
    ("DISCOUNT",        ("DISCOUNT",)),
    ("CASH",            ("CASH PAID", "CASH DEPOSIT", "BY CASH", "TRFR FROM")),
    ("FUND_TRANSFER",   ("FT - CR", "FT-CR", "FT ", "BIL/INFT", "INF/INFT", "ACH/")),
]

def guess_transaction_type(description):
    d = (description or "").upper()
    for label, needles in _TYPE_RULES:
        if any(n in d for n in needles):
            return label
    return "OTHER"


def _looks_like_code(segment):
    """Reference/bank codes: a digit with no internal space, or a short ALL-CAPS abbreviation."""
    if re.search(r"\d", segment) and " " not in segment:
        return True
    if len(segment) <= 3 and segment.isupper():
        return True
    return False


def _pick_name_like(parts):
    """Walk segments from the end; return the first one that doesn't look like a ref/bank code."""
    for p in reversed(parts):
        if p and not re.match(r"^\d+$", p) and not _looks_like_code(p):
            return p
    return ""


def extract_merchant(description, txn_type):
    """Best-effort merchant/counterparty extraction. Heuristic across formats — not guaranteed exact."""
    desc = norm_cell(description)
    if not desc:
        return ""

    if txn_type == "PURCHASE":
        m = re.match(r"PURCHASE\s+(.+?)(?:\s{2,}|\s+IN\s|\s+\d{1,2}:\d{2})", desc, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    if txn_type == "UPI":
        parts = [p.strip() for p in desc.split("/") if p.strip()]
        for idx in (3, 2, 4):
            if len(parts) > idx:
                c = parts[idx]
                if c and not re.match(r"^\d+$", c) and "@" not in c:
                    return c
        return ""

    # Generic fallback for everything else (NEFT, RTGS, IMPS, IFT,
    # FUND_TRANSFER, CHEQUE, etc): try slash-delimited segments first,
    # then hyphen-delimited, preferring whichever segment looks most
    # like a name rather than a bank/reference code.
    if "/" in desc:
        result = _pick_name_like([p.strip() for p in desc.split("/") if p.strip()])
        if result:
            return result
    if "-" in desc:
        result = _pick_name_like([p.strip() for p in desc.split("-") if p.strip()])
        if result:
            return result
    return ""


# ── legacy page-collapsed extraction (original Standard-Chartered layout) ──
# Kept intact for backwards compatibility with statements where pdfplumber
# collapses a whole page's transactions into ONE table row per column.
TXN_START = re.compile(
    r"^(ATM WITHDRAWAL|PURCHASE|UPI/|CRADJ/|IMPS/|NEFT |IN\d{4}|CREDIT OF INTEREST|"
    r"NON SCB ATM|CGST|SGST|DISCOUNT ON|IMPS P2A|BALANCE FORWARD|TOTAL\b)",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"^\d{1,2} \w{3} \d{2}$")
DATE_X_MAX = 100
DESC_X_MIN = 115
DESC_X_MAX = 480


def group_descriptions(raw_text):
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    groups, current = [], []
    for line in lines:
        if TXN_START.match(line) and current:
            groups.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append("\n".join(current))
    return groups


def classify_from_delta(prev_bal, curr_bal):
    if prev_bal is None or curr_bal is None:
        return "", None
    delta = round(curr_bal - prev_bal, 2)
    if delta < 0:
        return "DEBIT", abs(delta)
    elif delta > 0:
        return "CREDIT", abs(delta)
    return "DEBIT", 0.0


def build_date_map(page):
    by_y = defaultdict(list)
    for w in page.extract_words():
        if w["x0"] < DATE_X_MAX:
            by_y[round(w["top"])].append(w["text"])
    date_map = {}
    for y, tokens in sorted(by_y.items()):
        candidate = " ".join(tokens[:3])
        if DATE_RE.match(candidate):
            date_map[y] = candidate
    return date_map


def build_txn_y_list(page):
    by_y = defaultdict(list)
    for w in page.extract_words():
        if DESC_X_MIN < w["x0"] < DESC_X_MAX:
            by_y[round(w["top"])].append(w["text"])
    txn_ys = []
    for y in sorted(by_y.keys()):
        line = " ".join(by_y[y])
        if TXN_START.match(line):
            txn_ys.append(y)
    return txn_ys


def date_for_y(txn_y, date_map):
    best = ""
    for dy in sorted(date_map.keys()):
        if dy <= txn_y:
            best = date_map[dy]
        else:
            break
    return best


def is_page_collapsed_row(row, col_map):
    """
    Detect the legacy "whole page in one row" shape: the balance cell (or
    description cell) contains multiple newline-separated values instead
    of a single value.
    """
    bal_idx = col_map.get("balance")
    if bal_idx is None:
        return False
    bal_text = safe_col(row, bal_idx)
    lines = [l for l in str(bal_text).split("\n") if l.strip()]
    return len(lines) > 1


def extract_legacy_page_row(page, row, col_map, opening_balance, stats):
    """Legacy balance-delta + y-coordinate extraction for a page-collapsed row."""
    desc_idx = col_map.get("description")
    bal_idx = col_map.get("balance")

    bals_raw = [l.strip() for l in str(safe_col(row, bal_idx)).split("\n") if l.strip()]
    bals = [parse_amount(b) for b in bals_raw]
    descs = group_descriptions(str(safe_col(row, desc_idx))) if desc_idx is not None else []

    if not descs and not bals:
        stats["empty_data_rows_skipped"] += 1
        return [], opening_balance

    n = min(len(descs), len(bals))
    descs, bals = descs[:n], bals[:n]

    date_map = build_date_map(page)
    txn_ys = build_txn_y_list(page)

    prev_bal = opening_balance
    transactions = []
    txn_idx = 0

    for desc, curr_bal in zip(descs, bals):
        first_line = desc.splitlines()[0].strip() if desc else ""
        if not first_line:
            txn_idx += 1
            continue
        if first_line.upper() in ("BALANCE FORWARD", "TOTAL") or first_line.upper().startswith("TOTAL"):
            prev_bal = curr_bal
            txn_idx += 1
            continue

        txn_y = txn_ys[txn_idx] if txn_idx < len(txn_ys) else None
        date_val = date_for_y(txn_y, date_map) if txn_y is not None else ""
        txn_idx += 1

        debit_credit, amount = classify_from_delta(prev_bal, curr_bal)
        txn_type = guess_transaction_type(desc)
        merchant = extract_merchant(desc, txn_type)
        time_val = extract_time(desc)

        transactions.append({
            "debit_credit": debit_credit, "amount": amount, "balance": curr_bal,
            "date": date_val, "time": time_val,
            "transaction_type": txn_type, "merchant": merchant,
        })
        prev_bal = curr_bal
        stats["transactions_extracted"] += 1

    return transactions, prev_bal


# ── main per-row (header-driven) extraction ────────────────────────────────
def looks_like_opening_balance(description_norm):
    d = re.sub(r"[\s.]+$", "", description_norm.strip().lower())
    return d in OPENING_BALANCE_MARKERS or d.startswith("balance forward") or d.startswith("opening balance") or d == "b/f"


def build_transaction(col_map, row, running_balance):
    """Build a transaction dict from one already-per-transaction row. Returns (txn_or_None, new_running_balance)."""
    date_raw = safe_col(row, col_map.get("date", -1))
    desc_raw = safe_col(row, col_map.get("description", -1)) if "description" in col_map else ""
    debit_raw = safe_col(row, col_map.get("debit", -1)) if "debit" in col_map else ""
    credit_raw = safe_col(row, col_map.get("credit", -1)) if "credit" in col_map else ""
    balance_raw = safe_col(row, col_map.get("balance", -1))

    description = norm_cell(desc_raw)
    debit_amt = parse_amount(debit_raw)
    credit_amt = parse_amount(credit_raw)
    balance_amt = parse_amount(balance_raw)

    if debit_amt:
        debit_credit, amount = "DEBIT", abs(debit_amt)
    elif credit_amt:
        debit_credit, amount = "CREDIT", abs(credit_amt)
    else:
        # Neither column has a usable value — fall back to balance-delta
        # against the running balance, same technique as the legacy path.
        debit_credit, amount = classify_from_delta(running_balance, balance_amt)

    date_val, time_val = parse_date_time(date_raw)
    if not time_val:
        time_val = extract_time(description)

    txn_type = guess_transaction_type(description)
    merchant = extract_merchant(description, txn_type)

    txn = {
        "debit_credit": debit_credit,
        "amount": amount,
        "balance": balance_amt if balance_amt is not None else running_balance,
        "date": date_val,
        "time": time_val,
        "transaction_type": txn_type,
        "merchant": merchant,
        "_description": description,  # internal only, stripped before CSV write
    }
    new_balance = balance_amt if balance_amt is not None else running_balance
    return txn, new_balance


def extract_transactions(pdf_path):
    all_rows = []
    txn_id = 1
    running_balance = None
    last_txn = None  # for merging continuation rows, persists across tables/pages

    stats = defaultdict(int)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table:
                    stats["malformed_tables_skipped"] += 1
                    continue

                header_idx, col_map = find_header(table)
                if col_map is None:
                    logger.debug("Skipping non-transaction table (no header match): %r", table[:2])
                    stats["malformed_tables_skipped"] += 1
                    continue

                for i, row in enumerate(table):
                    if i <= header_idx:
                        # header row itself (repeats on every page) — not data
                        continue

                    stats["rows_seen"] += 1

                    if row_is_blank(row):
                        stats["malformed_rows_skipped"] += 1
                        continue

                    date_raw = norm_cell(safe_col(row, col_map.get("date", -1)))
                    desc_raw = norm_cell(safe_col(row, col_map.get("description", -1))) if "description" in col_map else ""
                    balance_raw = norm_cell(safe_col(row, col_map.get("balance", -1)))
                    debit_raw = norm_cell(safe_col(row, col_map.get("debit", -1))) if "debit" in col_map else ""
                    credit_raw = norm_cell(safe_col(row, col_map.get("credit", -1))) if "credit" in col_map else ""

                    # Opening-balance / balance-forward seed row: not a transaction.
                    if looks_like_opening_balance(desc_raw) or (
                        not date_raw and desc_raw and not debit_raw and not credit_raw and balance_raw
                    ):
                        bal = parse_amount(balance_raw)
                        if bal is not None:
                            running_balance = bal
                        stats["header_rows_skipped"] += 1
                        continue

                    # Continuation row: date column empty but there's leftover
                    # description text that pdfplumber split into its own row
                    # (long multi-line cells sometimes overflow like this).
                    if not date_raw and not balance_raw and not debit_raw and not credit_raw:
                        fragment = " ".join(
                            norm_cell(c) for c in row if c and str(c).strip()
                        ).strip()
                        if fragment and last_txn is not None:
                            existing = last_txn.get("_description", "")
                            if fragment not in existing:
                                last_txn["_description"] = (existing + " " + fragment).strip()
                                # Re-derive type/merchant now that we have more text.
                                last_txn["transaction_type"] = guess_transaction_type(last_txn["_description"])
                                if not last_txn["merchant"]:
                                    last_txn["merchant"] = extract_merchant(
                                        last_txn["_description"], last_txn["transaction_type"]
                                    )
                            stats["empty_data_rows_skipped"] += 1
                            continue
                        else:
                            stats["malformed_rows_skipped"] += 1
                            continue

                    # Legacy page-collapsed shape check (only meaningful on the
                    # first real data row of a table — original Standard
                    # Chartered-style PDFs put the whole page in one row).
                    if is_page_collapsed_row(row, col_map):
                        txns, running_balance = extract_legacy_page_row(
                            page, row, col_map, running_balance, stats
                        )
                        for txn in txns:
                            txn["id"] = txn_id
                            all_rows.append(txn)
                            txn_id += 1
                            last_txn = None  # legacy rows are already complete; no merging needed
                        continue

                    # Normal case: this row already represents one transaction.
                    if not date_raw:
                        # No date and nothing matched above — can't safely
                        # treat this as a transaction.
                        stats["malformed_rows_skipped"] += 1
                        continue

                    txn, running_balance = build_transaction(col_map, row, running_balance)
                    txn["id"] = txn_id
                    all_rows.append(txn)
                    txn_id += 1
                    last_txn = txn
                    stats["transactions_extracted"] += 1

    # Strip internal-only fields before returning.
    for txn in all_rows:
        txn.pop("_description", None)

    total_skipped = (
        stats["malformed_rows_skipped"] + stats["header_rows_skipped"]
        + stats["footer_rows_skipped"] + stats["empty_data_rows_skipped"]
    )
    logger.info(
        "Parse summary — rows seen: %d | transactions extracted: %d | "
        "rows skipped: %d (malformed: %d, opening-balance/header: %d, footer: %d, "
        "merged-continuation/empty: %d) | malformed tables skipped: %d",
        stats["rows_seen"], len(all_rows), total_skipped,
        stats["malformed_rows_skipped"], stats["header_rows_skipped"],
        stats["footer_rows_skipped"], stats["empty_data_rows_skipped"],
        stats["malformed_tables_skipped"],
    )

    return all_rows


# ── CSV / convert() entry points (unchanged interface) ─────────────────────
def save_csv(transactions, csv_path):
    fieldnames = ["id", "debit_credit", "amount", "balance", "date", "time",
                  "transaction_type", "merchant"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(transactions)


def convert(pdf_path: "str | Path", output_dir: "str | Path" = "uploads") -> str:
    """
    Convert a bank-statement PDF to CSV and save it under output_dir.
    Called by services/input_router.py for .pdf uploads.

    Returns
    -------
    str — absolute path to the generated CSV.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    transactions = extract_transactions(str(pdf_path))

    csv_name = f"{pdf_path.stem}_{uuid.uuid4().hex[:8]}.csv"
    csv_path = output_dir / csv_name
    save_csv(transactions, csv_path)

    return str(csv_path.resolve())


def main():
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_csv.py <input.pdf> [output.csv]")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    pdf_path = sys.argv[1]
    csv_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace(".pdf", ".csv")

    print(f"Reading: {pdf_path}")
    transactions = extract_transactions(pdf_path)
    print(f"Found {len(transactions)} transactions")

    save_csv(transactions, csv_path)
    print(f"Saved:   {csv_path}")


if __name__ == "__main__":
    main()
