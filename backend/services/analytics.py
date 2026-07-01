"""
services/analytics.py
---------------------
Pure analytics service for the Bank Statement Analysis Platform.

Input  : Pandas DataFrame produced by app.py (sourced from normalizer.py).
Output : JSON-serializable dicts consumed by app.py, fraud.py,
         risk_engine.py, llm_summary.py, and report_generator.py.

Public API
----------
    validate_schema(df)                 → dict
    total_debit(df)                     → float
    total_credit(df)                    → float
    transaction_count(df)               → int
    average_transaction(df)             → float | None
    median_transaction(df)              → float | None
    summary_statistics(df)              → dict
    daily_transaction_volume(df)        → list[dict]
    monthly_transaction_trends(df)      → list[dict]
    debit_credit_analysis(df)           → dict
    merchant_analysis(df)               → dict
    top_merchants(df, top_n=10)         → list[dict]
    transaction_type_distribution(df)   → list[dict]
    spending_trends(df)                 → dict
    generate_chart_data(df)             → dict   (Recharts-ready)
    generate_analytics_report(df)       → dict   (master report)

Design principles
-----------------
- Every function is independently callable (no hidden shared state).
- All outputs are JSON-serialisable (float, int, str, list, dict, None).
- NaN / NaT / None are handled safely; no function raises on missing data.
- numpy scalars are cast to Python natives so json.dumps() never throws.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Expected schema — used by validate_schema() and internal guards.
# ---------------------------------------------------------------------------
EXPECTED_COLUMNS: set[str] = {
    "date", "time", "debit_credit", "amount",
    "balance", "transaction_type", "merchant",
}


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================

def _safe_float(value: Any) -> float | None:
    """Cast a numpy/pandas scalar to a plain Python float; None if NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        result = float(value)
        return None if np.isnan(result) or np.isinf(result) else result
    except (TypeError, ValueError):
        return None


def _debit_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask for rows where debit_credit == 'Debit'."""
    if "debit_credit" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["debit_credit"].str.strip().str.title() == "Debit"


def _credit_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask for rows where debit_credit == 'Credit'."""
    if "debit_credit" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["debit_credit"].str.strip().str.title() == "Credit"


def _amount_series(df: pd.DataFrame) -> pd.Series:
    """Return the 'amount' column as numeric; empty Series if absent."""
    if "amount" not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df["amount"], errors="coerce")


def _ensure_date(df: pd.DataFrame) -> pd.Series:
    """Return 'date' column as datetime64; NaT where unparseable."""
    if "date" not in df.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(df["date"], errors="coerce")


# ===========================================================================
# SCHEMA VALIDATION
# ===========================================================================

def validate_schema(df: pd.DataFrame) -> dict[str, Any]:
    """
    Check that the DataFrame conforms to the expected standardized schema.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    dict with keys:
        valid          (bool)
        missing_cols   (list[str])
        extra_cols     (list[str])
        row_count      (int)
        null_summary   (dict[col → null_count])
    """
    present      = set(df.columns)
    missing_cols = sorted(EXPECTED_COLUMNS - present)
    extra_cols   = sorted(present - EXPECTED_COLUMNS)

    null_summary: dict[str, int] = {
        col: int(df[col].isna().sum())
        for col in EXPECTED_COLUMNS
        if col in df.columns
    }

    return {
        "valid":        len(missing_cols) == 0,
        "missing_cols": missing_cols,
        "extra_cols":   extra_cols,
        "row_count":    len(df),
        "null_summary": null_summary,
    }


# ===========================================================================
# SCALAR METRICS
# ===========================================================================

def total_debit(df: pd.DataFrame) -> float:
    """
    Sum of all debit transaction amounts.

    Returns 0.0 for empty DataFrames or when the column is absent.
    """
    if df.empty:
        return 0.0
    amounts = _amount_series(df)
    mask    = _debit_mask(df)
    result  = amounts[mask].sum()
    return round(float(result), 2)


def total_credit(df: pd.DataFrame) -> float:
    """
    Sum of all credit transaction amounts.

    Returns 0.0 for empty DataFrames or when the column is absent.
    """
    if df.empty:
        return 0.0
    amounts = _amount_series(df)
    mask    = _credit_mask(df)
    result  = amounts[mask].sum()
    return round(float(result), 2)


def transaction_count(df: pd.DataFrame) -> int:
    """Total number of transaction rows."""
    return len(df)


def average_transaction(df: pd.DataFrame) -> float | None:
    """Mean amount across all transactions. None if no valid amounts exist."""
    if df.empty:
        return None
    amounts = _amount_series(df).dropna()
    if amounts.empty:
        return None
    return round(float(amounts.mean()), 2)


def median_transaction(df: pd.DataFrame) -> float | None:
    """Median amount across all transactions. None if no valid amounts exist."""
    if df.empty:
        return None
    amounts = _amount_series(df).dropna()
    if amounts.empty:
        return None
    return round(float(amounts.median()), 2)


# ===========================================================================
# SUMMARY STATISTICS
# ===========================================================================

def summary_statistics(df: pd.DataFrame) -> dict[str, Any]:
    """
    Descriptive statistics for the amount column plus debit/credit totals.

    Returns
    -------
    dict with keys:
        transaction_count, total_debit, total_credit, net_cash_flow,
        average_transaction, median_transaction,
        largest_debit, largest_credit,
        std_dev, min_amount, max_amount,
        closing_balance, average_daily_spending
    """
    if df.empty:
        return {
            "transaction_count":    0,
            "total_debit":          0.0,
            "total_credit":         0.0,
            "net_cash_flow":        0.0,
            "average_transaction":  None,
            "median_transaction":   None,
            "largest_debit":        None,
            "largest_credit":       None,
            "std_dev":              None,
            "min_amount":           None,
            "max_amount":           None,
            "closing_balance":      None,
            "average_daily_spending": None,
        }

    amounts = _amount_series(df)
    td      = total_debit(df)
    tc      = total_credit(df)

    # Largest single transactions
    debit_amounts  = amounts[_debit_mask(df)].dropna()
    credit_amounts = amounts[_credit_mask(df)].dropna()
    largest_debit  = _safe_float(debit_amounts.max())  if not debit_amounts.empty  else None
    largest_credit = _safe_float(credit_amounts.max()) if not credit_amounts.empty else None

    # Closing balance = last non-null balance row
    closing_balance: float | None = None
    if "balance" in df.columns:
        bal_series = pd.to_numeric(df["balance"], errors="coerce").dropna()
        if not bal_series.empty:
            closing_balance = round(float(bal_series.iloc[-1]), 2)

    # Average daily spending (debits only, spread over active days)
    avg_daily: float | None = None
    dates = _ensure_date(df).dropna()
    if not dates.empty:
        active_days = max((dates.max() - dates.min()).days, 1)
        avg_daily   = round(td / active_days, 2)

    return {
        "transaction_count":      len(df),
        "total_debit":            td,
        "total_credit":           tc,
        "net_cash_flow":          round(tc - td, 2),
        "average_transaction":    average_transaction(df),
        "median_transaction":     median_transaction(df),
        "largest_debit":          largest_debit,
        "largest_credit":         largest_credit,
        "std_dev":                _safe_float(amounts.dropna().std()),
        "min_amount":             _safe_float(amounts.dropna().min()),
        "max_amount":             _safe_float(amounts.dropna().max()),
        "closing_balance":        closing_balance,
        "average_daily_spending": avg_daily,
    }


# ===========================================================================
# TIME-SERIES BREAKDOWNS
# ===========================================================================

def daily_transaction_volume(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Aggregate total amount and count per calendar day.

    Returns
    -------
    list[dict] sorted by date ascending, each dict:
        { "date": "YYYY-MM-DD", "total_amount": float, "count": int }
    """
    if df.empty or "amount" not in df.columns:
        return []

    work = df.copy()
    work["_date"]   = _ensure_date(work)
    work["_amount"] = _amount_series(work)
    work = work.dropna(subset=["_date"])

    if work.empty:
        return []

    grouped = (
        work.groupby("_date")
        .agg(total_amount=("_amount", "sum"), count=("_amount", "count"))
        .reset_index()
        .sort_values("_date")
    )

    return [
        {
            "date":         row["_date"].strftime("%Y-%m-%d"),
            "total_amount": round(float(row["total_amount"]), 2),
            "count":        int(row["count"]),
        }
        for _, row in grouped.iterrows()
    ]


def monthly_transaction_trends(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Aggregate debit, credit, and net per calendar month.

    Returns
    -------
    list[dict] sorted by month ascending, each dict:
        { "month": "YYYY-MM", "total_debit": float,
          "total_credit": float, "net": float, "count": int }
    """
    if df.empty or "amount" not in df.columns:
        return []

    work = df.copy()
    work["_date"]   = _ensure_date(work)
    work["_amount"] = _amount_series(work)
    work = work.dropna(subset=["_date"])

    if work.empty:
        return []

    work["_month"] = work["_date"].dt.to_period("M")

    results: list[dict] = []
    for period, grp in work.groupby("_month"):
        debit_sum  = float(grp.loc[_debit_mask(grp),  "_amount"].sum())
        credit_sum = float(grp.loc[_credit_mask(grp), "_amount"].sum())
        results.append({
            "month":        str(period),
            "total_debit":  round(debit_sum,  2),
            "total_credit": round(credit_sum, 2),
            "net":          round(credit_sum - debit_sum, 2),
            "count":        len(grp),
        })

    return sorted(results, key=lambda r: r["month"])


# ===========================================================================
# CATEGORICAL BREAKDOWNS
# ===========================================================================

def debit_credit_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """
    Split totals, counts, and percentages by Debit vs Credit.

    Returns
    -------
    dict:
        { "debit":  { total, count, pct_by_count, pct_by_amount },
          "credit": { total, count, pct_by_count, pct_by_amount } }
    """
    if df.empty:
        empty = {"total": 0.0, "count": 0, "pct_by_count": 0.0, "pct_by_amount": 0.0}
        return {"debit": empty.copy(), "credit": empty.copy()}

    amounts   = _amount_series(df)
    d_mask    = _debit_mask(df)
    c_mask    = _credit_mask(df)
    total_all = float(amounts.dropna().sum()) or 1.0  # avoid ZeroDivisionError
    n_total   = len(df) or 1

    def _side(mask: pd.Series) -> dict[str, Any]:
        sub    = amounts[mask].dropna()
        total  = float(sub.sum())
        count  = int(mask.sum())
        return {
            "total":          round(total,                         2),
            "count":          count,
            "pct_by_count":   round(count  / n_total   * 100,     2),
            "pct_by_amount":  round(total  / total_all * 100,     2),
        }

    return {"debit": _side(d_mask), "credit": _side(c_mask)}


def merchant_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """
    Per-merchant spend summary.

    Returns
    -------
    dict:
        { "total_unique_merchants": int,
          "merchants": list[{ merchant, total_amount, count, avg_amount }] }
    """
    if df.empty or "merchant" not in df.columns:
        return {"total_unique_merchants": 0, "merchants": []}

    work = df.copy()
    work["_amount"] = _amount_series(work)
    work = work.dropna(subset=["merchant"])
    work = work[work["merchant"].str.strip() != ""]

    if work.empty:
        return {"total_unique_merchants": 0, "merchants": []}

    grouped = (
        work.groupby("merchant")["_amount"]
        .agg(total_amount="sum", count="count", avg_amount="mean")
        .reset_index()
        .sort_values("total_amount", ascending=False)
    )

    merchants = [
        {
            "merchant":     row["merchant"],
            "total_amount": round(float(row["total_amount"]), 2),
            "count":        int(row["count"]),
            "avg_amount":   round(float(row["avg_amount"]),   2),
        }
        for _, row in grouped.iterrows()
    ]

    return {
        "total_unique_merchants": len(merchants),
        "merchants":              merchants,
    }


def top_merchants(df: pd.DataFrame, top_n: int = 10) -> list[dict[str, Any]]:
    """
    Return the *top_n* merchants ranked by total spend.

    Parameters
    ----------
    df    : pd.DataFrame
    top_n : int (default 10)

    Returns
    -------
    list[dict] — same schema as merchant_analysis()["merchants"] but capped.
    """
    analysis = merchant_analysis(df)
    return analysis["merchants"][:top_n]


def transaction_type_distribution(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Count and percentage breakdown by transaction_type.

    Returns
    -------
    list[dict]:
        [ { "transaction_type": str, "count": int, "pct": float }, … ]
    """
    if df.empty or "transaction_type" not in df.columns:
        return []

    series = df["transaction_type"].dropna()
    series = series[series.str.strip() != ""]

    if series.empty:
        return []

    counts  = series.value_counts()
    n_total = len(series)

    return [
        {
            "transaction_type": str(txn_type),
            "count":            int(count),
            "pct":              round(count / n_total * 100, 2),
        }
        for txn_type, count in counts.items()
    ]


# ===========================================================================
# SPENDING TRENDS
# ===========================================================================

def spending_trends(df: pd.DataFrame) -> dict[str, Any]:
    """
    Week-over-week and month-over-month spending change metrics.

    Returns
    -------
    dict:
        { "weekly_spending":  list[{ week, total_debit }],
          "monthly_spending": list[{ month, total_debit }],
          "wow_change_pct":   float | None,   # last week vs prior week
          "mom_change_pct":   float | None }  # last month vs prior month
    """
    if df.empty or "amount" not in df.columns:
        return {
            "weekly_spending":  [],
            "monthly_spending": [],
            "wow_change_pct":   None,
            "mom_change_pct":   None,
        }

    work = df.copy()
    work["_date"]   = _ensure_date(work)
    work["_amount"] = _amount_series(work)
    work = work.dropna(subset=["_date"])
    d_mask = _debit_mask(work)

    # Weekly
    work["_week"] = work["_date"].dt.to_period("W")
    weekly = (
        work[d_mask].groupby("_week")["_amount"]
        .sum().reset_index()
        .sort_values("_week")
    )
    weekly_list = [
        {"week": str(r["_week"]), "total_debit": round(float(r["_amount"]), 2)}
        for _, r in weekly.iterrows()
    ]

    # Monthly
    work["_month"] = work["_date"].dt.to_period("M")
    monthly = (
        work[d_mask].groupby("_month")["_amount"]
        .sum().reset_index()
        .sort_values("_month")
    )
    monthly_list = [
        {"month": str(r["_month"]), "total_debit": round(float(r["_amount"]), 2)}
        for _, r in monthly.iterrows()
    ]

    def _pct_change(series: list[dict], key: str) -> float | None:
        vals = [r["total_debit"] for r in series]
        if len(vals) < 2 or vals[-2] == 0:
            return None
        return round((vals[-1] - vals[-2]) / vals[-2] * 100, 2)

    return {
        "weekly_spending":  weekly_list,
        "monthly_spending": monthly_list,
        "wow_change_pct":   _pct_change(weekly_list,  "week"),
        "mom_change_pct":   _pct_change(monthly_list, "month"),
    }


# ===========================================================================
# RECHARTS-READY CHART DATA
# ===========================================================================

def generate_chart_data(df: pd.DataFrame) -> dict[str, Any]:
    """
    Build Recharts-ready datasets for the frontend.

    Every chart follows this envelope:
        { "labels": [...], "values": [...] }

    Additional per-series charts include a "series" list for multi-line charts.

    Returns
    -------
    dict with chart keys:
        daily_volume, monthly_trends, debit_vs_credit,
        top_merchants_chart, transaction_type_chart, spending_trend_chart
    """
    # ── Daily volume ─────────────────────────────────────────────────────
    daily = daily_transaction_volume(df)
    daily_chart = {
        "labels": [r["date"]         for r in daily],
        "values": [r["total_amount"] for r in daily],
    }

    # ── Monthly debit / credit (multi-series) ────────────────────────────
    monthly = monthly_transaction_trends(df)
    monthly_chart = {
        "labels": [r["month"] for r in monthly],
        "series": [
            {"name": "Debit",  "values": [r["total_debit"]  for r in monthly]},
            {"name": "Credit", "values": [r["total_credit"] for r in monthly]},
            {"name": "Net",    "values": [r["net"]          for r in monthly]},
        ],
    }

    # ── Debit vs Credit pie ───────────────────────────────────────────────
    dca = debit_credit_analysis(df)
    debit_vs_credit = {
        "labels": ["Debit", "Credit"],
        "values": [dca["debit"]["total"], dca["credit"]["total"]],
    }

    # ── Top merchants bar ─────────────────────────────────────────────────
    tm = top_merchants(df, top_n=10)
    top_merchants_chart = {
        "labels": [r["merchant"]     for r in tm],
        "values": [r["total_amount"] for r in tm],
    }

    # ── Transaction type donut ────────────────────────────────────────────
    txn_dist = transaction_type_distribution(df)
    txn_type_chart = {
        "labels": [r["transaction_type"] for r in txn_dist],
        "values": [r["count"]            for r in txn_dist],
    }

    # ── Spending trend (monthly debits) ───────────────────────────────────
    trends = spending_trends(df)
    spending_trend_chart = {
        "labels": [r["month"]       for r in trends["monthly_spending"]],
        "values": [r["total_debit"] for r in trends["monthly_spending"]],
    }

    return {
        "daily_volume":         daily_chart,
        "monthly_trends":       monthly_chart,
        "debit_vs_credit":      debit_vs_credit,
        "top_merchants_chart":  top_merchants_chart,
        "transaction_type_chart": txn_type_chart,
        "spending_trend_chart": spending_trend_chart,
    }


# ===========================================================================
# MASTER REPORT
# ===========================================================================

def generate_analytics_report(df: pd.DataFrame) -> dict[str, Any]:
    """
    Compile the complete analytics report consumed by app.py and all
    downstream service modules (fraud.py, risk_engine.py, llm_summary.py,
    report_generator.py).

    Parameters
    ----------
    df : pd.DataFrame
        Typed DataFrame from app.py's step_to_dataframe().

    Returns
    -------
    dict with three top-level keys:

    "statistics" — raw numbers for downstream computation
        All fields from summary_statistics(), plus:
        transaction_type_distribution, debit_credit_breakdown,
        merchant_summary, schema_validation

    "insights" — distilled key metrics for the summary panel and LLM prompt
        total_debit, total_credit, net_cash_flow, closing_balance,
        average_daily_spending, largest_debit, largest_credit,
        top_merchants, wow_change_pct, mom_change_pct

    "charts" — Recharts-ready datasets
        All keys from generate_chart_data()
    """
    logger.info("Generating analytics report for %d rows…", len(df))

    # Guard: return a valid but empty report for an empty DataFrame
    if df.empty:
        logger.warning("DataFrame is empty — returning zero-value report.")
        return {
            "statistics": summary_statistics(df),
            "insights":   {},
            "charts":     {},
        }

    # ── Statistics block ──────────────────────────────────────────────────
    stats = summary_statistics(df)
    stats["schema_validation"]          = validate_schema(df)
    stats["transaction_type_distribution"] = transaction_type_distribution(df)
    stats["debit_credit_breakdown"]     = debit_credit_analysis(df)
    stats["merchant_summary"]           = merchant_analysis(df)
    stats["daily_transaction_volume"]   = daily_transaction_volume(df)
    stats["monthly_transaction_trends"] = monthly_transaction_trends(df)
    stats["spending_trends"]            = spending_trends(df)

    # ── Insights block (flattened for easy consumption by other modules) ──
    trends_data = spending_trends(df)
    insights: dict[str, Any] = {
        "total_debit":            stats["total_debit"],
        "total_credit":           stats["total_credit"],
        "net_cash_flow":          stats["net_cash_flow"],
        "closing_balance":        stats["closing_balance"],
        "average_daily_spending": stats["average_daily_spending"],
        "largest_debit":          stats["largest_debit"],
        "largest_credit":         stats["largest_credit"],
        "average_transaction":    stats["average_transaction"],
        "median_transaction":     stats["median_transaction"],
        "top_merchants":          top_merchants(df, top_n=10),
        "wow_change_pct":         trends_data["wow_change_pct"],
        "mom_change_pct":         trends_data["mom_change_pct"],
    }

    # ── Charts block ──────────────────────────────────────────────────────
    charts = generate_chart_data(df)

    logger.info("Analytics report complete.")
    return {
        "statistics": stats,
        "insights":   insights,
        "charts":     charts,
    }
