"""
services/risk_engine.py
-----------------------
Rule-based risk detection service for the Bank Statement Analysis Platform.

Pipeline position:
    normalizer → analytics → risk_engine (THIS) → anomaly_detector → llm_summary

Responsibilities:
    - Detect high-value transactions
    - Detect spending spikes
    - Detect repeated transactions
    - Detect excessive withdrawals
    - Detect rapid transactions (only when 'time' column is populated)

Does NOT:
    - Use any machine learning
    - Write to a database
    - Generate reports
    - Perform anomaly detection

Public interface expected by app.py:
    run(df: pd.DataFrame, report: dict) -> dict

    Returns:
        {
            "summary":               { ... },
            "flagged_transactions":  [ ... ]   # only risk_score > 0
        }
"""

from __future__ import annotations

import logging
from typing import Any

import json
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rule names
FLAG_HIGH_VALUE          = "HIGH_VALUE_TRANSACTION"
FLAG_SPENDING_SPIKE      = "SPENDING_SPIKE"
FLAG_REPEATED            = "REPEATED_TRANSACTION"
FLAG_EXCESSIVE_WITHDRAW  = "EXCESSIVE_WITHDRAWAL"
FLAG_RAPID               = "RAPID_TRANSACTION"

# Risk points per rule
POINTS: dict[str, int] = {
    FLAG_HIGH_VALUE:         15,
    FLAG_SPENDING_SPIKE:     10,
    FLAG_REPEATED:           10,
    FLAG_EXCESSIVE_WITHDRAW: 15,
    FLAG_RAPID:              10,
}

# Risk level thresholds
RISK_LEVELS = [
    (60, "CRITICAL"),
    (40, "HIGH"),
    (20, "MODERATE"),
    (0,  "LOW"),
]

# Withdrawal keywords (case-insensitive match on transaction_type)
WITHDRAWAL_KEYWORDS = {"atm", "cash", "withdrawal"}


# ===========================================================================
# HELPERS
# ===========================================================================

def _risk_level(score: int) -> str:
    """Map a numeric risk score to a named risk level."""
    for threshold, label in RISK_LEVELS:
        if score >= threshold:
            return label
    return "LOW"


def _safe_str(value: Any) -> str:
    """Return stripped string or empty string for NaN/None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _has_time(df: pd.DataFrame) -> bool:
    """
    Return True only when the 'time' column exists AND has at least one
    non-null, non-empty value.  If False, rapid-transaction detection is
    skipped entirely.
    """
    if "time" not in df.columns:
        return False
    populated = df["time"].dropna()
    populated = populated[populated.astype(str).str.strip() != ""]
    return not populated.empty


# ===========================================================================
# RISK ENGINE CLASS
# ===========================================================================

class RiskEngine:
    """
    Rule-based risk engine.

    Parameters
    ----------
    df : pd.DataFrame
        Standardized transaction DataFrame from normalizer.py / app.py.

    Usage
    -----
        engine = RiskEngine(df)
        result = engine.run()
        # result → { "summary": {...}, "flagged_transactions": [...] }
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df      = df.copy()
        self.n_rows  = len(df)

        # Per-index accumulator: { original_index: {"flags": [], "reasons": [], "score": 0} }
        self._risk: dict[Any, dict] = {}

        # Rule-level counters for summary
        self._counts: dict[str, int] = {
            FLAG_HIGH_VALUE:         0,
            FLAG_SPENDING_SPIKE:     0,
            FLAG_REPEATED:           0,
            FLAG_EXCESSIVE_WITHDRAW: 0,
            FLAG_RAPID:              0,
        }

        # Pre-compute typed columns once — used across multiple methods
        self._amounts  = pd.to_numeric(self.df.get("amount",  pd.Series(dtype=float)), errors="coerce")
        self._dates    = pd.to_datetime(self.df.get("date",   pd.Series(dtype="datetime64[ns]")), errors="coerce")

    # -----------------------------------------------------------------------
    # Internal flag recorder
    # -----------------------------------------------------------------------

    def _flag(self, idx: Any, flag_name: str, reason: str) -> None:
        """
        Record a risk flag against a transaction index.
        Accumulates flags/reasons; each flag adds its points once per transaction.
        """
        if idx not in self._risk:
            self._risk[idx] = {"flags": [], "reasons": [], "score": 0}

        entry = self._risk[idx]

        # Each flag is added once per transaction (idempotent per flag name)
        if flag_name not in entry["flags"]:
            entry["flags"].append(flag_name)
            entry["reasons"].append(reason)
            entry["score"] += POINTS[flag_name]
            self._counts[flag_name] += 1

    # -----------------------------------------------------------------------
    # Rule 1 — High Value Transaction
    # -----------------------------------------------------------------------

    def detect_high_value_transactions(self) -> None:
        """
        Flag any transaction whose amount exceeds 3× the median amount.

        Rule    : amount > 3 × median(amount)
        Points  : 15
        Flag    : HIGH_VALUE_TRANSACTION
        """
        amounts = self._amounts.dropna()
        if amounts.empty:
            logger.debug("HIGH_VALUE: no valid amounts — skipped.")
            return

        median_amt = amounts.median()
        threshold  = 3 * median_amt
        logger.debug("HIGH_VALUE threshold: %.2f  (median=%.2f)", threshold, median_amt)

        for idx in self.df.index:
            amt = self._amounts.get(idx)
            if pd.isna(amt):
                continue
            if amt > threshold:
                self._flag(
                    idx,
                    FLAG_HIGH_VALUE,
                    f"Amount {amt:.2f} exceeds 3x median transaction amount ({median_amt:.2f})",
                )

    # -----------------------------------------------------------------------
    # Rule 2 — Spending Spike Detection
    # -----------------------------------------------------------------------

    def detect_spending_spikes(self) -> None:
        """
        Flag all transactions on a day where total daily spend > 3× median daily spend.

        Rule    : daily_total > 3 × median(daily_totals)
        Points  : 10
        Flag    : SPENDING_SPIKE
        """
        if self._dates.dropna().empty or self._amounts.dropna().empty:
            logger.debug("SPENDING_SPIKE: missing date or amount data — skipped.")
            return

        # Build a working frame with date + amount
        work = pd.DataFrame({
            "amount": self._amounts,
            "date":   self._dates,
        }, index=self.df.index).dropna(subset=["date"])

        daily_totals = work.groupby("date")["amount"].sum()
        median_daily = daily_totals.median()
        threshold    = 3 * median_daily
        spike_dates  = set(daily_totals[daily_totals > threshold].index)

        logger.debug(
            "SPENDING_SPIKE threshold: %.2f  (median_daily=%.2f)  spike_days=%d",
            threshold, median_daily, len(spike_dates),
        )

        for idx, row_date in self._dates.items():
            if pd.isna(row_date):
                continue
            if row_date in spike_dates:
                day_total = daily_totals[row_date]
                self._flag(
                    idx,
                    FLAG_SPENDING_SPIKE,
                    f"Daily spending {day_total:.2f} on {row_date.date()} "
                    f"exceeded 3x historical median daily spending ({median_daily:.2f})",
                )

    # -----------------------------------------------------------------------
    # Rule 3 — Repeated Transaction Detection
    # -----------------------------------------------------------------------

    def detect_repeated_transactions(self) -> None:
        """
        Flag transactions where the same (merchant, amount) pair appears
        3+ times within any 24-hour rolling window.

        Rule    : count(same merchant + same amount within 24 h) >= 3
        Points  : 10
        Flag    : REPEATED_TRANSACTION
        """
        if "merchant" not in self.df.columns:
            logger.debug("REPEATED: no merchant column — skipped.")
            return

        work = pd.DataFrame({
            "merchant": self.df["merchant"].fillna("").astype(str).str.strip(),
            "amount":   self._amounts,
            "date":     self._dates,
        }, index=self.df.index).dropna(subset=["date", "amount"])

        # Remove rows with empty merchant (can't group meaningfully)
        work = work[work["merchant"] != ""]
        if work.empty:
            return

        work = work.sort_values("date")

        # For each unique (merchant, amount) group check 24-hour windows
        for (merchant, amount), grp in work.groupby(["merchant", "amount"]):
            if len(grp) < 3:
                continue

            timestamps = grp["date"].tolist()
            indices    = grp.index.tolist()

            # Sliding window: for each tx, count how many others are within 24 h
            for i, (ts_i, idx_i) in enumerate(zip(timestamps, indices)):
                window = [
                    idx_j
                    for j, (ts_j, idx_j) in enumerate(zip(timestamps, indices))
                    if i != j and abs((ts_i - ts_j).total_seconds()) <= 86400
                ]
                if len(window) >= 2:   # tx_i + at least 2 others = 3 total
                    self._flag(
                        idx_i,
                        FLAG_REPEATED,
                        f"Merchant '{merchant}' charged {amount:.2f} "
                        f"repeated {len(window) + 1}x within 24 hours",
                    )

    # -----------------------------------------------------------------------
    # Rule 4 — Excessive Withdrawal Detection
    # -----------------------------------------------------------------------

    def detect_excessive_withdrawals(self) -> None:
        """
        Flag withdrawal transactions on days with 4+ withdrawals.

        Withdrawal = transaction_type containing 'ATM', 'CASH', or 'WITHDRAWAL'
        (case-insensitive).

        Rule    : withdrawal_count_per_day >= 4
        Points  : 15
        Flag    : EXCESSIVE_WITHDRAWAL
        """
        if "transaction_type" not in self.df.columns:
            logger.debug("EXCESSIVE_WITHDRAWAL: no transaction_type column — skipped.")
            return

        txn_types = self.df["transaction_type"].fillna("").astype(str).str.upper()

        # Boolean mask: is this row a withdrawal?
        is_withdrawal = txn_types.apply(
            lambda t: any(kw in t for kw in {"ATM", "CASH", "WITHDRAWAL"})
        )

        work = pd.DataFrame({
            "is_withdrawal": is_withdrawal,
            "date":          self._dates,
        }, index=self.df.index)

        withdrawal_rows = work[work["is_withdrawal"] & work["date"].notna()]
        if withdrawal_rows.empty:
            return

        daily_counts  = withdrawal_rows.groupby("date").size()
        flagged_dates = set(daily_counts[daily_counts >= 4].index)

        logger.debug(
            "EXCESSIVE_WITHDRAWAL flagged_days=%d", len(flagged_dates)
        )

        for idx in withdrawal_rows.index:
            row_date = withdrawal_rows.loc[idx, "date"]
            if row_date in flagged_dates:
                count = int(daily_counts[row_date])
                self._flag(
                    idx,
                    FLAG_EXCESSIVE_WITHDRAW,
                    f"More than 4 withdrawals detected on {row_date.date()} "
                    f"(found {count})",
                )

    # -----------------------------------------------------------------------
    # Rule 5 — Rapid Transaction Detection
    # -----------------------------------------------------------------------

    def detect_rapid_transactions(self) -> None:
        """
        Flag transactions occurring within 2 minutes of another transaction.

        Skipped entirely when the 'time' column is absent or fully null.

        Rule    : time_diff_to_adjacent_transaction < 2 minutes
        Points  : 10
        Flag    : RAPID_TRANSACTION
        """
        if not _has_time(self.df):
            logger.info(
                "RAPID_TRANSACTION: 'time' column missing or empty — "
                "skipping rapid transaction detection as instructed."
            )
            return

        # Build full timestamps by combining date + time
        def _combine(row: pd.Series) -> pd.Timestamp | None:
            date_val = row.get("date")
            time_val = _safe_str(row.get("time"))
            if pd.isna(date_val) or not time_val:
                return None
            try:
                return pd.to_datetime(f"{date_val.date()} {time_val}")
            except Exception:
                return None

        timestamps = self.df.apply(_combine, axis=1)

        work = pd.DataFrame({
            "timestamp": timestamps,
        }, index=self.df.index).dropna(subset=["timestamp"])

        if len(work) < 2:
            return

        work = work.sort_values("timestamp")
        ts_list  = work["timestamp"].tolist()
        idx_list = work.index.tolist()

        two_min = pd.Timedelta(minutes=2)

        for i, (ts_i, idx_i) in enumerate(zip(ts_list, idx_list)):
            flagged = False
            # Check previous transaction
            if i > 0 and (ts_i - ts_list[i - 1]) < two_min:
                flagged = True
            # Check next transaction
            if not flagged and i < len(ts_list) - 1 and (ts_list[i + 1] - ts_i) < two_min:
                flagged = True

            if flagged:
                self._flag(
                    idx_i,
                    FLAG_RAPID,
                    "Transaction occurred within 2 minutes of another transaction",
                )

    # -----------------------------------------------------------------------
    # Risk level calculation (applied after all rules have run)
    # -----------------------------------------------------------------------

    def calculate_risk_levels(self) -> None:
        """Attach risk_level string to every accumulated risk entry."""
        for entry in self._risk.values():
            entry["risk_level"] = _risk_level(entry["score"])

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    def generate_summary(self) -> dict[str, Any]:
        """
        Build the summary section of the output.

        Returns
        -------
        dict with counts per rule, overall flagged count, average / max scores.
        """
        flagged_entries = [e for e in self._risk.values() if e["score"] > 0]
        scores          = [e["score"] for e in flagged_entries]

        return {
            "total_transactions":          self.n_rows,
            "flagged_transactions":        len(flagged_entries),
            "high_value_count":            self._counts[FLAG_HIGH_VALUE],
            "spending_spike_count":        self._counts[FLAG_SPENDING_SPIKE],
            "repeated_transaction_count":  self._counts[FLAG_REPEATED],
            "excessive_withdrawal_count":  self._counts[FLAG_EXCESSIVE_WITHDRAW],
            "rapid_transaction_count":     self._counts[FLAG_RAPID],
            "average_flagged_risk_score":  round(sum(scores) / len(scores), 2) if scores else 0.0,
            "max_risk_score":              max(scores) if scores else 0,
        }

    # -----------------------------------------------------------------------
    # Main run
    # -----------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute all detection rules and return the complete risk report.

        Returns
        -------
        dict:
            {
                "summary":              { ... },
                "flagged_transactions": [ ... ]   # only risk_score > 0
            }
        """
        if self.df.empty:
            logger.warning("RiskEngine received an empty DataFrame — returning zero report.")
            return {
                "summary": {
                    "total_transactions":         0,
                    "flagged_transactions":        0,
                    "high_value_count":            0,
                    "spending_spike_count":        0,
                    "repeated_transaction_count":  0,
                    "excessive_withdrawal_count":  0,
                    "rapid_transaction_count":     0,
                    "average_flagged_risk_score":  0.0,
                    "max_risk_score":              0,
                },
                "flagged_transactions": [],
            }

        logger.info("RiskEngine starting — %d transactions.", self.n_rows)

        # Run all rules
        self.detect_high_value_transactions()
        self.detect_spending_spikes()
        self.detect_repeated_transactions()
        self.detect_excessive_withdrawals()
        self.detect_rapid_transactions()

        # Attach risk levels
        self.calculate_risk_levels()

        # Build flagged_transactions list (only risk_score > 0)
        flagged: list[dict] = []
        for idx, entry in self._risk.items():
            if entry["score"] <= 0:
                continue

            row = self.df.loc[idx]

            date_val = self._dates.get(idx)
            date_str = date_val.strftime("%Y-%m-%d") if pd.notna(date_val) else None

            flagged.append({
                "transaction_index": int(idx) if isinstance(idx, (int, float)) else str(idx),
                "date":              date_str,
                "time":              _safe_str(row.get("time"))     or None,
                "merchant":          _safe_str(row.get("merchant")) or None,
                "amount":            float(self._amounts.get(idx))
                                     if pd.notna(self._amounts.get(idx)) else None,
                "debit_credit":      _safe_str(row.get("debit_credit")) or None,
                "transaction_type":  _safe_str(row.get("transaction_type")) or None,
                "risk_score":        entry["score"],
                "risk_level":        entry["risk_level"],
                "flags":             entry["flags"],
                "reasons":           entry["reasons"],
            })

        # Sort by risk_score descending so highest-risk transactions appear first
        flagged.sort(key=lambda r: r["risk_score"], reverse=True)

        summary = self.generate_summary()

        logger.info(
            "RiskEngine complete — %d/%d transactions flagged  "
            "(max_score=%d  avg_score=%.1f)",
            summary["flagged_transactions"],
            self.n_rows,
            summary["max_risk_score"],
            summary["average_flagged_risk_score"],
        )

        return {
            "summary":              summary,
            "flagged_transactions": flagged,
        }


# ===========================================================================
# app.py INTERFACE
# ===========================================================================

def run(df: pd.DataFrame, report: dict) -> dict:
    """
    Entry point called by app.py's step_optional_services().
    Also saves a standalone risk_report.json for inspection.
    """
    engine = RiskEngine(df)
    result = engine.run()

    # Save dedicated risk report
    output_path = Path("risk_report.json")
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    logger.info("Risk report saved → %s", output_path.resolve())

    return result   