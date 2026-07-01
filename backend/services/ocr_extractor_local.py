import csv
import re
import sys
import os
import uuid
from pathlib import Path
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

COLUMNS = ["id", "debit_credit", "amount", "balance", "date", "time", "transaction_type", "merchant"]

DATE_START  = re.compile(r"^\d{2}-\d{2}-\d{4}")
DATETIME_RE = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(\d{2}:\d{2})")
AMOUNT_RE   = re.compile(r"-?[\d,]+\.\d{2}")
JUNK_RE     = re.compile(r"[\|_\[\]{}]+")

def ocr_image(image_path: str) -> str:
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, config="--psm 6")
    return text

def group_transaction_lines(raw_text: str) -> list[str]:
    lines = raw_text.split("\n")
    blocks: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if DATE_START.match(stripped):
            blocks.append([stripped])
        elif blocks:
            blocks[-1].append(stripped)
    return [" ".join(b) for b in blocks]

def extract_amounts(text: str) -> list[str]:
    return AMOUNT_RE.findall(text)

def determine_dr_cr(merchant: str) -> str:
    m = merchant.upper()
    if re.search(r"\bCR[-\s]", m) or re.search(r"\bCR$", m):
        return "CR"
    if "CHQ DEP" in m or "CHEQUE DEP" in m or "CASH DEP" in m:
        return "CR"
    if re.search(r"NEFT\s+CR", m) or "NEFT-CR" in m:
        return "CR"
    if "O/W" in m or "NEFT O/W" in m:
        return "DR"
    if "RTGS" in m and "CR" not in m:
        return "DR"
    if "NET TXN" in m:
        return "DR"
    return "DR"

def infer_tx_type(merchant: str) -> str:
    prefixes = ["NEFT", "RTGS", "IMPS", "UPI", "CHQ DEP", "CHQ",
                "ATM", "NET TXN", "CASH", "POS", "ECS", "NACH",
                "ACH", "DD", "IFT", "EMI"]
    upper = merchant.upper().strip()
    for p in prefixes:
        if upper.startswith(p):
            return p
    return upper.split()[0] if upper else ""

def clean_merchant(raw: str) -> str:
    cleaned = JUNK_RE.sub(" ", raw)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

def parse_transaction(block: str, row_id: int) -> dict | None:
    m_dt = DATETIME_RE.match(block)
    if not m_dt:
        return None
    date = m_dt.group(1)
    time = m_dt.group(2)
    remainder = block[m_dt.end():].strip()
    
    amounts = extract_amounts(remainder)
    if not amounts:
        return None
        
    balance = amounts[-1]
    amount  = amounts[-2] if len(amounts) >= 2 else ""
    
    merchant_raw = remainder
    for a in amounts:
        merchant_raw = merchant_raw.replace(a, " ", 1)
    merchant_raw = re.sub(r"\b\d{10,}\b", " ", merchant_raw)
    merchant_raw = re.sub(r"\b\d{2}-\d{2}-\d{4}\b", " ", merchant_raw)
    merchant = clean_merchant(merchant_raw)
    
    debit_credit = determine_dr_cr(merchant)
    tx_type = infer_tx_type(merchant)
    
    return {
        "id":               row_id,
        "debit_credit":     debit_credit,
        "amount":           amount,
        "balance":          balance,
        "date":             date,
        "time":             time,
        "transaction_type": tx_type,
        "merchant":         merchant,
    }

def save_csv(records: list[dict], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

def process(image_path: str, output_csv: str = None) -> str:
    if output_csv is None:
        output_csv = Path(image_path).stem + "_transactions.csv"
        
    print(f"[OCR] Reading image: {image_path}")
    raw_text = ocr_image(image_path)
    
    print("[OCR] Grouping transaction lines...")
    blocks = group_transaction_lines(raw_text)
    print(f"[OCR] Found {len(blocks)} transaction blocks")
    
    records = []
    for i, block in enumerate(blocks, start=1):
        rec = parse_transaction(block, i)
        if rec:
            records.append(rec)
            
    print(f"[OCR] Parsed {len(records)} transactions")
    save_csv(records, output_csv)
    print(f"[OCR] CSV saved -> {output_csv}")
    return output_csv

def convert(image_path: str | Path, output_dir: str | Path = "uploads") -> str:
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_name = f"{image_path.stem}_{uuid.uuid4().hex[:8]}.csv"
    csv_path = output_dir / csv_name
    
    process(str(image_path), str(csv_path))
    return str(csv_path.resolve())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr_module_local.py <image_path> [output.csv]")
        sys.exit(1)
    img = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    process(img, out)