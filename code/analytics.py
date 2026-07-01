# analytics.py
# Handles all data processing and chart generation

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


# --------------------------------------------------
# DATA CLEANING
# --------------------------------------------------

def clean_data(df):
    """
    Maps actual CSV columns to standardized schema.
    Handles the real dataset columns:
      type, mode, amount, currentBalance,
      transactionTimestamp, valueDate, txnId, narration, reference
    Target schema:
      debit_credit, transaction_type, amount, balance, date, merchant, month
    """

    # Step 1: Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # --------------------------------------------------
    # Explicit column mapping for this dataset
    # --------------------------------------------------
    rename_map = {}

    for col in df.columns:
        col_lower = col.lower()

        # type → debit_credit  (contains DEBIT/CREDIT values)
        if col_lower == "type":
            rename_map[col] = "debit_credit"

        # mode → transaction_type  (ATM/CARD/UPI/NEFT etc.)
        elif col_lower == "mode":
            rename_map[col] = "transaction_type"

        # amount stays as amount
        elif col_lower == "amount":
            rename_map[col] = "amount"

        # currentBalance → balance
        elif col_lower == "currentbalance":
            rename_map[col] = "balance"

        # valueDate → date  (prefer this over transactionTimestamp)
        elif col_lower == "valuedate":
            rename_map[col] = "date"

        # narration → merchant
        elif col_lower == "narration":
            rename_map[col] = "merchant"

    df.rename(columns=rename_map, inplace=True)

    # --------------------------------------------------
    # Fallback: generic detection for other CSV formats
    # (only runs if explicit mapping above didn't catch it)
    # --------------------------------------------------

    if "debit_credit" not in df.columns:
        for col in df.columns:
            if "debit" in col.lower() or "credit" in col.lower():
                df.rename(columns={col: "debit_credit"}, inplace=True)
                break

    if "transaction_type" not in df.columns:
        for col in df.columns:
            if "mode" in col.lower() or "txn_type" in col.lower():
                df.rename(columns={col: "transaction_type"}, inplace=True)
                break

    if "balance" not in df.columns:
        for col in df.columns:
            if "balance" in col.lower():
                df.rename(columns={col: "balance"}, inplace=True)
                break

    if "date" not in df.columns:
        for col in df.columns:
            if "date" in col.lower():
                df.rename(columns={col: "date"}, inplace=True)
                break

    if "merchant" not in df.columns:
        for col in df.columns:
            col_lower = col.lower()
            if any(k in col_lower for k in ["merchant", "place", "description", "narration", "remarks"]):
                df.rename(columns={col: "merchant"}, inplace=True)
                break

    # --------------------------------------------------
    # Type conversions
    # --------------------------------------------------

    # Parse date column safely
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Parse transactionTimestamp if present (for time info)
    if "transactionTimestamp" in df.columns:
        df["transactionTimestamp"] = pd.to_datetime(
            df["transactionTimestamp"], utc=True, errors="coerce"
        )

    # Ensure amount is numeric
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    # Ensure balance is numeric
    if "balance" in df.columns:
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce")

    # --------------------------------------------------
    # Drop rows where amount is missing (unusable records)
    # --------------------------------------------------
    if "amount" in df.columns:
        df.dropna(subset=["amount"], inplace=True)

    # --------------------------------------------------
    # FIX: Fill missing values by column dtype
    # NEVER fill numeric columns with strings
    # --------------------------------------------------
    for col in df.columns:
        if df[col].dtype == object:
            # Text columns → fill with "Unknown"
            df[col] = df[col].fillna("Unknown")
        else:
            # Numeric/datetime columns → leave NaN or fill with 0
            # (leave as NaN so charts/aggregations handle them correctly)
            pass

    # --------------------------------------------------
    # Add helper columns
    # --------------------------------------------------
    if "date" in df.columns:
        df["month"] = df["date"].dt.to_period("M").astype(str)

    # Standardize debit_credit to uppercase
    if "debit_credit" in df.columns:
        df["debit_credit"] = df["debit_credit"].str.strip().str.upper()

    # Standardize transaction_type to uppercase
    if "transaction_type" in df.columns:
        df["transaction_type"] = df["transaction_type"].str.strip().str.upper()

    return df


# --------------------------------------------------
# SUMMARY METRICS
# --------------------------------------------------

def get_summary(df):
    """
    Returns a dict of key summary metrics.
    """
    summary = {}

    summary["total_transactions"] = len(df)
    summary["total_amount"]       = df["amount"].sum() if "amount" in df.columns else 0
    summary["avg_amount"]         = df["amount"].mean() if "amount" in df.columns else 0
    summary["max_amount"]         = df["amount"].max() if "amount" in df.columns else 0
    summary["min_amount"]         = df["amount"].min() if "amount" in df.columns else 0

    # Debit vs Credit totals
    if "debit_credit" in df.columns and "amount" in df.columns:
        dc = df["debit_credit"].str.upper()
        summary["total_debit"]   = df.loc[dc == "DEBIT",  "amount"].sum()
        summary["total_credit"]  = df.loc[dc == "CREDIT", "amount"].sum()
    else:
        summary["total_debit"]  = 0
        summary["total_credit"] = 0

    # Most common transaction type
    if "transaction_type" in df.columns and len(df) > 0:
        summary["top_txn_type"] = df["transaction_type"].mode()[0]
    else:
        summary["top_txn_type"] = "N/A"

    # Top merchant
    if "merchant" in df.columns and len(df) > 0:
        summary["top_merchant"] = df["merchant"].mode()[0]
    else:
        summary["top_merchant"] = "N/A"

    return summary


# --------------------------------------------------
# CHARTS
# --------------------------------------------------

def chart_debit_credit(df):
    """Bar chart — total amount split by Debit vs Credit."""
    if "debit_credit" not in df.columns or "amount" not in df.columns:
        return None

    # Safe: drop rows where either column is null before grouping
    temp = df[["debit_credit", "amount"]].dropna()
    if temp.empty:
        return None

    grouped = (
        temp.groupby(temp["debit_credit"].str.upper())["amount"]
        .sum()
        .reset_index()
    )
    grouped.columns = ["Type", "Total Amount"]

    fig = px.bar(
        grouped,
        x="Type",
        y="Total Amount",
        color="Type",
        color_discrete_map={"DEBIT": "#EF4444", "CREDIT": "#22C55E"},
        title="Debit vs Credit — Total Amount",
        text_auto=".2s",
    )
    fig.update_layout(showlegend=False)
    return fig


def chart_txn_type(df):
    """Pie chart — transaction type distribution."""
    if "transaction_type" not in df.columns:
        return None

    grouped = df["transaction_type"].value_counts().reset_index()
    grouped.columns = ["Transaction Type", "Count"]

    fig = px.pie(
        grouped,
        names="Transaction Type",
        values="Count",
        title="Transaction Type Distribution",
        hole=0.4,
    )
    return fig


def chart_top_merchants(df, top_n=10):
    """Horizontal bar chart — top merchants by total spend."""
    if "merchant" not in df.columns or "amount" not in df.columns:
        return None

    temp = df[["merchant", "amount"]].dropna()
    if temp.empty:
        return None

    grouped = (
        temp.groupby("merchant")["amount"]
        .sum()
        .nlargest(top_n)
        .reset_index()
    )
    grouped.columns = ["Merchant", "Total Amount"]

    fig = px.bar(
        grouped,
        x="Total Amount",
        y="Merchant",
        orientation="h",
        title=f"Top {top_n} Merchants by Spend",
        color="Total Amount",
        color_continuous_scale="Blues",
        text_auto=".2s",
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return fig


def chart_daily_volume(df):
    """Line chart — daily transaction count."""
    if "date" not in df.columns:
        return None

    temp = df[["date"]].dropna()
    if temp.empty:
        return None

    daily = temp.groupby("date").size().reset_index(name="Count")

    fig = px.line(
        daily,
        x="date",
        y="Count",
        title="Daily Transaction Volume",
        markers=True,
    )
    fig.update_traces(line_color="#6366F1")
    return fig


def chart_monthly_spend(df):
    """Bar chart — monthly total spend trend."""
    if "month" not in df.columns or "amount" not in df.columns:
        return None

    temp = df[["month", "amount"]].dropna()
    if temp.empty:
        return None

    monthly = (
        temp.groupby("month")["amount"]
        .sum()
        .reset_index()
    )
    monthly.columns = ["Month", "Total Spend"]

    fig = px.bar(
        monthly,
        x="Month",
        y="Total Spend",
        title="Monthly Spending Trend",
        color="Total Spend",
        color_continuous_scale="Purples",
        text_auto=".2s",
    )
    return fig
