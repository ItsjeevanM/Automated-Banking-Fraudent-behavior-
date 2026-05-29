# 🏦 Automated Bank Statement Analyzer

> **Intelligent financial forensics platform** — extract, standardize, detect suspicious transactions, and generate evidence-ready reports from raw bank statements.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Streamlit-1.x-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
  <img src="https://img.shields.io/badge/Pandas-Data%20Processing-150458?style=for-the-badge&logo=pandas&logoColor=white"/>
  <img src="https://img.shields.io/badge/Plotly-Interactive%20Charts-3F4F75?style=for-the-badge&logo=plotly&logoColor=white"/>
  <img src="https://img.shields.io/badge/Status-Active%20Development-green?style=for-the-badge"/>
</p>

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Live Application Screenshots](#-live-application-screenshots)
- [Current Features](#-current-features)
- [AI Feature Roadmap](#-ai-feature-roadmap--planned)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Installation & Setup](#-installation--setup)
- [Usage Guide](#-usage-guide)
- [Data Format](#-data-format)
- [Future Work](#-future-work)

---

## 🎯 Overview

The growth of digital banking has created an explosion of financial transaction data, making manual analysis slow, error-prone, and impractical at scale. **Automated Bank Statement Analyzer** is a full-stack intelligence platform that turns raw bank statement files into actionable financial insights and fraud-detection reports.

### What This Platform Does

| Stage | What Happens |
|---|---|
| **Ingest** | Accepts CSV exports from any Indian bank; auto-detects and maps column schemas |
| **Standardize** | Cleans timestamps, normalizes debit/credit labels, resolves merchant names |
| **Analyze** | Computes key metrics, merchant rankings, spending trends, and transaction distributions |
| **Detect** | Applies configurable risk rules to score and flag suspicious transactions |
| **Report** | Surfaces risk scores, flagged transaction counts, and risk levels in a compliance-ready view |

The platform is purpose-built for **compliance officers, forensic auditors, financial investigators, and individuals** who need to understand large volumes of transaction data quickly — without writing a single line of SQL or code.

---

## 📸 Live Application Screenshots

### 1 · Upload Bank Statement
Upload any CSV exported from your bank. The platform auto-detects column names and formats from major Indian banks (HDFC, ICICI, SBI, Axis, Kotak, and more).

![Upload Bank Statement](screenshots/01_upload_data.png)

> **How it works:** The upload module maps any combination of column names — `type / Debit/Credit`, `mode / Transaction Type`, `narration / Merchant` — to a unified internal schema. No manual column mapping required.

---

### 2 · Raw Data Preview
After upload, the raw file is displayed exactly as received, before any transformations — preserving original timestamps with IST timezone offsets, original narrations, and merchant identifiers.

![Raw Data Preview](screenshots/02_raw_data_preview.png)

> **Sample columns detected:** `type`, `mode`, `amount`, `currentBalance`, `transactionTimestamp`, `valueDate`, `txnId`, `narration`

---

### 3 · Cleaned & Standardized Data
The platform applies data cleaning rules: UTC normalization, debit/credit label standardization, duplicate removal, and null handling — then previews the 985-row cleaned dataset ready for analysis.

![Cleaned Data Preview](screenshots/03_cleaned_data_preview.png)

> **Transformations applied:** Column renaming → Timestamp UTC conversion → Debit/Credit normalization → Balance reconciliation → Transaction ID deduplication

---

### 4 · Analytics Dashboard — Key Metrics
The main dashboard surfaces all critical financial KPIs at a glance, computed across the entire statement period.

![Analytics Dashboard](screenshots/04_analytics_dashboard.png)

| Metric | Value (Sample Dataset) |
|---|---|
| Total Transactions | 985 |
| Total Amount | ₹8,42,660 |
| Avg Transaction | ₹855 |
| Total Debit | ₹4,22,090 |
| Total Credit | ₹4,20,571 |
| Max Single Transaction | ₹45,000 |
| Top Transaction Type | UPI |
| Top Merchant | NEFT |

---

### 5 · Top Merchants & Daily Volume
Visualizes the top 10 merchants by total spend and the daily transaction volume pattern across the statement period — revealing behavioral patterns at a glance.

![Merchant and Volume Charts](screenshots/05_merchants_volume.png)

> **Insight from sample data:** NEFT transfers dominate (₹1.7L total), followed by cash withdrawals and UPI payments. Daily volume spikes visible in Oct–Nov 2023 warrant further investigation.

---

### 6 · Monthly Spending Trend
A color-intensity bar chart tracks total monthly spending from July 2023 through May 2024 — immediately surfacing anomalous months.

![Monthly Spending Trend](screenshots/06_monthly_trend.png)

> **Anomaly visible:** November 2023 shows ₹2,30,000 in spending — **4.8× the average monthly spend** — flagged as a high-risk period requiring investigation.

---

### 7 · Risk Analysis
The risk engine evaluates all transactions against configurable rules and computes an overall account risk score. Analysts can tune the high-value transaction threshold using an interactive slider.

![Risk Analysis](screenshots/07_risk_analysis.png)

| Risk Indicator | Value |
|---|---|
| Overall Risk Score | **62.8 / 100** |
| Risk Level | 🔴 **High Risk** |
| Flagged Transactions | **868 / 985** (88%) |
| High-Value Threshold | ₹50,000 (configurable) |

---

## ✅ Current Features

### 📁 Data Ingestion & Standardization
- CSV upload with automatic column schema detection
- Supports multi-format column naming conventions across Indian banks
- Raw data preview before processing
- UTC timestamp normalization (handles IST +05:30 offsets)
- Debit/Credit label standardization
- Transaction ID deduplication
- Missing value handling and balance reconciliation

### 📊 Analytics Dashboard
- Key financial metrics (total, average, max transactions; debit/credit split)
- Top 10 merchants by total spend — interactive horizontal bar chart
- Daily transaction volume timeline — lollipop/stem chart
- Monthly spending trend — color-intensity bar chart (Jul 2023 – May 2024)
- Transaction type distribution (UPI, NEFT, CARD, ATM, IMPS, OTHERS)
- Debit vs. Credit total amount comparison

### 🚨 Risk Analysis Engine
- Configurable high-value transaction threshold (₹ slider)
- Overall Risk Score (0–100) computed from rule ensemble
- Risk Level classification (Low / Medium / High / Critical)
- Flagged transaction count and percentage
- Risk Rules Applied expandable breakdown
- Color-coded risk progress bar

---

## 🤖 AI Feature Roadmap *(Planned)*

The next phase introduces a full **Explainable AI (XAI)** and **Behavioral Intelligence** layer. All 7 features below are prioritized for implementation.

---

### 1 · SHAP-Based Transaction Explanations
**Category:** Explainable AI

Every flagged transaction receives a plain-English breakdown showing exactly which factors drove its risk score. No more black-box decisions.

```
⚠  FLAGGED — Transaction #TXN-4521
   Amount: ₹87,000  |  Time: 2:14 AM  |  Risk Score: 91

   Why this was flagged:
   ▓▓▓▓▓▓▓▓▓▓  Amount: 6.2× your average night transaction   (+38 pts)
   ▓▓▓▓▓▓▓     Merchant Category: Crypto Exchange (first-time) (+28 pts)
   ▓▓▓▓        Hour: Outside your normal 9 AM–11 PM window    (+17 pts)
   ▓▓          IP geolocation mismatch with home city          (+8 pts)
```

**Tech:** SHAP values on XGBoost/LightGBM classifier; per-transaction feature importance waterfall charts
**Impact:** Transforms ML output into courtroom-ready, auditable evidence

---

### 2 · Confidence Corridors
**Category:** Explainable AI — Uncertainty Quantification

Instead of a single brittle risk score, each flagged transaction shows a **confidence band** — telling the analyst when to trust the model and when to investigate manually.

```
Transaction Risk Assessment:
   Score: 74 ± 12  [Low Confidence → Needs human review]
   Score: 93 ± 3   [High Confidence → Auto-escalate]
```

**Tech:** Monte Carlo Dropout / Bayesian Neural Networks for uncertainty quantification
**Impact:** Calibrated trust in AI — humans intervene exactly where the model is uncertain

---

### 3 · Spending DNA Fingerprint
**Category:** Behavioral Intelligence

Build a unique **behavioral profile per account** — normal spending rhythm, preferred merchant categories, typical transaction size ranges, and geographic footprint. Any deviation from the DNA triggers context-aware alerts.

```
Your Spending DNA Profile:
  ☕ Morning coffee:     ₹180–220, weekday mornings
  🍽  Weekend dining:    ₹1,200–3,500, Fri–Sun evenings
  💰 Salary credit:     1st–2nd of each month, ~₹68,000
  🏪 Grocery run:       ₹2,000–5,000, weekend

🚨 Alert: ₹45,000 grocery transaction — 12× your usual spend
```

**Tech:** Isolation Forest + LSTM autoencoders trained per-user; cosine similarity on spending embeddings
**Impact:** Personalized anomaly detection — not one global threshold applied to all accounts

---

### 4 · Circadian Rhythm Violation Detection
**Category:** Behavioral Intelligence — Temporal Anomaly

Everyone has a **financial circadian rhythm** — times they never transact. Transactions outside a user's personal active window automatically receive elevated risk scores.

```
Profile: User has 0 transactions between 1:00 AM – 5:00 AM
         in the last 18 months of history.

New transaction at 3:47 AM → Circadian Violation Score: +35 pts
Combined with amount anomaly → Total Risk Score: 78
```

**Tech:** Gaussian Mixture Models on transaction hour/weekday distributions per user; KL-divergence scoring
**Impact:** Catches account takeover fraud even when the transaction amount appears normal

---

### 5 · Financial Stress Index (FSI)
**Category:** Behavioral Intelligence — Distress Detection

AI detects early warning signs of **financial distress** from transaction patterns — rapid micro-withdrawals, sudden shift to cash, increased payday loan interactions — before it escalates to a crisis or fraud event.

```
Financial Stress Index: 78 / 100  (Elevated ⚠)

Signals Detected This Month:
  📈 ATM withdrawals: 14 in 8 days  (avg: 2/month)
  💸 3 payday loan deposits detected
  🛒 Supermarket spend: ₹1,800 (↓60% from avg ₹4,500)
  🏧 Cash usage ratio: 67% (↑ from normal 12%)

Recommendation: Flag for welfare check / fraud victim review
```

**Tech:** Gradient Boosted Trees on behavioral indicator features; sliding time-window feature engineering
**Impact:** Banks can proactively offer support; compliance teams identify potential fraud victims early

---

### 6 · Auto-Generated Forensic Report
**Category:** LLM-Powered Intelligence

One-click generation of a **court-ready or compliance-ready narrative report**. An LLM weaves all flagged transactions into a coherent forensic story — timeline, risk assessment, causal narrative, and recommended next action.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORENSIC TRANSACTION ANALYSIS REPORT
Account: XXXX4521  |  Period: March 1–31, 2024
Risk Level: HIGH  |  Generated: Auto (LLM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXECUTIVE SUMMARY
Between March 1–31, this account exhibited 3 distinct
high-risk behavioral clusters. On March 14th, an unusual
sequence of 11 transactions totaling ₹4.2L was recorded
across 6 merchants in 4 cities within a 90-minute window,
suggesting coordinated fraudulent activity or account
compromise. Recommended action: Freeze and investigate.

TIMELINE OF SUSPICIOUS ACTIVITY
[March 7]  First contact with new merchant category (Crypto)
[March 12] Circadian violation — 3:44 AM transfer ₹22,000
[March 14] Velocity burst — 11 transactions in 90 minutes
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Tech:** Claude/GPT-4 with structured chain-of-thought prompting; template-guided generation from aggregated transaction features
**Impact:** Reduces forensic report writing from 4–6 hours to under 60 seconds per case

---

### 7 · Cash Flow Prediction Engine
**Category:** Predictive AI — Time-Series Forecasting

Using historical transaction patterns, the AI **forecasts future account balances day-by-day**, predicts overdraft risk dates, and surfaces upcoming "bill storm" warnings before they arrive.

```
📅 30-Day Balance Forecast — Account XXXX4521

  Day 1   ₹12,400  ──────────────
  Day 5   ₹10,800  ────────────
  Day 8   ₹ 8,200  ──────── ← Estimated rent debit (~₹25,000)
  Day 9   ₹ 6,100  ──────
  Day 11  ₹ 4,800  ───── ⚠ Approaching low balance
  Day 12  ₹ 1,200  ─ 🚨 OVERDRAFT RISK (62% probability)
  Day 22  ₹69,200  ────────────────────── ← Salary credit

Upcoming Bills Detected:
  • Rent debit ~₹25,000 (Day 8, recurring 8th of month)
  • Insurance premium ~₹3,200 (Day 15, recurring)
  • Netflix/OTT ~₹500 (Day 18)
```

**Tech:** Temporal Fusion Transformer (TFT) or N-BEATS; trained on recurring transaction patterns per account
**Impact:** Proactive overdraft prevention + financial wellness features for account holders

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend / UI** | [Streamlit](https://streamlit.io/) |
| **Data Processing** | Pandas, NumPy |
| **Visualization** | Plotly Express, Plotly Graph Objects |
| **Risk Engine** | Rule-based classifier (current), XGBoost/LightGBM (planned) |
| **Explainability (Planned)** | SHAP, DiCE (Diverse Counterfactuals) |
| **Behavioral AI (Planned)** | Scikit-learn, PyTorch / LSTM Autoencoders |
| **LLM Reports (Planned)** | Anthropic Claude API / OpenAI GPT-4 |
| **Forecasting (Planned)** | PyTorch Forecasting (TFT), statsforecast |
| **Language** | Python 3.10+ |

---

## 📁 Project Structure

```
automated-bank-analyzer/
│
├── app.py                          # Main Streamlit entry point
├── requirements.txt
├── README.md
│
├── modules/
│   ├── ingestion/
│   │   ├── csv_loader.py           # Multi-format CSV ingestion
│   │   └── schema_mapper.py        # Auto column detection & mapping
│   │
│   ├── processing/
│   │   ├── cleaner.py              # Data cleaning & standardization
│   │   └── feature_engineer.py    # Feature extraction for ML
│   │
│   ├── analytics/
│   │   ├── dashboard.py            # Key metrics computation
│   │   └── charts.py               # Plotly visualization functions
│   │
│   ├── risk/
│   │   ├── rule_engine.py          # Configurable rule-based scorer
│   │   └── risk_calculator.py      # Aggregate risk score computation
│   │
│   └── ai/                         # ← Planned AI modules
│       ├── shap_explainer.py       # SHAP-based transaction explanations
│       ├── behavioral_profile.py   # Spending DNA + Circadian detection
│       ├── stress_index.py         # Financial Stress Index (FSI)
│       ├── forensic_report.py      # LLM auto-report generation
│       └── cashflow_forecast.py    # Time-series balance prediction
│
├── data/
│   └── sample/
│       └── bank_statements.csv     # Sample dataset (985 rows, Jul 2023–May 2024)
│
└── screenshots/
    ├── 01_upload_data.png
    ├── 02_raw_data_preview.png
    ├── 03_cleaned_data_preview.png
    ├── 04_analytics_dashboard.png
    ├── 05_merchants_volume.png
    ├── 06_monthly_trend.png
    └── 07_risk_analysis.png
```

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.10 or higher
- pip

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/automated-bank-analyzer.git
cd automated-bank-analyzer
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

### requirements.txt
```
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.26.0
plotly>=5.18.0
python-dateutil>=2.8.0
```

---

## 📖 Usage Guide

### Step 1 — Upload Your Bank Statement
Navigate to **Upload Data** in the sidebar. Click **Upload** and select your CSV file (up to 200MB).

The platform accepts any CSV with these columns in any naming variation:

| Required Data | Accepted Column Names |
|---|---|
| Transaction Date | `Date`, `valueDate`, `TransactionDate` |
| Debit/Credit Type | `type`, `Debit/Credit`, `Transaction Type` |
| Amount | `amount`, `Amount`, `Withdrawal`, `Deposit` |
| Running Balance | `currentBalance`, `Balance`, `Closing Balance` |
| Transaction Mode | `mode`, `Mode`, `Narration` |
| Merchant / Reference | `narration`, `Description`, `Remarks` |

### Step 2 — Review Cleaned Data
After upload, switch to **Upload Data → Cleaned Preview** to verify 985 rows were loaded correctly and all columns were standardized.

### Step 3 — Explore the Dashboard
Navigate to **Dashboard** to see:
- Full key metrics panel
- Top 10 merchants by spend
- Daily transaction volume timeline
- Monthly spending trend

### Step 4 — Run Risk Analysis
Navigate to **Risk Analysis** to:
- Adjust the **High-Value Transaction Threshold** using the ₹ slider
- View the computed **Overall Risk Score** and **Risk Level**
- See how many transactions were flagged
- Expand **Risk Rules Applied** to see the rule breakdown

---

## 📂 Data Format

### Sample Input (Raw CSV)
```
type,mode,amount,currentBalance,transactionTimestamp,valueDate,txnId,narration
DEBIT,CARD,100,2180.8,2023-06-27T09:40:19+05:30,2023-06-27,6e80ee9f-...,GAS FILLING
DEBIT,UPI,1200,2624.8,2023-08-23T08:17:48+05:30,2023-08-23,fd9c35d1-...,UPI/3235
CREDIT,UPI,3000,3524.8,2023-08-22T11:49:13+05:30,2023-08-22,b87c4941-...,UPI/3234
```

### Sample Output (Standardized)
```
debit_credit,transaction_type,amount,balance,transactionTimestamp,date,txnId
DEBIT,CARD,100,2180.8,2023-06-27 04:10:19+00:00,2023-06-27,6e80ee9f-...
DEBIT,UPI,1200,2624.8,2023-08-23 02:47:48+00:00,2023-08-23,fd9c35d1-...
CREDIT,UPI,3000,3524.8,2023-08-22 06:19:13+00:00,2023-08-22,b87c4941-...
```

---

## 🔮 Future Work

| Priority | Feature | Status |
|---|---|---|
| 🔴 High | SHAP-Based Transaction Explanations | Planned |
| 🔴 High | Spending DNA Fingerprint (per-user behavioral profile) | Planned |
| 🔴 High | Auto-Generated Forensic Report (LLM) | Planned |
| 🟡 Medium | Confidence Corridors (uncertainty bands) | Planned |
| 🟡 Medium | Circadian Rhythm Violation Detection | Planned |
| 🟡 Medium | Financial Stress Index (FSI) | Planned |
| 🟡 Medium | Cash Flow Prediction Engine | Planned |
| 🟢 Low | PDF & scanned image ingestion (OCR) | Future |
| 🟢 Low | Multi-account comparison view | Future |
| 🟢 Low | SAR / Regulatory report auto-filing | Future |
| 🟢 Low | Federated anomaly learning across branches | Future |

---

## 🔒 Privacy & Security

- No transaction data is stored on any server — all processing happens **in-memory** during the session
- No data is transmitted to third parties
- Session state is cleared on browser close
- Future LLM report generation will use anonymized, PII-masked data before API calls

---

## 📄 License

This project is developed as part of an academic research initiative.

---

## 👥 Authors

**Automated Bank Statement Analysis Team · 2026**

> *"Making financial forensics accessible, explainable, and evidence-ready."*
