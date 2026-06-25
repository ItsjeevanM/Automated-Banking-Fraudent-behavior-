"""
ocr_extractor.py
============================================================
Bank Statement OCR Extractor
Tested on: YES Bank scanned PDFs

Supports:
  - Digital PDFs (pdfplumber — fast, accurate)
  - Scanned PDFs (pdf2image + Tesseract or PaddleOCR)
  - Images (PNG, JPG)

Output columns (matches engineer_features() contract):
  date, amount, narration, balance, mode, debit_credit

Install:
  pip install pdfplumber pdf2image Pillow pytesseract
  sudo apt install tesseract-ocr   # Ubuntu
  brew install tesseract            # Mac
  
  Optional better accuracy:
  pip install paddlepaddle paddleocr
============================================================
"""
from __future__ import annotations

import logging
import re
import shutil
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger("ocr_extractor")

# ── Optional imports ──────────────────────────────────────────
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    from PIL import Image, ImageEnhance, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

HAS_TESSERACT = False
try:
    import pytesseract
    if shutil.which("tesseract"):
        HAS_TESSERACT = True
except ImportError:
    pass

HAS_PADDLE = False
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    HAS_PADDLE = True
except Exception:
    pass

# ── Constants ─────────────────────────────────────────────────
OUTPUT_COLUMNS  = ["date", "amount", "narration", "balance", "mode", "debit_credit"]

# Amounts above this are running balances, not transaction amounts
# Indian bank balances are typically in lakhs/crores (> 5 lakhs)
BAL_THRESHOLD   = 500_000

# ── Regex ─────────────────────────────────────────────────────
# Date: DD-MM-YYYY, DD.MM.YYYY, DD/MM/YYYY
_DATE_RE = re.compile(r'\b(\d{2}[-./]\d{2}[-./]\d{4})\b')

# Indian amount: 4,973.70 or 80,43,382.88 — must have decimal
_AMT_RE  = re.compile(r'(?<!\d)(\d{1,3}(?:,\d{2,3})+\.\d{2})(?!\d)')

# Negative indicator before amount
_NEG_RE  = re.compile(r'[-~](\d{1,3}(?:,\d{2,3})+\.\d{2})')

# Reference numbers to strip from narration
_REF_RE  = re.compile(r'\b[A-Z]?\d{8,}\b')

# Payment mode
_MODE_RE = re.compile(r'\b(NEFT|UPI|IMPS|RTGS|ATM|CASH|CHEQUE|POS)\b', re.I)

# Bank column header maps (for digital PDFs)
BANK_COL_MAPS = [
    {"txn date":"date","transaction date":"date","value date":"vdate",
     "narration":"narration","description":"narration","particulars":"narration",
     "withdrawal amt.":"debit","deposit amt.":"credit",
     "closing balance":"balance","balance":"balance"},
    {"date":"date","description":"narration","debit":"debit",
     "credit":"credit","balance":"balance"},
    {"transaction date":"date","transaction remarks":"narration",
     "debit amount":"debit","credit amount":"credit","balance (inr)":"balance"},
    {"tran date":"date","particulars":"narration","debit":"debit",
     "credit":"credit","balance":"balance"},
    {"date":"date","amount":"amount","narration":"narration",
     "balance":"balance","mode":"mode","withdrawal":"debit","deposit":"credit"},
]

# Noise words to exclude from narration
_NOISE = {
    'THE','AND','FOR','PVT','LTD','OAV','OAW','EFT','NEFT','UPI',
    'BANK','INDIA','eee','eet','Toe','aaa','ooo','www','nnn',
    'O/W','OW','AV','AG','NA','pvt','ltd','SERVICES'
}


def _to_float(s: str) -> Optional[float]:
    try:
        return float(str(s).replace(',', '').strip())
    except Exception:
        return None


def _clean_narration(text: str, max_words: int = 8) -> str:
    t = _DATE_RE.sub(' ', text)
    t = _REF_RE.sub(' ', t)
    t = _AMT_RE.sub(' ', t)
    t = re.sub(r'[|(){}\[\]~_\-=@#$%^&*]', ' ', t)
    t = re.sub(r'\b\d+\b', ' ', t)
    tokens = [
        x for x in t.split()
        if len(x) >= 3
        and re.search(r'[A-Za-z]', x)
        and x.upper() not in _NOISE
        and not re.fullmatch(r'[^A-Za-z]+', x)
    ]
    result = ' '.join(tokens[:max_words])
    return result if result.strip() else 'UNKNOWN'


def _parse_dates(series: pd.Series) -> pd.Series:
    formats = [
        "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
        "%d-%m-%y", "%d/%m/%y",
        "%Y-%m-%d",
    ]
    parsed  = pd.Series([pd.NaT] * len(series), index=series.index)
    mask    = pd.Series([True] * len(series), index=series.index)
    for fmt in formats:
        if not mask.any():
            break
        attempt = pd.to_datetime(series.where(mask), format=fmt, errors="coerce")
        hit = attempt.notna()
        parsed = parsed.where(~hit, attempt)
        mask   = mask & ~hit
    if mask.any():
        parsed = parsed.where(parsed.notna(),
                              pd.to_datetime(series.where(mask), errors="coerce"))
    return parsed


class BankStatementOCR:
    """
    Extract bank transactions from PDF or image.

    Usage:
        df = BankStatementOCR().extract("statement.pdf")
    """

    def __init__(self, dpi: int = 300):
        self.dpi      = dpi
        self.quality  = {}
        self._paddle  = None

    # ── Public ────────────────────────────────────────────────
    def extract(self, filepath: str) -> pd.DataFrame:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(filepath)

        ext = path.suffix.lower()
        logger.info("Extracting: %s", path.name)

        if ext == ".pdf":
            df = self._extract_pdf(path)
        elif ext in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
            df = self._extract_image(path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

        df = self._standardize(df)

        self.quality = {
            "rows"          : len(df),
            "valid_dates"   : int(df["date"].notna().sum()),
            "valid_amounts" : int(df["amount"].notna().sum()),
            "valid_balances": int(df["balance"].notna().sum()),
        }
        logger.info("Done — %s", self.quality)
        return df

    # ── PDF routing ───────────────────────────────────────────
    def _extract_pdf(self, path: Path) -> pd.DataFrame:
        # Try digital first
        if HAS_PDFPLUMBER:
            df = self._digital_pdf(path)
            if not df.empty and len(df) >= 3:
                logger.info("Used pdfplumber (digital PDF)")
                return df

        if not (HAS_PDF2IMAGE and HAS_PIL):
            raise RuntimeError(
                "pdf2image and Pillow required for scanned PDFs.\n"
                "pip install pdf2image Pillow"
            )

        # Page-by-page OCR (memory efficient for large files)
        all_rows: list[dict] = []
        import pdfplumber as _pl
        with _pl.open(str(path)) as pdf:
            n = len(pdf.pages)

        for page_num in range(1, n + 1):
            logger.info("OCR page %d/%d", page_num, n)
            pages = convert_from_path(
                str(path), dpi=self.dpi,
                first_page=page_num, last_page=page_num
            )
            if not pages:
                continue
            img = np.array(pages[0])
            rows = self._ocr_image(img)
            all_rows.extend(rows)

        return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()

    def _extract_image(self, path: Path) -> pd.DataFrame:
        if not HAS_PIL:
            raise RuntimeError("Pillow required: pip install Pillow")
        from PIL import Image as _Im
        img = np.array(_Im.open(str(path)).convert("RGB"))
        rows = self._ocr_image(img)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ── Digital PDF via pdfplumber ────────────────────────────
    def _digital_pdf(self, path: Path) -> pd.DataFrame:
        dfs = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    if len(table) < 2:
                        continue
                    df = self._table_to_df(table)
                    if df is not None and not df.empty:
                        dfs.append(df)
                if not dfs:
                    text = page.extract_text() or ""
                    rows = self._parse_text(text)
                    if rows:
                        dfs.append(pd.DataFrame(rows))
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    def _table_to_df(self, table: list) -> Optional[pd.DataFrame]:
        headers = [str(c or "").strip().lower() for c in table[0]]
        # find best column map
        best, best_score = {}, 0
        for cmap in BANK_COL_MAPS:
            score = sum(1 for h in headers if h in cmap)
            if score > best_score:
                best_score = score
                best = {h: cmap[h] for h in headers if h in cmap}
        if best_score < 2:
            return None
        rows = []
        for row in table[1:]:
            if not any(row):
                continue
            mapped = {}
            for h, cell in zip(headers, row):
                if h in best:
                    mapped[best[h]] = str(cell or "").strip()
            if mapped:
                rows.append(mapped)
        return pd.DataFrame(rows) if rows else None

    # ── OCR Engine ────────────────────────────────────────────
    def _ocr_image(self, img_arr: np.ndarray) -> list[dict]:
        """Try PaddleOCR first, fall back to Tesseract."""
        if HAS_PADDLE:
            try:
                return self._paddle_ocr(img_arr)
            except Exception as e:
                logger.warning("PaddleOCR failed (%s) — using Tesseract", e)

        if HAS_TESSERACT:
            return self._tesseract_ocr(img_arr)

        raise RuntimeError(
            "No OCR engine available.\n"
            "Install Tesseract:  sudo apt install tesseract-ocr\n"
            "Install PaddleOCR:  pip install paddlepaddle paddleocr"
        )

    def _preprocess(self, img_arr: np.ndarray):
        """Grayscale + contrast boost for better OCR."""
        from PIL import Image as _Im
        img = _Im.fromarray(img_arr).convert("L")
        img = ImageOps.autocontrast(img)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        return img

    def _tesseract_ocr(self, img_arr: np.ndarray) -> list[dict]:
        img = self._preprocess(img_arr)
        text = pytesseract.image_to_string(
            img, config="--psm 6 --oem 3 -c preserve_interword_spaces=1"
        )
        return self._parse_text(text)

    def _paddle_ocr(self, img_arr: np.ndarray) -> list[dict]:
        if self._paddle is None:
            self._paddle = _PaddleOCR(lang="en")
        result = self._paddle.ocr(img_arr)
        lines  = result[0] if result else []
        # Reconstruct text lines from bounding boxes grouped by Y
        from collections import defaultdict
        rows: dict[int, list] = defaultdict(list)
        for item in lines:
            bbox, (text, _) = item
            y = int((bbox[0][1] + bbox[2][1]) / 2 / 15) * 15
            rows[y].append((bbox[0][0], text))
        text = "\n".join(
            " ".join(t for _, t in sorted(words, key=lambda x: x[0]))
            for _, words in sorted(rows.items())
        )
        return self._parse_text(text)

    # ── Core text parser ──────────────────────────────────────
    def _parse_text(self, text: str) -> list[dict]:
        """
        Parse raw OCR text into transaction rows.

        Strategy:
          1. Find lines containing a date AND at least one Indian-format amount
          2. Separate amounts by threshold: < 500K = txn amount, >= 500K = balance
          3. Build context window (prev + current + next line) for narration + mode
          4. Deduplicate by (amount, balance)
        """
        all_lines = [l.strip() for l in text.split("\n") if l.strip()]
        rows: list[dict] = []

        for i, line in enumerate(all_lines):
            # Must have a date
            date_m = _DATE_RE.search(line)
            if not date_m:
                continue

            # Expand to window if no amounts on this line
            search_text = line
            for offset in (1, 2):
                if _AMT_RE.search(search_text):
                    break
                if i + offset < len(all_lines):
                    search_text += " " + all_lines[i + offset]

            amts_raw = _AMT_RE.findall(search_text)
            if not amts_raw:
                continue

            floats = [_to_float(a) for a in amts_raw]
            floats = [f for f in floats if f and f > 0.5]
            if not floats:
                continue

            # Split by threshold
            small = [f for f in floats if f < BAL_THRESHOLD]
            large = [f for f in floats if f >= BAL_THRESHOLD]

            if not small:
                continue  # only balance values, no txn amount

            amount = small[-1]

            # Balance: always negative in YES Bank (outflows)
            if large:
                balance = -large[-1]
            else:
                balance = None

            # Context window for narration + mode
            ctx_parts = []
            if i > 0:
                ctx_parts.append(all_lines[i - 1])
            ctx_parts.append(line)
            if i + 1 < len(all_lines) and not _DATE_RE.search(all_lines[i + 1]):
                ctx_parts.append(all_lines[i + 1])
            ctx = " ".join(ctx_parts)

            mode_m = _MODE_RE.search(ctx)
            mode = mode_m.group(1).upper() if mode_m else "NEFT"

            date_str = date_m.group(1).replace(".", "-").replace("/", "-")

            rows.append({
                "date"        : date_str,
                "amount"      : round(amount, 2),
                "narration"   : _clean_narration(ctx),
                "balance"     : round(balance, 2) if balance is not None else None,
                "mode"        : mode,
                "debit_credit": "DEBIT",
            })

        # Deduplicate (same amount + same balance = same row parsed twice)
        seen: set = set()
        unique: list[dict] = []
        for r in rows:
            key = (r["amount"], r["balance"])
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique

    # ── Standardize ───────────────────────────────────────────
    def _standardize(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        df = df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]

        # Merge debit/credit → amount if came from digital PDF table
        if "amount" not in df.columns:
            debit  = self._col_to_float(df, "debit")
            credit = self._col_to_float(df, "credit")
            df["amount"] = np.where(credit.fillna(0) > 0, credit, debit)
            if "debit_credit" not in df.columns:
                df["debit_credit"] = np.where(credit.fillna(0) > 0, "CREDIT", "DEBIT")

        if "date" in df.columns:
            df["date"] = _parse_dates(df["date"].astype(str))
        else:
            df["date"] = pd.NaT

        df["amount"]  = pd.to_numeric(df.get("amount"),  errors="coerce")
        df["balance"] = pd.to_numeric(df.get("balance"), errors="coerce")

        for col, default in [
            ("narration",    "UNKNOWN"),
            ("mode",         "UNKNOWN"),
            ("debit_credit", "DEBIT"),
        ]:
            if col not in df.columns:
                df[col] = default
            df[col] = df[col].fillna(default).astype(str)

        # Drop rows with no date AND no amount
        df = df[~(df["date"].isna() & df["amount"].isna())]

        for col in OUTPUT_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan if col in ("amount", "balance") else "UNKNOWN"

        return df[OUTPUT_COLUMNS].reset_index(drop=True)

    @staticmethod
    def _col_to_float(df: pd.DataFrame, col: str) -> pd.Series:
        if col not in df.columns:
            return pd.Series(np.nan, index=df.index)
        s = df[col].astype(str).str.replace(r"[^\d.\-]", "", regex=True)
        return pd.to_numeric(s, errors="coerce")


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python ocr_extractor.py <file.pdf> [output.csv]")
        sys.exit(1)

    filepath = sys.argv[1]
    outpath  = sys.argv[2] if len(sys.argv) > 2 else "output.csv"

    df = BankStatementOCR().extract(filepath)
    df.to_csv(outpath, index=False)

    print(f"\n{'='*55}")
    print(f"  Extracted : {len(df)} transactions")
    print(f"  Saved     : {outpath}")
    print(f"{'='*55}")
    print(df.to_string(index=False))
