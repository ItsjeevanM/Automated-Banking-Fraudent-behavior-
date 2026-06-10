"""
services/risk_engine.py
-----------------------
Rule-based risk detection service for the Bank Statement Analysis Platform.

Pipeline position:
    normalizer → analytics → risk_engine (THIS) → anomaly_detector → llm_summary

Responsibilities  (rule-based only, zero ML):
    1. HIGH_VALUE_TRANSACTION     — per-channel median + absolute floor
    2. SPENDING_SPIKE             — requires min 7 days of history
    3. REPEATED_TRANSACTION       — narration fallback + ±2 % amount tolerance
    4. EXCESSIVE_WITHDRAWAL       — scans both transaction_type AND narration
    5. RAPID_TRANSACTION          — rolling burst window (skipped if time absent)
    6. LATE_NIGHT_TRANSACTION     — new: time-of-day gate (skipped if time absent)
    7. BALANCE_DROP_ALERT         — new: single-txn % balance drain

Does NOT:
    - Use any machine learning
    - Write to a database
    - Generate reports
    - Perform anomaly detection

Public interface (called by app.py):
    run(df: pd.DataFrame, report: dict) -> dict

Output shape:
    {
        "summary":               { ... },
        "flagged_transactions":  [ ... ]   # only risk_score > 0
    }
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ===========================================================================
# ── CONFIGURABLE CONSTANTS ──────────────────────────────────────────────────
# All thresholds and tuning knobs live here.
# Change these without touching any logic below.
# ===========================================================================

# ── Rule 1: HIGH_VALUE_TRANSACTION ──────────────────────────────────────────
# Multiplier applied to the per-channel median amount.
HIGH_VALUE_MULTIPLIER: float = 5.0

# Absolute floor — a transaction must exceed BOTH the multiplier threshold
# AND this floor to be flagged. Prevents the rule firing on tiny-median
# channels (e.g. a channel whose median is ₹10 would flag ₹50 otherwise).
HIGH_VALUE_FLOOR: float = 5_000.0

# ── Rule 2: SPENDING_SPIKE ───────────────────────────────────────────────────
# Minimum number of unique calendar days required before the rule runs.
# Avoids meaningless medians on brand-new or single-day datasets.
SPENDING_SPIKE_MIN_DAYS: int = 7

# Multiplier applied to median daily spend.
SPENDING_SPIKE_MULTIPLIER: float = 4.0

# Absolute minimum daily total that must be exceeded (same idea as above).
SPENDING_SPIKE_FLOOR: float = 10_000.0

# ── Rule 3: REPEATED_TRANSACTION ────────────────────────────────────────────
# Minimum occurrences of (key, ~amount) within the time window to flag.
REPEATED_MIN_COUNT: int = 3

# Rolling time window in hours.
REPEATED_WINDOW_HOURS: int = 24

# Amount tolerance for "same amount" — fraction of the reference amount.
# 0.02 = within ±2 %.
REPEATED_AMOUNT_TOLERANCE: float = 0.02

# ── Rule 4: EXCESSIVE_WITHDRAWAL ────────────────────────────────────────────
# Minimum withdrawals per calendar day to trigger the flag.
EXCESSIVE_WITHDRAWAL_THRESHOLD: int = 4

# ── Rule 5: RAPID_TRANSACTION ───────────────────────────────────────────────
# Rolling window width in minutes.
RAPID_WINDOW_MINUTES: int = 10

# Minimum transactions inside the window to flag (including the transaction
# itself), so 5 means "5 or more transactions in 10 minutes".
RAPID_BURST_THRESHOLD: int = 5

# ── Rule 6: LATE_NIGHT_TRANSACTION ──────────────────────────────────────────
# Night window: [LATE_NIGHT_START_HOUR, 24) ∪ [0, LATE_NIGHT_END_HOUR).
LATE_NIGHT_START_HOUR: int = 23   # 11 PM
LATE_NIGHT_END_HOUR: int   = 5    # 5 AM

# Only flag night transactions above this amount.
LATE_NIGHT_MIN_AMOUNT: float = 2_000.0

# ── Rule 7: BALANCE_DROP_ALERT ───────────────────────────────────────────────
# Fraction of the day's opening balance that, if lost in a single transaction,
# triggers the flag.  0.40 = 40 %.
BALANCE_DROP_PCT_THRESHOLD: float = 0.40

# ── Risk points per rule ─────────────────────────────────────────────────────
POINTS: dict[str, int] = {
    "HIGH_VALUE_TRANSACTION":    15,
    "SPENDING_SPIKE":            10,
    "REPEATED_TRANSACTION":      10,
    "EXCESSIVE_WITHDRAWAL":      15,
    "RAPID_TRANSACTION":         10,
    "LATE_NIGHT_TRANSACTION":    10,
    "BALANCE_DROP_ALERT":        15,
}

# ── Risk level bands ─────────────────────────────────────────────────────────
# Evaluated top-to-bottom; first match wins.
RISK_LEVELS: list[tuple[int, str]] = [
    (60, "CRITICAL"),
    (40, "HIGH"),
    (20, "MODERATE"),
    (0,  "LOW"),
]

# ── Withdrawal keywords ──────────────────────────────────────────────────────
# Checked (case-insensitive) against BOTH transaction_type and narration.
WITHDRAWAL_KEYWORDS: set[str] = {
    "atm", "cash", "withdrawal", "cash wdl",
    "cashout", "cdm", "pos cash", "wdrawal", "wdrl",
}


# ===========================================================================
# ── INTERNAL HELPERS ────────────────────────────────────────────────────────
# ===========================================================================

def _risk_level(score: int) -> str:
    """Map a numeric risk score to its named level."""
    for threshold, label in RISK_LEVELS:
        if score >= threshold:
            return label
    return "LOW"


def _safe_str(value: Any) -> str:
    """Return stripped string; empty string for NaN / None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _has_time(df: pd.DataFrame) -> bool:
    """
    True only when 'time' exists and has at least one non-null, non-empty
    value.  Rules that need timestamps skip themselves when this is False.
    """
    if "time" not in df.columns:
        return False
    populated = df["time"].dropna()
    return not populated[populated.astype(str).str.strip() != ""].empty


# ---------------------------------------------------------------------------
# Merchant key resolution — three-tier, future-proof
# ---------------------------------------------------------------------------

# Regex strips trailing numeric IDs from narration strings like
# "UPI/BHARATPE6", "UPI/32378", "NEFT/00012345" so they cluster correctly.
_TRAILING_ID_RE = re.compile(r"[/\s_-]?\d{4,}$")


def _resolve_merchant_key(merchant: Any, mode: Any, narration: Any) -> str | None:
    """
    Three-tier merchant key resolution.

    Tier 1 — merchant column populated → use as-is (highest fidelity).
              When a vendor API or manual mapping fills this column later,
              the grouping automatically upgrades with zero code changes.

    Tier 2 — merchant null but mode available → "MODE::cleaned_narration"
              e.g. "UPI::BHARATPE", "NEFT::SALARY TRANSFER"
              The mode prefix keeps channels from colliding (a NEFT named
              "HDFC" and a UPI named "HDFC" are different counterparties).

    Tier 3 — neither available → stripped narration only.
              Removes trailing transaction IDs so near-duplicates cluster.

    Returns None if no usable key can be constructed (fully null row).
    """
    m = _safe_str(merchant)
    if m:
        return m.upper()                                    # ── Tier 1

    mo  = _safe_str(mode).upper()
    nar = _safe_str(narration).upper()
    nar = _TRAILING_ID_RE.sub("", nar).strip()

    if mo and nar:
        return f"{mo}::{nar}"                               # ── Tier 2
    if mo:
        return mo
    if nar:
        return nar                                          # ── Tier 3
    return None


# ---------------------------------------------------------------------------
# Channel extraction for per-channel HIGH_VALUE medians
# ---------------------------------------------------------------------------

def _extract_channel(mode: Any, narration: Any) -> str:
    """
    Derive a payment channel label from mode / narration.

    Priority:
      1. mode column (UPI, NEFT, IMPS, CARD, ATM, CASH, OTHERS …)
      2. Leading token of narration (e.g. "UPI/GPAY" → "UPI")
      3. "UNKNOWN" as fallback

    All channels are upper-cased so comparisons are case-insensitive.
    """
    mo = _safe_str(mode).upper()
    if mo and mo not in ("", "OTHERS"):
        return mo

    nar = _safe_str(narration).upper()
    if nar:
        # Take the part before the first "/" or space
        token = re.split(r"[/\s]", nar)[0]
        if token:
            return token

    return "UNKNOWN"


# ===========================================================================
# ── RISK ENGINE ──────────────────────────────────────────────────────────────
# ===========================================================================

class RiskEngine:
    """
    Rule-based risk engine.

    Parameters
    ----------
    df : pd.DataFrame
        Standardized transaction DataFrame produced by normalizer.py / app.py.

    Usage
    -----
        engine = RiskEngine(df)
        result = engine.run()
        # { "summary": {...}, "flagged_transactions": [...] }
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df     = df.copy()
        self.n_rows = len(df)

        # Per-index risk accumulator
        # { original_index: {"flags": [], "reasons": [], "score": 0} }
        self._risk: dict[Any, dict] = {}

        # Rule-level counters for the summary section
        self._counts: dict[str, int] = {flag: 0 for flag in POINTS}

        # ── Pre-compute typed series used across multiple rules ──────────
        self._amounts  = pd.to_numeric(
            self.df.get("amount",  pd.Series(dtype=float)), errors="coerce"
        )
        self._dates    = pd.to_datetime(
            self.df.get("date",    pd.Series(dtype="datetime64[ns]")), errors="coerce"
        )
        self._balances = pd.to_numeric(
            self.df.get("balance", self.df.get("currentBalance", pd.Series(dtype=float))),
            errors="coerce"
        )

        # Resolve channel for every row (used by HIGH_VALUE)
        mode_col     = self.df.get("mode",      pd.Series("", index=self.df.index))
        narration_col= self.df.get("narration",  pd.Series("", index=self.df.index))
        merchant_col = self.df.get("merchant",   pd.Series("", index=self.df.index))

        self._channels = pd.Series(
            [_extract_channel(mode_col.get(i,""), narration_col.get(i,""))
             for i in self.df.index],
            index=self.df.index,
        )
        self._merchant_keys = pd.Series(
            [_resolve_merchant_key(
                merchant_col.get(i,""),
                mode_col.get(i,""),
                narration_col.get(i,""),
             ) for i in self.df.index],
            index=self.df.index,
        )

    # -----------------------------------------------------------------------
    # Internal flag recorder
    # -----------------------------------------------------------------------

    def _flag(self, idx: Any, flag_name: str, reason: str) -> None:
        """
        Record one risk flag against a transaction index.
        Each flag name is recorded once per transaction (idempotent).
        Points accumulate across distinct flags.
        """
        if idx not in self._risk:
            self._risk[idx] = {"flags": [], "reasons": [], "score": 0}
        entry = self._risk[idx]
        if flag_name not in entry["flags"]:
            entry["flags"].append(flag_name)
            entry["reasons"].append(reason)
            entry["score"] += POINTS[flag_name]
            self._counts[flag_name] += 1

    # -----------------------------------------------------------------------
    # Rule 1 — High Value Transaction (per-channel median + absolute floor)
    # -----------------------------------------------------------------------

    def detect_high_value_transactions(self) -> None:
        """
        Flag transactions that are unusually large relative to their own
        payment channel (UPI, NEFT, IMPS, …).

        Why per-channel:
            A ₹50,000 NEFT salary credit is routine; a ₹50,000 UPI payment
            at midnight is not.  Using one global median conflates the two.

        Rule:
            amount > HIGH_VALUE_MULTIPLIER × channel_median
            AND amount > HIGH_VALUE_FLOOR
        """
        flag = "HIGH_VALUE_TRANSACTION"

        # Build per-channel medians
        work = pd.DataFrame({
            "amount":  self._amounts,
            "channel": self._channels,
        }, index=self.df.index).dropna(subset=["amount"])

        channel_medians: dict[str, float] = (
            work.groupby("channel")["amount"].median().to_dict()
        )
        logger.debug("HIGH_VALUE channel medians: %s", channel_medians)

        for idx in self.df.index:
            amt = self._amounts.get(idx)
            if pd.isna(amt):
                continue
            channel  = self._channels.get(idx, "UNKNOWN")
            median_c = channel_medians.get(channel)
            if median_c is None or median_c == 0:
                continue

            threshold = HIGH_VALUE_MULTIPLIER * median_c
            if amt > threshold and amt > HIGH_VALUE_FLOOR:
                self._flag(
                    idx, flag,
                    f"Amount {amt:,.2f} exceeds {HIGH_VALUE_MULTIPLIER}× "
                    f"{channel} channel median ({median_c:,.2f}) "
                    f"and absolute floor ({HIGH_VALUE_FLOOR:,.0f})",
                )

    # -----------------------------------------------------------------------
    # Rule 2 — Spending Spike (requires minimum history)
    # -----------------------------------------------------------------------

    def detect_spending_spikes(self) -> None:
        """
        Flag all transactions on a day where total daily spend exceeds
        SPENDING_SPIKE_MULTIPLIER × median daily spend.

        Guards:
            • Skip entirely if fewer than SPENDING_SPIKE_MIN_DAYS unique
              dates exist — avoids meaningless medians on sparse datasets.
            • Daily total must also exceed SPENDING_SPIKE_FLOOR so that
              accounts with tiny median spend aren't swamped by flags.
        """
        flag = "SPENDING_SPIKE"

        unique_days = self._dates.dropna().dt.normalize().nunique()
        if unique_days < SPENDING_SPIKE_MIN_DAYS:
            logger.info(
                "SPENDING_SPIKE: only %d unique days (need %d) — skipped.",
                unique_days, SPENDING_SPIKE_MIN_DAYS,
            )
            return

        work = pd.DataFrame({
            "amount": self._amounts,
            "date":   self._dates.dt.normalize(),
        }, index=self.df.index).dropna(subset=["date"])

        daily_totals  = work.groupby("date")["amount"].sum()
        median_daily  = daily_totals.median()
        threshold     = SPENDING_SPIKE_MULTIPLIER * median_daily

        spike_dates = set(
            daily_totals[
                (daily_totals > threshold) & (daily_totals > SPENDING_SPIKE_FLOOR)
            ].index
        )
        logger.debug(
            "SPENDING_SPIKE: median_daily=%.2f  threshold=%.2f  spike_days=%d",
            median_daily, threshold, len(spike_dates),
        )

        for idx in self.df.index:
            d = self._dates.get(idx)
            if pd.isna(d):
                continue
            day = d.normalize()
            if day in spike_dates:
                self._flag(
                    idx, flag,
                    f"Daily spend {daily_totals[day]:,.2f} on {day.date()} "
                    f"exceeded {SPENDING_SPIKE_MULTIPLIER}× median daily spend "
                    f"({median_daily:,.2f}) and floor ({SPENDING_SPIKE_FLOOR:,.0f})",
                )

    # -----------------------------------------------------------------------
    # Rule 3 — Repeated Transaction (merchant fallback + amount tolerance)
    # -----------------------------------------------------------------------

    def detect_repeated_transactions(self) -> None:
        """
        Flag (key, ~amount) pairs appearing REPEATED_MIN_COUNT+ times
        within a REPEATED_WINDOW_HOURS rolling window.

        Merchant key resolution (future-proof, three tiers):
            Tier 1 → merchant column  (exact vendor name when available)
            Tier 2 → mode::narration  (e.g. "UPI::BHARATPE")
            Tier 3 → stripped narration only

        Amount tolerance:
            Two amounts are "the same" if they differ by ≤ REPEATED_AMOUNT_TOLERANCE.
            This absorbs rounding differences and small convenience fees.
        """
        flag = "REPEATED_TRANSACTION"

        work = pd.DataFrame({
            "key":    self._merchant_keys,
            "amount": self._amounts,
            "date":   self._dates,
        }, index=self.df.index).dropna(subset=["date", "amount"])
        work = work[work["key"].notna() & (work["key"] != "")]

        if work.empty:
            logger.debug("REPEATED: no usable (key, amount, date) rows — skipped.")
            return

        work = work.sort_values("date")
        window_td = pd.Timedelta(hours=REPEATED_WINDOW_HOURS)

        # Group by key first to limit comparisons
        for key, grp in work.groupby("key"):
            if len(grp) < REPEATED_MIN_COUNT:
                continue

            timestamps = grp["date"].tolist()
            amounts    = grp["amount"].tolist()
            indices    = grp.index.tolist()

            for i, (ts_i, amt_i, idx_i) in enumerate(
                zip(timestamps, amounts, indices)
            ):
                # Find all rows within window AND within amount tolerance
                similar = [
                    idx_j
                    for j, (ts_j, amt_j, idx_j) in enumerate(
                        zip(timestamps, amounts, indices)
                    )
                    if i != j
                    and abs((ts_i - ts_j).total_seconds()) <= window_td.total_seconds()
                    and (
                        abs(amt_i - amt_j) / amt_i <= REPEATED_AMOUNT_TOLERANCE
                        if amt_i != 0 else amt_j == 0
                    )
                ]

                # similar contains the *other* matching rows;
                # total cluster = len(similar) + 1 (for tx_i itself)
                if len(similar) >= REPEATED_MIN_COUNT - 1:
                    self._flag(
                        idx_i, flag,
                        f"Key '{key}' with amount ~{amt_i:,.2f} repeated "
                        f"{len(similar)+1}× within {REPEATED_WINDOW_HOURS}h "
                        f"(±{REPEATED_AMOUNT_TOLERANCE*100:.0f}% tolerance)",
                    )

    # -----------------------------------------------------------------------
    # Rule 4 — Excessive Withdrawal (checks both columns)
    # -----------------------------------------------------------------------

    def detect_excessive_withdrawals(self) -> None:
        """
        Flag withdrawal transactions on days with >= EXCESSIVE_WITHDRAWAL_THRESHOLD
        withdrawals.

        Withdrawal detection scans BOTH transaction_type AND narration
        (case-insensitive substring match against WITHDRAWAL_KEYWORDS) so
        formats like "ATM/", "CASH WDL", "CDM", "CASHOUT" are all caught.
        """
        flag = "EXCESSIVE_WITHDRAWAL"

        txn_type_col = self.df.get("transaction_type",
                                    pd.Series("", index=self.df.index))
        narration_col= self.df.get("narration",
                                    pd.Series("", index=self.df.index))

        def _is_withdrawal(idx: Any) -> bool:
            combined = (
                _safe_str(txn_type_col.get(idx, "")).lower()
                + " "
                + _safe_str(narration_col.get(idx, "")).lower()
            )
            return any(kw in combined for kw in WITHDRAWAL_KEYWORDS)

        is_withdrawal = pd.Series(
            {idx: _is_withdrawal(idx) for idx in self.df.index}
        )

        work = pd.DataFrame({
            "is_withdrawal": is_withdrawal,
            "date":          self._dates.dt.normalize(),
        }, index=self.df.index)

        withdrawal_rows = work[work["is_withdrawal"] & work["date"].notna()]
        if withdrawal_rows.empty:
            return

        daily_counts  = withdrawal_rows.groupby("date").size()
        flagged_dates = set(
            daily_counts[daily_counts >= EXCESSIVE_WITHDRAWAL_THRESHOLD].index
        )

        for idx in withdrawal_rows.index:
            day = withdrawal_rows.loc[idx, "date"]
            if day in flagged_dates:
                self._flag(
                    idx, flag,
                    f"{int(daily_counts[day])} withdrawals on {day.date()} "
                    f"(threshold: {EXCESSIVE_WITHDRAWAL_THRESHOLD})",
                )

    # -----------------------------------------------------------------------
    # Rule 5 — Rapid Transaction (rolling burst window)
    # -----------------------------------------------------------------------

    def detect_rapid_transactions(self) -> None:
        """
        Flag transactions that are part of a burst: >= RAPID_BURST_THRESHOLD
        transactions within a RAPID_WINDOW_MINUTES rolling window.

        Skipped entirely when 'time' is absent or fully null — same behaviour
        as before.

        Why rolling window instead of pairwise gap:
            3 UPI payments in 90 seconds (normal batch) no longer triggers.
            8 transactions in 10 minutes does.
        """
        flag = "RAPID_TRANSACTION"

        if not _has_time(self.df):
            logger.info(
                "RAPID_TRANSACTION: 'time' absent/empty — skipped as instructed."
            )
            return

        # Build full timestamps: date + time combined
        def _combine(row: pd.Series) -> pd.Timestamp | None:
            d = row.get("date")
            t = _safe_str(row.get("time"))
            if pd.isna(d) or not t:
                return None
            try:
                return pd.to_datetime(f"{d.date()} {t}")
            except Exception:
                return None

        timestamps = self.df.apply(_combine, axis=1)
        work = pd.DataFrame({"ts": timestamps}, index=self.df.index).dropna()

        if len(work) < RAPID_BURST_THRESHOLD:
            return

        work     = work.sort_values("ts")
        ts_list  = work["ts"].tolist()
        idx_list = work.index.tolist()
        window   = pd.Timedelta(minutes=RAPID_WINDOW_MINUTES)

        for i, (ts_i, idx_i) in enumerate(zip(ts_list, idx_list)):
            # Count all transactions within ±window/2 of ts_i
            # (symmetric so the window doesn't bias toward future transactions)
            count_in_window = sum(
                1 for ts_j in ts_list
                if abs((ts_i - ts_j).total_seconds()) <= window.total_seconds() / 2
            )
            if count_in_window >= RAPID_BURST_THRESHOLD:
                self._flag(
                    idx_i, flag,
                    f"{count_in_window} transactions within "
                    f"{RAPID_WINDOW_MINUTES}-minute window "
                    f"(threshold: {RAPID_BURST_THRESHOLD})",
                )

    # -----------------------------------------------------------------------
    # Rule 6 — Late Night Transaction (NEW)
    # -----------------------------------------------------------------------

    def detect_late_night_transactions(self) -> None:
        """
        Flag significant transactions occurring during night hours
        [LATE_NIGHT_START_HOUR, 24) ∪ [0, LATE_NIGHT_END_HOUR).

        Skipped when 'time' is absent or fully null — consistent with
        RAPID_TRANSACTION behaviour.

        Why:
            Fraudulent card/UPI usage peaks in late-night hours when the
            account holder is unlikely to be awake to notice.
        """
        flag = "LATE_NIGHT_TRANSACTION"

        if not _has_time(self.df):
            logger.info(
                "LATE_NIGHT_TRANSACTION: 'time' absent/empty — skipped."
            )
            return

        for idx in self.df.index:
            amt = self._amounts.get(idx)
            if pd.isna(amt) or amt < LATE_NIGHT_MIN_AMOUNT:
                continue

            t_raw = _safe_str(self.df.loc[idx].get("time", ""))
            if not t_raw:
                continue

            # Parse hour out of HH:MM:SS
            try:
                hour = int(t_raw.split(":")[0])
            except (ValueError, IndexError):
                continue

            is_night = (hour >= LATE_NIGHT_START_HOUR) or (hour < LATE_NIGHT_END_HOUR)
            if is_night:
                self._flag(
                    idx, flag,
                    f"Transaction of {amt:,.2f} at {t_raw} falls in "
                    f"late-night window "
                    f"({LATE_NIGHT_START_HOUR}:00–{LATE_NIGHT_END_HOUR}:00), "
                    f"min amount {LATE_NIGHT_MIN_AMOUNT:,.0f}",
                )

    # -----------------------------------------------------------------------
    # Rule 7 — Balance Drop Alert (NEW)
    # -----------------------------------------------------------------------

    def detect_balance_drop(self) -> None:
        """
        Flag a transaction if it drains more than BALANCE_DROP_PCT_THRESHOLD
        of the day's opening balance in a single hit.

        Opening balance per day = balance value on the FIRST transaction of
        that calendar day (chronological order within the day).

        Why:
            Catches large one-shot account drains that HIGH_VALUE misses
            when the account normally handles big transactions (so the 5×
            median floor is never breached).
        """
        flag = "BALANCE_DROP_ALERT"

        if self._balances.isna().all():
            logger.debug("BALANCE_DROP: no balance data — skipped.")
            return

        work = pd.DataFrame({
            "balance": self._balances,
            "amount":  self._amounts,
            "date":    self._dates.dt.normalize(),
            "ts":      self._dates,          # for within-day ordering
        }, index=self.df.index).dropna(subset=["date", "balance"])

        if work.empty:
            return

        # Opening balance = balance on the first (earliest) transaction each day.
        # If timestamps are identical, we take the minimum balance as a
        # conservative proxy for "before any transaction ran".
        opening_balance: dict[Any, float] = (
            work.sort_values("ts")
                .groupby("date")["balance"]
                .first()
                .to_dict()
        )

        for idx in work.index:
            amt     = work.loc[idx, "amount"]
            day     = work.loc[idx, "date"]
            opening = opening_balance.get(day)

            if pd.isna(amt) or opening is None or opening <= 0:
                continue

            # Balance AFTER this transaction = opening - amount (for debits).
            # We approximate the drop as amount / opening_balance.
            drop_pct = amt / opening
            if drop_pct > BALANCE_DROP_PCT_THRESHOLD:
                self._flag(
                    idx, flag,
                    f"Transaction of {amt:,.2f} is {drop_pct*100:.1f}% of "
                    f"opening balance {opening:,.2f} on {day.date()} "
                    f"(threshold: {BALANCE_DROP_PCT_THRESHOLD*100:.0f}%)",
                )

    # -----------------------------------------------------------------------
    # Risk level assignment
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
        Build the summary block of the output dict.
        """
        flagged  = [e for e in self._risk.values() if e["score"] > 0]
        scores   = [e["score"] for e in flagged]

        return {
            "total_transactions":           self.n_rows,
            "flagged_transactions":         len(flagged),
            "high_value_count":             self._counts["HIGH_VALUE_TRANSACTION"],
            "spending_spike_count":         self._counts["SPENDING_SPIKE"],
            "repeated_transaction_count":   self._counts["REPEATED_TRANSACTION"],
            "excessive_withdrawal_count":   self._counts["EXCESSIVE_WITHDRAWAL"],
            "rapid_transaction_count":      self._counts["RAPID_TRANSACTION"],
            "late_night_count":             self._counts["LATE_NIGHT_TRANSACTION"],
            "balance_drop_count":           self._counts["BALANCE_DROP_ALERT"],
            "average_flagged_risk_score":   round(sum(scores)/len(scores), 2) if scores else 0.0,
            "max_risk_score":               max(scores) if scores else 0,
        }

    # -----------------------------------------------------------------------
    # Main orchestrator
    # -----------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """
        Execute all detection rules in order and return the complete report.

        Returns
        -------
        dict:
            {
                "summary":              { ... },
                "flagged_transactions": [ ... ]   # risk_score > 0 only,
                                                  # sorted highest score first
            }
        """
        if self.df.empty:
            logger.warning("RiskEngine: empty DataFrame — returning zero report.")
            return {
                "summary": {k: 0 for k in [
                    "total_transactions","flagged_transactions",
                    "high_value_count","spending_spike_count",
                    "repeated_transaction_count","excessive_withdrawal_count",
                    "rapid_transaction_count","late_night_count",
                    "balance_drop_count","average_flagged_risk_score","max_risk_score",
                ]},
                "flagged_transactions": [],
            }

        logger.info("RiskEngine starting — %d transactions.", self.n_rows)

        self.detect_high_value_transactions()
        self.detect_spending_spikes()
        self.detect_repeated_transactions()
        self.detect_excessive_withdrawals()
        self.detect_rapid_transactions()
        self.detect_late_night_transactions()
        self.detect_balance_drop()

        self.calculate_risk_levels()

        # ── Assemble flagged_transactions list ───────────────────────────
        flagged: list[dict] = []
        for idx, entry in self._risk.items():
            if entry["score"] <= 0:
                continue

            row      = self.df.loc[idx]
            date_val = self._dates.get(idx)

            flagged.append({
                "transaction_index": int(idx) if isinstance(idx, (int, float)) else str(idx),
                "date":              date_val.strftime("%Y-%m-%d") if pd.notna(date_val) else None,
                "time":              _safe_str(row.get("time"))              or None,
                "merchant":          _safe_str(row.get("merchant"))          or None,
                "narration":         _safe_str(row.get("narration"))         or None,
                "mode":              _safe_str(row.get("mode"))              or None,
                "channel":           self._channels.get(idx, "UNKNOWN"),
                "amount":            float(self._amounts[idx])
                                     if pd.notna(self._amounts.get(idx)) else None,
                "debit_credit":      _safe_str(row.get("debit_credit"))      or None,
                "transaction_type":  _safe_str(row.get("transaction_type"))  or None,
                "risk_score":        entry["score"],
                "risk_level":        entry["risk_level"],
                "flags":             entry["flags"],
                "reasons":           entry["reasons"],
            })

        flagged.sort(key=lambda r: r["risk_score"], reverse=True)

        summary = self.generate_summary()
        logger.info(
            "RiskEngine done — %d/%d flagged  max=%d  avg=%.1f",
            summary["flagged_transactions"], self.n_rows,
            summary["max_risk_score"], summary["average_flagged_risk_score"],
        )

        return {"summary": summary, "flagged_transactions": flagged}


# ===========================================================================
# ── app.py INTERFACE ─────────────────────────────────────────────────────────
# ===========================================================================

def run(df: pd.DataFrame, report: dict) -> dict:
    """
    Entry point called by app.py's step_optional_services().
    Also saves a dedicated risk_report.json for standalone inspection.

    Parameters
    ----------
    df     : standardized transaction DataFrame
    report : analytics report dict (read-only here)

    Returns
    -------
    dict merged into report["risk"] by app.py
    """
    import json
    from pathlib import Path

    engine = RiskEngine(df)
    result = engine.run()

    output_path = Path("risk_report.json")
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    logger.info("Risk report saved → %s", output_path.resolve())

    return result
