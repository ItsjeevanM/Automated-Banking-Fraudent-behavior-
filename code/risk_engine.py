# risk_engine.py
# Rule-based suspicious transaction detection and risk scoring

import pandas as pd
import numpy as np


# --------------------------------------------------
# RULE ENGINE
# --------------------------------------------------

def detect_suspicious(df, high_value_threshold=50000):
    """
    Applies rule-based checks to flag suspicious transactions.
    Returns a list of dicts: {index, reason, risk_points}
    """

    flags = []

    # ---------- Rule 1: High-Value Transaction ----------
    if "amount" in df.columns:
        high_value = df[df["amount"] > high_value_threshold]
        for idx in high_value.index:
            flags.append({
                "index": idx,
                "reason": f"High-value transaction (₹{df.loc[idx, 'amount']:,.0f} > threshold ₹{high_value_threshold:,})",
                "risk_points": 30
            })

    # ---------- Rule 2: Repeated Same Amount ----------
    if "amount" in df.columns:
        amount_counts = df["amount"].value_counts()
        repeated_amounts = amount_counts[amount_counts >= 3].index.tolist()
        repeated_txns = df[df["amount"].isin(repeated_amounts)]
        for idx in repeated_txns.index:
            amt = df.loc[idx, "amount"]
            flags.append({
                "index": idx,
                "reason": f"Repeated transaction amount (₹{amt:,.0f} appears {int(amount_counts[amt])}x)",
                "risk_points": 20
            })

    # ---------- Rule 3: Spending Spike ----------
    if "amount" in df.columns:
        mean_amt = df["amount"].mean()
        std_amt  = df["amount"].std()
        # Guard: std can be 0 or NaN on very small datasets
        if pd.notna(std_amt) and std_amt > 0:
            spike_threshold = mean_amt + 2 * std_amt
            spikes = df[df["amount"] > spike_threshold]
            for idx in spikes.index:
                flags.append({
                    "index": idx,
                    "reason": f"Unusual spending spike (₹{df.loc[idx, 'amount']:,.0f} exceeds mean+2σ = ₹{spike_threshold:,.0f})",
                    "risk_points": 25
                })

    # ---------- Rule 4: Multiple Transactions in Short Time ----------
    if "date" in df.columns:
        # Work on a copy with only non-null dates
        date_series = df["date"].dropna()
        if not date_series.empty:
            date_counts = date_series.dt.date.value_counts()
            busy_dates  = date_counts[date_counts > 5].index.tolist()
            if busy_dates:
                busy_mask = df["date"].notna() & df["date"].dt.date.isin(busy_dates)
                for idx in df[busy_mask].index:
                    txn_date = df.loc[idx, "date"].date()
                    flags.append({
                        "index": idx,
                        "reason": f"Multiple transactions on same day ({date_counts[txn_date]} txns on {txn_date})",
                        "risk_points": 15
                    })

    # ---------- Rule 5: Excessive Debits ----------
    if "debit_credit" in df.columns and "amount" in df.columns:
        debit_df     = df[df["debit_credit"].str.upper() == "DEBIT"]
        total_debit  = debit_df["amount"].sum()
        total_amount = df["amount"].sum()
        if total_amount > 0 and (total_debit / total_amount) > 0.8:
            for idx in debit_df.index:
                flags.append({
                    "index": idx,
                    "reason": f"Excessive withdrawals — debits are {(total_debit/total_amount)*100:.1f}% of all transactions",
                    "risk_points": 10
                })

    return flags


# --------------------------------------------------
# AGGREGATE FLAGS INTO A CLEAN TABLE
# --------------------------------------------------

def build_flag_table(df, flags):
    """
    Merges flags with original transaction rows.
    Returns a clean DataFrame of suspicious transactions.
    """
    if not flags:
        return pd.DataFrame(columns=["txn_index", "amount", "reason", "risk_points"])

    flag_df = pd.DataFrame(flags)

    # Combine multiple reasons and sum risk points for the same transaction
    flag_df = (
        flag_df.groupby("index")
        .agg(
            reason      =("reason",      " | ".join),
            risk_points =("risk_points", "sum")
        )
        .reset_index()
        # Rename so we don't lose the index reference after merging
        .rename(columns={"index": "txn_index"})
    )

    # Cap risk points per transaction at 100
    flag_df["risk_points"] = flag_df["risk_points"].clip(upper=100)

    # Pick relevant display columns from original df
    display_cols = ["amount"]
    for col in ["date", "merchant", "transaction_type", "debit_credit", "balance"]:
        if col in df.columns:
            display_cols.append(col)

    # Merge on positional index
    merged = flag_df.merge(
        df[display_cols].reset_index().rename(columns={"index": "txn_index"}),
        on="txn_index",
        how="left"
    )

    return merged


# --------------------------------------------------
# OVERALL RISK SCORE
# --------------------------------------------------

def calculate_risk_score(df, flags):
    """
    Computes an overall portfolio risk score between 0 and 100.
    """
    if not flags or len(df) == 0:
        return 0

    flag_df = pd.DataFrame(flags)

    unique_flagged = flag_df["index"].nunique()
    flagged_ratio  = unique_flagged / len(df)

    avg_severity = flag_df.groupby("index")["risk_points"].sum().mean()
    avg_severity = min(avg_severity, 100)

    # 60% weight on ratio of flagged transactions, 40% on severity
    score = (flagged_ratio * 60) + (avg_severity / 100 * 40)
    score = round(min(score, 100), 1)

    return score


# --------------------------------------------------
# RISK LABEL
# --------------------------------------------------

def get_risk_label(score):
    """Returns risk level label and color."""
    if score <= 30:
        return "🟢 Low Risk", "#22C55E"
    elif score <= 60:
        return "🟡 Medium Risk", "#F59E0B"
    else:
        return "🔴 High Risk", "#EF4444"
