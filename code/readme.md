# 🏦 Bank Statement Analysis Platform

A Streamlit-based college project for analyzing bank statements,
visualizing spending patterns, and detecting suspicious transactions
using rule-based risk assessment.

---

## 📁 Folder Structure

```
bank_analysis/
├── app.py              # Main Streamlit application
├── analytics.py        # Data cleaning + chart functions
├── risk_engine.py      # Rule-based risk detection engine
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

## ⚙️ Setup & Run

### 1. Clone or download the project
```bash
git clone https://github.com/yourname/bank_analysis.git
cd bank_analysis
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Activate — Mac/Linux
source venv/bin/activate

# Activate — Windows
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
streamlit run app.py
```

### 5. Open in browser
```
http://localhost:8501
```

---

## 📋 Expected CSV Format

Your bank statement CSV should have columns like these
(exact names are auto-detected):

| Column | Example Values |
|--------|---------------|
| Date | 2024-01-15 |
| Debit/Credit | DEBIT / CREDIT |
| Amount | 5000 |
| Balance | 95000 |
| Transaction Type | UPI, NEFT, ATM, CHQ |
| Merchant/Place | Swiggy, Amazon, Salary |

> Column names don't need to match exactly —
> the cleaner auto-detects common variations.

---

## 🖥️ Pages

### 📤 Upload Data
- Upload any bank statement CSV
- Preview raw data
- See row count, missing values, column types
- Auto-cleans and stores data for analysis

### 📊 Dashboard
- Key metrics (total debit, credit, avg transaction)
- Debit vs Credit bar chart
- Transaction type pie chart
- Top merchants by spend
- Daily transaction volume line chart
- Monthly spending trend

### ⚠️ Risk Analysis
- Configurable high-value threshold slider
- Overall risk score (0–100)
- Risk level: 🟢 Low / 🟡 Medium / 🔴 High
- Flagged transactions table with reasons
- Download flagged transactions as CSV

---

## 🔍 Risk Rules

| Rule | Trigger | Points |
|------|---------|--------|
| High-Value Transaction | Amount > threshold | 30 |
| Repeated Amount | Same amount 3+ times | 20 |
| Spending Spike | Amount > mean + 2σ | 25 |
| Multiple Same-Day Txns | 5+ txns on one day | 15 |
| Excessive Debits | Debits > 80% of total | 10 |

**Risk Score Levels:**
- 🟢 0–30 → Low Risk
- 🟡 31–60 → Medium Risk
- 🔴 61–100 → High Risk

---

## 🛠️ Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Core language |
| Streamlit | Web UI framework |
| Pandas | Data processing |
| NumPy | Statistical calculations |
| Plotly | Interactive charts |

---

## 📌 Notes

- No login or authentication required
- No database — all data lives in session state
- No external APIs used
- Works fully offline after install

---

## 👨‍💻 Author

**Your Name**
College Name · Department · 2024