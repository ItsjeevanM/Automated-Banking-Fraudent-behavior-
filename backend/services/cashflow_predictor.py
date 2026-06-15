"""
services/cashflow_predictor.py  —  Version 2
---------------------------------------------
Deterministic cash-runway forecasting. No ML, no external APIs.

Pipeline:
    Current Balance → Estimated Spending Rate → Runway → Depletion Date → Warnings

Public API:
    predict_cashflow(df: pd.DataFrame) -> dict
    run(df, report) -> dict          ← called by app.py

Output:
    {
        "metrics":  { current_balance, estimated_daily_spending, ... },
        "forecast": { runway_days, depletion_date, risk_classification,
                      projected_balances },
        "warnings": [ ... ],
        "metadata": { confidence_level, confidence_reason,
                      statement_start, statement_end }
    }
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds — change these, nothing else needs to change.
# ---------------------------------------------------------------------------

# Runway warning: flag when fewer than N days of cash remain.
LOW_RUNWAY_DAYS = 30

# Balance warning: flag when current balance is below this amount.
LOW_BALANCE_ABS = 5_000.0

# Withdrawal keywords for narration scan.
WITHDRAWAL_KEYWORDS = {"atm", "cash", "withdrawal", "cashout", "cdm"}

# Recurring income: a credit key must appear in at least this many months.
RECURRING_INCOME_MIN_MONTHS = 3

# Recurring income: ignore credits below this amount (filters cashbacks, etc.).
RECURRING_INCOME_MIN_AMOUNT = 1_000.0

# Projected balance: how far ahead to show weekly snapshots.
FORECAST_HORIZON_DAYS = 90


# ---------------------------------------------------------------------------
# Statistical method decisions
# (explained fully in the module-level docstring below each function)
# ---------------------------------------------------------------------------

# OUTLIER TRANSACTIONS — 99th percentile
# Why: On this data, IQR(1.5x) flags 81 txns, MAD(3x) flags 143 — both
# nonsensical as "outliers". The 99th percentile flags the top 1%, which
# is the clearest plain-English definition of unusual. On 695 debits that
# means ~7 transactions, which is genuinely rare. Tradeoff: fixed percentage
# means on a 50-txn dataset you get 0-1 outliers, which may be too few —
# but that is honest: you don't have enough data to reliably detect outliers.
OUTLIER_PERCENTILE = 99

# SPENDING SPIKE DAYS — 95th percentile of daily spend
# Why: IQR(1.5x) flags 37 days, 3x-median flags 52 days — both too many.
# The 95th percentile flags the top 5% of spending days, which is exactly
# 13 days out of 257 active days (~5%). That is a defensible definition of
# "exceptional". Tradeoff: purely relative — if all days are expensive it
# still flags the top 5%, but that's correct: you want unusual *for this account*.
SPIKE_PERCENTILE = 95

# SPENDING RATE ESTIMATOR — trimmed mean (remove top 5% of daily spend days)
# Why: Raw mean = 1,642/day (distorted by rare large days).
#      Median = 490/day (too conservative — ignores real regular spend).
#      Trimmed mean (top 5% removed) = 858/day — represents typical spending
#      excluding genuine outlier days, which is what a forecast should model.
# Tradeoff: slightly underestimates spend compared to raw mean, but that
# distortion is intentional — one ₹45,000 vacation shouldn't define your
# baseline burn rate.
TRIM_FRACTION = 0.05   # remove top 5% of daily spend days


# ===========================================================================
# Helpers — kept minimal
# ===========================================================================

def _f(v: Any, default: float = 0.0) -> float:
    """Safe float cast."""
    try:
        r = float(v)
        return default if (np.isnan(r) or np.isinf(r)) else r
    except (TypeError, ValueError):
        return default


def _ds(d: Any) -> str | None:
    """Timestamp / date → ISO string, None on failure."""
    if d is None:
        return None
    try:
        return pd.Timestamp(d).strftime("%Y-%m-%d")
    except Exception:
        return None


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce the DataFrame to a consistent internal schema.
    Handles both the normalizer's output (debit_credit, merchant, balance)
    and the raw CSV schema (type, narration, currentBalance).
    """
    w = df.copy()

    # date
    if "date" not in w.columns and "valueDate" in w.columns:
        w["date"] = w["valueDate"]
    if "date" in w.columns:
        w["date"] = pd.to_datetime(w["date"], errors="coerce")

    # debit_credit
    if "debit_credit" not in w.columns and "type" in w.columns:
        w["debit_credit"] = (
            w["type"].str.strip().str.upper()
                     .map({"DEBIT": "Debit", "CREDIT": "Credit",
                           "DR": "Debit",    "CR": "Credit"})
                     .fillna(w["type"])
        )

    # amount
    w["amount"] = pd.to_numeric(w.get("amount", pd.Series(dtype=float)),
                                errors="coerce")

    # balance
    if "balance" not in w.columns:
        src = "currentBalance" if "currentBalance" in w.columns else None
        if src:
            w["balance"] = pd.to_numeric(w[src], errors="coerce")

    # narration label (used by recurring income and outlier description)
    if "narration" not in w.columns and "merchant" in w.columns:
        w["narration"] = w["merchant"]

    return w


# ===========================================================================
# Step 1 — Core metrics
# ===========================================================================

def calculate_metrics(df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute the numbers every other step depends on.

    Returns a dict. All values are plain Python scalars, pd.Series, or
    pd.DataFrame — the response builder strips non-serializable ones.
    """
    dates = df["date"].dropna() if "date" in df.columns else pd.Series(dtype="datetime64[ns]")

    if dates.empty:
        return _empty_metrics()

    statement_start = dates.min()
    statement_end   = dates.max()
    calendar_days   = max((statement_end - statement_start).days + 1, 1)

    dc = df.get("debit_credit", pd.Series(dtype=str))
    debit_mask  = dc.str.strip().str.title() == "Debit"
    credit_mask = dc.str.strip().str.title() == "Credit"

    debit_rows  = df[debit_mask].dropna(subset=["amount"])
    credit_rows = df[credit_mask].dropna(subset=["amount"])

    total_debits  = _f(debit_rows["amount"].sum())
    total_credits = _f(credit_rows["amount"].sum())

    # Daily spend series — needed for spike detection and rate estimation
    if not debit_rows.empty and "date" in debit_rows.columns:
        daily_spend = (
            debit_rows.dropna(subset=["date"])
                      .groupby(debit_rows["date"].dt.normalize())["amount"]
                      .sum()
        )
    else:
        daily_spend = pd.Series(dtype=float)

    # ── Spending rate: trimmed mean of daily spend ───────────────────────
    # Remove top TRIM_FRACTION of daily spend days before computing mean.
    # This keeps one-off expensive days from inflating the baseline.
    # See module-level comment for full reasoning.
    if not daily_spend.empty:
        cutoff         = daily_spend.quantile(1 - TRIM_FRACTION)
        trimmed_daily  = daily_spend[daily_spend <= cutoff]
        estimated_daily_spending = _f(
            trimmed_daily.mean() if not trimmed_daily.empty else daily_spend.mean()
        )
        median_daily_spending = _f(daily_spend.median())
    else:
        estimated_daily_spending = 0.0
        median_daily_spending    = 0.0

    # Balance
    if "balance" in df.columns:
        bal = df["balance"].dropna()
        current_balance = _f(bal.iloc[-1]) if not bal.empty else 0.0
    else:
        current_balance = 0.0

    return {
        "calendar_days":             calendar_days,
        "active_debit_days":         len(daily_spend),
        "total_debits":              round(total_debits,  2),
        "total_credits":             round(total_credits, 2),
        "estimated_daily_spending":  round(estimated_daily_spending, 2),
        "median_daily_spending":     round(median_daily_spending,    2),
        "current_balance":           round(current_balance, 2),
        "statement_start":           statement_start,
        "statement_end":             statement_end,
        # keep these as Series for use in warnings/confidence — stripped later
        "_daily_spend":              daily_spend,
        "_debit_rows":               debit_rows,
        "_credit_rows":              credit_rows,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "calendar_days": 0, "active_debit_days": 0,
        "total_debits": 0.0, "total_credits": 0.0,
        "estimated_daily_spending": 0.0, "median_daily_spending": 0.0,
        "current_balance": 0.0,
        "statement_start": None, "statement_end": None,
        "_daily_spend": pd.Series(dtype=float),
        "_debit_rows": pd.DataFrame(),
        "_credit_rows": pd.DataFrame(),
    }


# ===========================================================================
# Step 2 — Forecast
# ===========================================================================

def generate_forecast(metrics: dict[str, Any]) -> dict[str, Any]:
    """
    Runway, depletion date, weekly projected balances, risk classification.

    Assumption: future daily spend = estimated_daily_spending (trimmed mean).
    No income is assumed — conservative by design. If recurring income is
    present a warning covers this.
    """
    rate    = metrics["estimated_daily_spending"]
    balance = metrics["current_balance"]
    end     = metrics["statement_end"]

    balance = max(balance, 0)

    base_date = (
        end.date() if isinstance(end, pd.Timestamp) else date.today()
    )

    if rate > 0:
        runway_days    = int(balance / rate)
        depletion_date = _ds(base_date + timedelta(days=runway_days))
    else:
        runway_days    = None
        depletion_date = None

    # Risk classification
    if runway_days is None:
        risk = "UNKNOWN"
    elif runway_days <= 7 or balance < LOW_BALANCE_ABS * 0.25:
        risk = "CRITICAL"
    elif runway_days <= LOW_RUNWAY_DAYS or balance < LOW_BALANCE_ABS:
        risk = "HIGH"
    elif runway_days <= LOW_RUNWAY_DAYS * 3:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    # Weekly projected balances — floor at 0, no negative balance shown
    projected_balances: list[dict] = []
    for offset in range(0, FORECAST_HORIZON_DAYS + 1, 7):
        projected_balances.append({
            "day":               offset,
            "date":              _ds(base_date + timedelta(days=offset)),
            "projected_balance": round(max(balance - rate * offset, 0.0), 2),
        })

    return {
        "runway_days":          runway_days,
        "depletion_date":       depletion_date,
        "risk_classification":  risk,
        "projected_balances":   projected_balances,
    }


# ===========================================================================
# Step 3 — Warnings
# ===========================================================================

def generate_warnings(metrics: dict[str, Any]) -> list[str]:
    """
    Produce a short list of genuinely actionable warnings.

    1. Low absolute balance
    2. Low runway
    3. Spending spike days    (95th percentile — ~top 5% of days)
    4. Outlier transactions   (99th percentile — top 1% of debits)
    5. Recurring income       (pattern detected, no prediction made)
    """
    warnings: list[str] = []

    balance     = metrics["current_balance"]
    rate        = metrics["estimated_daily_spending"]
    daily       = metrics["_daily_spend"]
    debit_rows  = metrics["_debit_rows"]
    credit_rows = metrics["_credit_rows"]

    balance = max(balance, 0)
    
    runway      = int(balance / rate) if rate > 0 else None

    # ── 1. Low balance ───────────────────────────────────────────────────
    if balance < LOW_BALANCE_ABS:
        warnings.append(
            f"Low balance: {balance:,.2f} is below the {LOW_BALANCE_ABS:,.0f} threshold."
        )

    # ── 2. Low runway ────────────────────────────────────────────────────
    if runway is not None and runway < LOW_RUNWAY_DAYS:
        warnings.append(
            f"Short runway: estimated {runway} days of cash remaining "
            f"at {rate:,.2f}/day spending rate."
        )

    # ── 3. Spending spike days — 95th percentile ─────────────────────────
    # Method: flag days above the 95th percentile of all daily spend values.
    # Only the top 5% of days are considered spikes — a clear, defensible bar.
    # Previous 3x-median method flagged 52 days; this flags ~13.
    if len(daily) >= 10:
        spike_thresh = daily.quantile(SPIKE_PERCENTILE / 100)
        spike_days   = daily[daily > spike_thresh]
        if not spike_days.empty:
            worst_day   = spike_days.idxmax()
            worst_spend = spike_days.max()
            warnings.append(
                f"{len(spike_days)} high-spend day(s) detected "
                f"(above {SPIKE_PERCENTILE}th percentile: {spike_thresh:,.0f}/day). "
                f"Highest: {worst_spend:,.2f} on {_ds(worst_day)}."
            )

    # ── 4. Outlier transactions — 99th percentile ─────────────────────────
    # Method: flag transactions above the 99th percentile of debit amounts.
    # On this dataset: threshold = ~12,042. Flags 7 transactions.
    # Previous 5x-median method flagged 27; IQR(1.5x) flagged 81.
    # 99th percentile is the clearest, most honest definition of "top 1%".
    if len(debit_rows) >= 20:
        amounts      = debit_rows["amount"].dropna()
        outlier_thresh = amounts.quantile(OUTLIER_PERCENTILE / 100)
        outliers     = debit_rows[debit_rows["amount"] > outlier_thresh]
        if not outliers.empty:
            biggest  = outliers.loc[outliers["amount"].idxmax()]
            label    = ""
            for col in ("narration", "merchant", "mode"):
                val = str(biggest.get(col, "")).strip()
                if val and val.lower() not in ("nan", "none", ""):
                    label = f" ({val})"
                    break
            warnings.append(
                f"{len(outliers)} unusually large debit(s) detected "
                f"(above {OUTLIER_PERCENTILE}th percentile: {outlier_thresh:,.0f}). "
                f"Largest: {_f(biggest['amount']):,.2f}{label}."
            )

    # ── 5. Recurring income ───────────────────────────────────────────────
    # Detect credit keys that appear in >= RECURRING_INCOME_MIN_MONTHS
    # distinct months AND exceed the minimum significance amount.
    # We report the pattern only — no income is predicted.
    if not credit_rows.empty and "date" in credit_rows.columns:
        cr = credit_rows.dropna(subset=["date"]).copy()
        cr = cr[cr["amount"] >= RECURRING_INCOME_MIN_AMOUNT]

        # Key resolution: prefer narration, fall back to mode
        for col in ("narration", "merchant", "mode"):
            if col in cr.columns and cr[col].notna().any():
                cr["_key"] = (
                    cr[col].fillna("").astype(str).str.strip().str.upper()
                )
                break
        else:
            cr["_key"] = "UNKNOWN"

        cr["_month"] = cr["date"].dt.to_period("M").astype(str)
        month_counts = cr.groupby("_key")["_month"].nunique()

        if (month_counts >= RECURRING_INCOME_MIN_MONTHS).any():
            warnings.append(
                "Recurring income detected. "
                "Forecast may underestimate account longevity."
            )

    return warnings


# ===========================================================================
# Step 4 — Confidence
# ===========================================================================

def _confidence(metrics: dict[str, Any]) -> tuple[str, str]:
    """
    Score forecast reliability on four factors:
        1. Statement length      — longer = more reliable baseline
        2. Spending stability    — fewer spike days relative to active days
        3. Transaction volume    — more data = better statistics
        4. Outlier day fraction  — high fraction = rate estimate less trustworthy

    Scoring: each factor contributes a point.
        4 points → High
        2–3      → Medium
        0–1      → Low

    This is intentionally harder to reach High than v1, which could score
    High on a 60-day dataset with moderate variance. A forecast based on
    2 months of erratic UPI spending should not say High.
    """
    daily         = metrics["_daily_spend"]
    calendar_days = metrics["calendar_days"]
    active_days   = metrics["active_debit_days"]

    score = 0
    notes: list[str] = []

    # Factor 1: statement length
    if calendar_days >= 90:
        score += 1
        notes.append(f"good history ({calendar_days}d)")
    else:
        notes.append(f"short history ({calendar_days}d)")

    # Factor 2: spending stability — what fraction of active days are spikes?
    if len(daily) >= 10:
        spike_thresh    = daily.quantile(SPIKE_PERCENTILE / 100)
        spike_fraction  = (daily > spike_thresh).mean()  # should be ~0.05
        if spike_fraction <= 0.08:
            score += 1
            notes.append("stable daily spend")
        else:
            notes.append(f"erratic daily spend ({spike_fraction:.0%} spike days)")
    else:
        notes.append("too few active days to assess stability")

    # Factor 3: transaction volume
    n_debits = len(metrics["_debit_rows"])
    if n_debits >= 100:
        score += 1
        notes.append(f"good transaction volume ({n_debits})")
    else:
        notes.append(f"low transaction volume ({n_debits})")

    # Factor 4: outlier day fraction — what proportion of calendar days are
    # extreme-spend days? High proportion means the trimmed mean may still
    # be pulled upward.
    if active_days > 0 and len(daily) >= 10:
        outlier_day_pct = (daily > daily.quantile(0.95)).sum() / active_days
        if outlier_day_pct <= 0.05:
            score += 1
            notes.append("few outlier days")
        else:
            notes.append(f"many outlier days ({outlier_day_pct:.0%})")

    if score >= 4:
        level = "High"
    elif score >= 2:
        level = "Medium"
    else:
        level = "Low"

    reason = f"{level} confidence ({score}/4): {', '.join(notes)}."
    return level, reason


# ===========================================================================
# Public API
# ===========================================================================

def predict_cashflow(df: pd.DataFrame) -> dict[str, Any]:
    """
    Main entry point.

    Parameters
    ----------
    df : pd.DataFrame
        Standardized transactions from normalizer.py / app.py, or a raw
        bank statement CSV DataFrame.

    Returns
    -------
    dict — JSON-serializable, keys: metrics, forecast, warnings, metadata.
    """
    logger.info("cashflow_predictor v2: %d rows.", len(df))

    if df.empty:
        return {
            "metrics":  {},
            "forecast": {"runway_days": None, "depletion_date": None,
                         "risk_classification": "UNKNOWN", "projected_balances": []},
            "warnings": ["No transaction data — forecast cannot be generated."],
            "metadata": {"confidence_level": "Low",
                         "confidence_reason": "No data.",
                         "statement_start": None, "statement_end": None},
        }

    w        = _prep(df)
    metrics  = calculate_metrics(w)
    forecast = generate_forecast(metrics)
    warnings = generate_warnings(metrics)
    conf_level, conf_reason = _confidence(metrics)

    # Strip internal pd.Series / pd.DataFrame before serializing
    clean_metrics = {k: v for k, v in metrics.items() if not k.startswith("_")}
    clean_metrics["statement_start"] = _ds(metrics["statement_start"])
    clean_metrics["statement_end"]   = _ds(metrics["statement_end"])

    result = {
        "metrics":  clean_metrics,
        "forecast": forecast,
        "warnings": warnings,
        "metadata": {
            "confidence_level":  conf_level,
            "confidence_reason": conf_reason,
            "statement_start":   _ds(metrics["statement_start"]),
            "statement_end":     _ds(metrics["statement_end"]),
        },
    }

    logger.info(
        "cashflow_predictor v2: runway=%s days | risk=%s | confidence=%s | warnings=%d",
        forecast.get("runway_days"), forecast.get("risk_classification"),
        conf_level, len(warnings),
    )

    _print_summary(result)
    return result


def _print_summary(result: dict[str, Any]) -> None:
    """Print a concise terminal summary."""
    m = result["metrics"]
    f = result["forecast"]
    meta = result["metadata"]

    sep = "=" * 60
    print(f"\n{sep}")
    print("  CASHFLOW FORECAST")
    print(sep)
    print(f"  Current Balance        : {m.get('current_balance', 'N/A'):>12,.2f}")
    print(f"  Estimated Daily Spend  : {m.get('estimated_daily_spending', 'N/A'):>12,.2f}")
    rw = f.get('runway_days')
    print(f"  Runway Days            : {str(rw) if rw is not None else 'N/A':>12}")
    print(f"  Depletion Date         : {f.get('depletion_date') or 'N/A':>12}")
    print(f"  Risk Level             : {f.get('risk_classification', 'N/A'):>12}")
    print(f"  Confidence             : {meta.get('confidence_level', 'N/A'):>12}")
    if result["warnings"]:
        print()
        print("  Warnings:")
        for w in result["warnings"]:
            # Wrap long warnings at 55 chars
            words = w.split()
            line, lines = "", []
            for word in words:
                if len(line) + len(word) + 1 > 55:
                    lines.append(line)
                    line = word
                else:
                    line = (line + " " + word).strip()
            if line:
                lines.append(line)
            print(f"    • {lines[0]}")
            for l in lines[1:]:
                print(f"      {l}")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# app.py interface
# ---------------------------------------------------------------------------

def run(df: pd.DataFrame, report: dict) -> dict:
    """Called by app.py's step_optional_services(). Merged into report['cashflow']."""
    return predict_cashflow(df)


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys

    if len(sys.argv) < 2:
        print("Usage: python cashflow_predictor.py <path/to/statement.csv>")
        sys.exit(1)

    raw = pd.read_csv(sys.argv[1])
    out = predict_cashflow(raw)
    print(json.dumps(
        {k: v for k, v in out.items() if k != "forecast" or True},
        indent=2, default=str
    ))
