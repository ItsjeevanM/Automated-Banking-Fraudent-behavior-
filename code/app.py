# app.py
# Main Streamlit application — Bank Statement Analysis Platform

import streamlit as st
import pandas as pd
from analytics import (
    clean_data, get_summary,
    chart_debit_credit, chart_txn_type,
    chart_top_merchants, chart_daily_volume,
    chart_monthly_spend
)
from risk_engine import (
    detect_suspicious, build_flag_table,
    calculate_risk_score, get_risk_label
)

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="Bank Statement Analyzer",
    page_icon="",
    layout="wide"
)

# --------------------------------------------------
# SIDEBAR NAVIGATION
# --------------------------------------------------

st.sidebar.title("Bank Analyzer")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Upload Data", " Dashboard", "Risk Analysis"]
)

st.sidebar.markdown("---")
st.sidebar.caption("College Project Demo · 2024")

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

if "df" not in st.session_state:
    st.session_state.df = None


# ==================================================
# PAGE 1 — UPLOAD DATA
# ==================================================

if page == "Upload Data":

    st.title("Upload Bank Statement")
    st.markdown("Upload a CSV file exported from your bank. Columns are auto-detected and standardized.")

    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])

    if uploaded_file:
        raw_df = pd.read_csv(uploaded_file)

        st.subheader(" Raw Data Preview")
        st.dataframe(raw_df.head(20), use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Rows",    len(raw_df))
            st.metric("Total Columns", len(raw_df.columns))
        with col2:
            st.metric("Missing Values",  int(raw_df.isnull().sum().sum()))
            st.metric("Duplicate Rows",  int(raw_df.duplicated().sum()))

        st.subheader("Column Info")
        col_info = pd.DataFrame({
            "Column":          raw_df.columns,
            "Type":            raw_df.dtypes.values,
            "Non-Null Count":  raw_df.notnull().sum().values,
            "Sample Value":    [
                str(raw_df[c].dropna().iloc[0]) if not raw_df[c].dropna().empty else "N/A"
                for c in raw_df.columns
            ]
        })
        st.dataframe(col_info, use_container_width=True)

        # Clean and store in session state
        cleaned = clean_data(raw_df.copy())
        st.session_state.df = cleaned

        st.success(f" Data cleaned and ready! {len(cleaned)} rows loaded.")

        st.subheader("🧹 Cleaned Data Preview")
        st.dataframe(cleaned.head(20), use_container_width=True)

    else:
        st.info(" Upload a CSV file to get started.")

        st.markdown("#### Expected CSV columns (any of these formats work):")
        sample = pd.DataFrame({
            "Date / valueDate":              ["2024-01-01", "2024-01-02"],
            "type / Debit/Credit":           ["DEBIT",      "CREDIT"],
            "amount":                        [5000,          15000],
            "currentBalance / Balance":      [95000,         110000],
            "mode / Transaction Type":       ["UPI",         "NEFT"],
            "narration / Merchant":          ["Swiggy",      "Salary"]
        })
        st.dataframe(sample, use_container_width=True)


# ==================================================
# PAGE 2 — DASHBOARD
# ==================================================

elif page == " Dashboard":

    st.title("Analytics Dashboard")

    if st.session_state.df is None:
        st.warning("Please upload a CSV file first from the Upload Data page.")
        st.stop()

    df      = st.session_state.df
    summary = get_summary(df)

    # ---------- Summary Metrics ----------
    st.subheader(" Key Metrics")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Transactions", summary["total_transactions"])
    m2.metric("Total Amount",       f"₹{summary['total_amount']:,.0f}")
    m3.metric("Avg Transaction",    f"₹{summary['avg_amount']:,.0f}")
    m4.metric("Total Debit",        f"₹{summary['total_debit']:,.0f}")
    m5.metric("Total Credit",       f"₹{summary['total_credit']:,.0f}")

    st.markdown("---")

    m6, m7, m8 = st.columns(3)
    m6.metric("Max Transaction", f"₹{summary['max_amount']:,.0f}")
    m7.metric("Top Txn Type",    summary["top_txn_type"])
    m8.metric("Top Merchant",    summary["top_merchant"])

    st.markdown("---")

    # ---------- Charts Row 1 ----------
    col1, col2 = st.columns(2)

    with col1:
        fig = chart_debit_credit(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Debit/Credit column not detected.")

    with col2:
        fig = chart_txn_type(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Transaction Type column not detected.")

    # ---------- Charts Row 2 ----------
    col3, col4 = st.columns(2)

    with col3:
        fig = chart_top_merchants(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Merchant column not detected.")

    with col4:
        fig = chart_daily_volume(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Date column not detected.")

    # ---------- Monthly Trend — Full Width ----------
    fig = chart_monthly_spend(df)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Monthly trend not available — Date column not detected.")


# ==================================================
# PAGE 3 — RISK ANALYSIS
# ==================================================

elif page == "Risk Analysis":

    st.title("Risk Analysis")

    if st.session_state.df is None:
        st.warning(" Please upload a CSV file first from the Upload Data page.")
        st.stop()

    df = st.session_state.df

    # ---------- Threshold Config ----------
    st.subheader(" Configuration")
    threshold = st.slider(
        "High-Value Transaction Threshold (₹)",
        min_value=1000,
        max_value=500000,
        value=50000,
        step=1000
    )

    st.markdown("---")

    # ---------- Run Risk Engine ----------
    flags       = detect_suspicious(df, high_value_threshold=threshold)
    flag_table  = build_flag_table(df, flags)
    risk_score  = calculate_risk_score(df, flags)
    risk_label, risk_color = get_risk_label(risk_score)

    # ---------- Risk Score Display ----------
    st.subheader("Overall Risk Score")

    # FIX: use "txn_index" column (not "index") — safe even when empty
    n_flagged = flag_table["txn_index"].nunique() if not flag_table.empty else 0

    score_col, label_col, flagged_col = st.columns(3)
    score_col.metric("Risk Score",            f"{risk_score} / 100")
    label_col.metric("Risk Level",            risk_label)
    flagged_col.metric("Flagged Transactions", f"{n_flagged} / {len(df)}")

    # Visual progress bar
    st.markdown(f"""
    <div style="background:#e5e7eb;border-radius:8px;height:20px;margin:8px 0 16px 0;">
        <div style="background:{risk_color};width:{risk_score}%;height:20px;
                    border-radius:8px;transition:width 0.5s;">
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ---------- Rules Legend ----------
    with st.expander("Risk Rules Applied"):
        st.markdown("""
        | Rule | Description | Risk Points |
        |------|-------------|-------------|
        | High-Value Transaction | Amount exceeds configured threshold | 30 pts |
        | Repeated Amount | Same amount appears 3+ times | 20 pts |
        | Spending Spike | Amount > mean + 2 standard deviations | 25 pts |
        | Multiple Same-Day | More than 5 transactions on one day | 15 pts |
        | Excessive Debits | Debits exceed 80% of total transaction value | 10 pts |
        """)

    # ---------- Suspicious Transactions Table ----------
    st.subheader(" Suspicious Transactions")

    if flag_table.empty:
        st.success(" No suspicious transactions detected with current settings.")
    else:
        # FIX: use .map() instead of deprecated .applymap()
        def highlight_risk(val):
            if isinstance(val, (int, float)):
                if val >= 61:
                    return "background-color: #FEE2E2; color: #991B1B"
                elif val >= 31:
                    return "background-color: #FEF9C3; color: #92400E"
                else:
                    return "background-color: #DCFCE7; color: #166534"
            return ""

        # Drop internal index column before display
        display_df = flag_table.drop(columns=["txn_index"], errors="ignore")

        try:
            # Pandas >= 2.1 uses .map(); older uses .applymap()
            styled = display_df.style.map(highlight_risk, subset=["risk_points"])
        except AttributeError:
            styled = display_df.style.applymap(highlight_risk, subset=["risk_points"])

        st.dataframe(styled, use_container_width=True)

        # Download button
        csv_out = display_df.to_csv(index=False)
        st.download_button(
            label="⬇Download Flagged Transactions CSV",
            data=csv_out,
            file_name="flagged_transactions.csv",
            mime="text/csv"
        )

    st.markdown("---")

    # ---------- Risk Score Breakdown ----------
    st.subheader(" Risk Score Breakdown")

    score_ranges = pd.DataFrame({
        "Risk Level":  ["Low",    " Medium",                    "High"],
        "Score Range": ["0 – 30",    "31 – 60",                      "61 – 100"],
        "Meaning":     [
            "Normal transaction behaviour",
            "Some unusual patterns detected",
            "Multiple high-risk patterns found"
        ]
    })
    st.table(score_ranges)
