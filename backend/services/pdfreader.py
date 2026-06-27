"""
Bank Statement PDF → CSV Converter

Extracts transactions from a Standard Chartered bank statement PDF.
Two key techniques:
  1. Balance-delta  — derives debit/credit and amount from consecutive
                      balance values, bypassing the misaligned
                      deposit/withdrawal columns entirely.
  2. Y-coordinate   — maps each transaction to the correct date by
                      comparing word positions on the page, fixing the
                      "one date per date-group" collapse in pdfplumber.

Output columns:
  id, debit_credit, amount, balance, date, time, transaction_type, merchant

Usage:
    python pdf_to_csv.py <input.pdf> [output.csv]

Requires:
    pip install pdfplumber
"""
import re
import csv
import sys
from collections import defaultdict
import pdfplumber

# ── column x-boundaries (points) ──────────────────────────────────────────────
DATE_X_MAX  = 100   # Date column:        x0 < 100
DESC_X_MIN  = 115   # Description column: 115 < x0 < 480
DESC_X_MAX  = 480   # (115 excludes the value-date column at ~84-110)

# ── patterns ───────────────────────────────────────────────────────────────────
TXN_START = re.compile(
    r"^(ATM WITHDRAWAL|PURCHASE|UPI/|CRADJ/|IMPS/|NEFT |IN\d{4}|CREDIT OF INTEREST|"
    r"NON SCB ATM|CGST|SGST|DISCOUNT ON|IMPS P2A|BALANCE FORWARD|TOTAL\b)",
    re.IGNORECASE,
)
DATE_RE    = re.compile(r"^\d{1,2} \w{3} \d{2}$")
SKIP_DESCS = {"BALANCE FORWARD", "TOTAL"}

# ── description helpers ────────────────────────────────────────────────────────
def group_descriptions(raw_text):
    """Split a merged multi-row description cell into one string per transaction."""
    lines  = [l.strip() for l in raw_text.split("\n") if l.strip()]
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

def extract_time(description):
    m = re.search(r"\b(\d{2}:\d{2}:\d{2})\b", description)
    return m.group(1) if m else ""

def guess_transaction_type(description):
    d = description.upper()
    if "ATM WITHDRAWAL" in d:                            return "ATM_WITHDRAWAL"
    if d.startswith("UPI/") or d.startswith("CRADJ/UPI"): return "UPI"
    if d.startswith("IMPS/"):                            return "IMPS"
    if d.startswith("NEFT") or re.match(r"^IN\d{4}", d): return "NEFT"
    if "PURCHASE" in d:                                  return "PURCHASE"
    if "CREDIT OF INTEREST" in d:                        return "INTEREST"
    if "NON SCB ATM" in d or "ATM USAGE" in d or \
       "IMPS P2A CHARGES" in d:                         return "CHARGES"
    if "CGST" in d or "SGST" in d:                      return "TAX"
    if "DISCOUNT" in d:                                  return "DISCOUNT"
    return "OTHER"

def extract_merchant(description, txn_type):
    desc = description.strip()
    if txn_type == "PURCHASE":
        m = re.match(
            r"PURCHASE\s+(.+?)(?:\s{2,}|\s+IN\s|\s+\d{2}:\d{2}:\d{2})",
            desc, re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    if txn_type == "UPI":
        parts = [p.strip() for p in desc.split("/") if p.strip()]
        for idx in (4, 3, 2):
            if len(parts) > idx:
                c = parts[idx]
                if c and not re.match(r"^\d+$", c):
                    return c
    if txn_type == "IMPS":
        lines = [l.strip() for l in desc.splitlines() if l.strip()]
        if len(lines) >= 3:
            return lines[2]
    if txn_type == "NEFT":
        lines = [l.strip() for l in desc.splitlines() if l.strip()]
        if len(lines) >= 3:
            return lines[2]
    return ""

# ── balance helpers ────────────────────────────────────────────────────────────
def parse_amount(text):
    if not text:
        return None
    try:
        return round(float(text.replace(",", "").strip()), 2)
    except ValueError:
        return None

def classify_from_delta(prev_bal, curr_bal):
    """Derive debit/credit and amount purely from consecutive balance values."""
    if prev_bal is None or curr_bal is None:
        return "", None
    delta = round(curr_bal - prev_bal, 2)
    if   delta < 0: return "DEBIT",  abs(delta)
    elif delta > 0: return "CREDIT", abs(delta)
    else:           return "DEBIT",  0.0

# ── y-coordinate date mapping ──────────────────────────────────────────────────
def build_date_map(page):
    """
    Return {y_coord: date_string} for every date visible in the Date column.
    A date is 3 consecutive tokens matching DD Mon YY.
    """
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
    """
    Return an ordered list of y-coordinates, one per transaction start
    in the Description column.
    DESC_X_MIN=115 deliberately excludes the value-date column (~x=84-110)
    so tokens like "19" (year) don't pollute the line match.
    """
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
    """The correct date is the closest date entry at or above txn_y."""
    best = ""
    for dy in sorted(date_map.keys()):
        if dy <= txn_y:
            best = date_map[dy]
        else:
            break
    return best

# ── per-page extraction ────────────────────────────────────────────────────────
def extract_page_transactions(page, row, opening_balance):
    """
    Extract all transactions from one pdfplumber table row (which represents
    an entire page's worth of data collapsed into one row per column).
    Returns (transactions_list, closing_balance).
    """
    def col(i):
        return (row[i] if i < len(row) else None) or ""
        
    bals_raw = [l.strip() for l in col(6).split("\n") if l.strip()]
    bals     = [parse_amount(b) for b in bals_raw]
    descs    = group_descriptions(col(2))
    
    n = min(len(descs), len(bals))
    descs, bals = descs[:n], bals[:n]
    
    date_map = build_date_map(page)
    txn_ys   = build_txn_y_list(page)
    
    prev_bal     = opening_balance
    transactions = []
    txn_idx      = 0   # index into txn_ys
    
    for desc, curr_bal in zip(descs, bals):
        first_line = desc.splitlines()[0].strip()
        if first_line.upper() in SKIP_DESCS or first_line.upper().startswith("TOTAL"):
            prev_bal = curr_bal
            txn_idx += 1
            continue
            
        txn_y    = txn_ys[txn_idx] if txn_idx < len(txn_ys) else None
        date_val = date_for_y(txn_y, date_map) if txn_y is not None else ""
        txn_idx += 1
        
        debit_credit, amount = classify_from_delta(prev_bal, curr_bal)
        txn_type = guess_transaction_type(desc)
        merchant = extract_merchant(desc, txn_type)
        time_val = extract_time(desc)
        
        transactions.append({
            "debit_credit":     debit_credit,
            "amount":           amount,
            "balance":          curr_bal,
            "date":             date_val,
            "time":             time_val,
            "transaction_type": txn_type,
            "merchant":         merchant,
        })
        prev_bal = curr_bal
        
    return transactions, prev_bal

# ── main extraction ────────────────────────────────────────────────────────────
HEADER_CELLS = {"DATE", "VALUE DATE", "VALUE\nDATE"}
SKIP_STARTS  = ("BRANCH", "MR ", "SA/", "REWARD", "SCHEME")

def extract_transactions(pdf_path):
    all_rows        = []
    txn_id          = 1
    running_balance = None
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    first = (row[0] or "").strip()
                    if first.upper() in HEADER_CELLS:
                        continue
                    if any(first.upper().startswith(p.upper()) for p in SKIP_STARTS):
                        continue
                        
                    # Seed opening balance from the first BALANCE FORWARD row
                    if running_balance is None:
                        descs = group_descriptions(row[2] or "")
                        bals  = [l.strip() for l in (row[6] or "").split("\n") if l.strip()]
                        if descs and descs[0].strip().upper() == "BALANCE FORWARD" and bals:
                            running_balance = parse_amount(bals[0])
                            
                    txns, running_balance = extract_page_transactions(
                        page, row, running_balance
                    )
                    
                    for txn in txns:
                        txn["id"] = txn_id
                        all_rows.append(txn)
                        txn_id += 1
                        
    return all_rows

def main():
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_csv.py <input.pdf> [output.csv]")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    csv_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace(".pdf", ".csv")
    
    print(f"Reading: {pdf_path}")
    transactions = extract_transactions(pdf_path)
    print(f"Found {len(transactions)} transactions")
    
    fieldnames = ["id", "debit_credit", "amount", "balance", "date", "time",
                  "transaction_type", "merchant"]
                  
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(transactions)
        
    print(f"Saved:   {csv_path}")

if __name__ == "__main__":
    main()