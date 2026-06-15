"""
unified_fraud_engine.py
============================================================
Unified Banking Fraud Detection Engine
Combines Rule-Based and Machine Learning Fraud Scopes.
============================================================
"""

from __future__ import annotations

import os
import sys
import re
import json
import logging
import warnings
import argparse
from typing import Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, average_precision_score,
    f1_score, precision_score, recall_score
)

# Set up logging
logger = logging.getLogger("unified_fraud_engine")
warnings.filterwarnings("ignore")

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    logger.warning("xgboost is not installed. Will fall back to rules-only/unsupervised scoring where applicable.")

try:
    from imblearn.over_sampling import SMOTE
    HAS_SMOTE = True
except ImportError:
    HAS_SMOTE = False
    logger.warning("imbalanced-learn is not installed. SMOTE will be skipped in training.")

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False
    logger.warning("shap is not installed. SHAP explanations will be skipped.")


# ===========================================================================
# 2. CONFIG DATACLASS
# ===========================================================================

@dataclass
class EngineConfig:
    # Directories
    MODELS_DIR: str = "models"
    RESULTS_DIR: str = "results"

    # Rule 1: High Value
    HIGH_VALUE_MULTIPLIER: float = 5.0
    HIGH_VALUE_FLOOR: float = 5_000.0

    # Rule 2: Spending Spike
    SPENDING_SPIKE_MIN_DAYS: int = 7
    SPENDING_SPIKE_MULTIPLIER: float = 4.0
    SPENDING_SPIKE_FLOOR: float = 10_000.0

    # Rule 3: Repeated Transactions
    REPEATED_MIN_COUNT: int = 3
    REPEATED_WINDOW_HOURS: int = 24
    REPEATED_AMOUNT_TOLERANCE: float = 0.02

    # Rule 4: Excessive Withdrawal
    EXCESSIVE_WITHDRAWAL_THRESHOLD: int = 4
    WITHDRAWAL_KEYWORDS: set[str] = field(default_factory=lambda: {
        "atm", "cash", "withdrawal", "cash wdl",
        "cashout", "cdm", "pos cash", "wdrawal", "wdrl",
    })

    # Rule 5: Rapid Transactions
    RAPID_WINDOW_MINUTES: int = 10
    RAPID_BURST_THRESHOLD: int = 5

    # Rule 6: Late Night Transactions
    LATE_NIGHT_START_HOUR: int = 23
    LATE_NIGHT_END_HOUR: int = 5
    LATE_NIGHT_MIN_AMOUNT: float = 2_000.0

    # Rule 7: Balance Drop Alert
    BALANCE_DROP_PCT_THRESHOLD: float = 0.40

    # Rule Points
    RULE_POINTS: dict[str, int] = field(default_factory=lambda: {
        "HIGH_VALUE_TRANSACTION": 15,
        "SPENDING_SPIKE": 10,
        "REPEATED_TRANSACTION": 10,
        "EXCESSIVE_WITHDRAWAL": 15,
        "RAPID_TRANSACTION": 10,
        "LATE_NIGHT_TRANSACTION": 10,
        "BALANCE_DROP_ALERT": 15,
    })

    # ML Scorer Component Weights (must sum to 1.0)
    ML_WEIGHTS: dict[str, float] = field(default_factory=lambda: {
        "xgb_fraud_prob": 0.55,
        "rf_confirmation": 0.15,
        "velocity": 0.15,
        "spending_dev": 0.10,
        "time_context": 0.05,
    })

    # ML Calibration
    CALIBRATION_K: float = 0.12
    CALIBRATION_STRETCH_WEIGHT: float = 0.70
    CALIBRATION_RAW_WEIGHT: float = 0.30

    # Fusion Layer Constants
    FUSION_BOOST_WEIGHT: float = 0.15


# Instantiated global config
CONFIG = EngineConfig()



# ===========================================================================
# 3. RISK CATEGORIES & HELPERS
# ===========================================================================

RISK_CATEGORIES = [
    (0,  20,  "Very Low",   "✅",  "Normal transaction — no significant risk signals"),
    (21, 40,  "Low",        "🟡",  "Minor anomaly detected — monitor if pattern repeats"),
    (41, 60,  "Medium",     "🟠",  "Multiple weak signals — consider manual review"),
    (61, 80,  "High",       "🔴",  "Strong fraud indicators — flag for investigation"),
    (81, 95,  "Very High",  "🚨",  "High-confidence fraud — immediate review required"),
    (96, 100, "Critical",   "☠",   "Extreme fraud signals — block and investigate now"),
]

def get_risk_category(score: float) -> tuple[str, str, str]:
    """
    Map a numeric risk score (0-100) to a category name, icon, and description.
    """
    for lo, hi, label, icon, desc in RISK_CATEGORIES:
        if lo <= score <= hi:
            return label, icon, desc
    return "Critical", "☠", "Score out of range"


# Known Column Maps for Datasets
ARYAN_COLS = {
    "amount"          : "amount",
    "timestamp"       : "timestamp",
    "txn_type"        : "transaction_type",
    "merchant"        : "merchant_category",
    "channel"         : "payment_channel",
    "label"           : "is_fraud",
    "fraud_type_col"  : "fraud_type",
    "anomaly_score"   : "anomaly_score",
    "device"          : "device_used",
    "detect"          : lambda df: "fraud_type" in df.columns and "sender_account" in df.columns
}

VALA_COLS = {
    "amount"          : "TransactionAmount",
    "timestamp"       : "TransactionDate",
    "txn_type"        : "TransactionType",
    "merchant"        : "MerchantID",
    "channel"         : "Channel",
    "balance_after"   : "AccountBalance",
    "label"           : "IsFraudulent",
    "fraud_type_col"  : None,
    "anomaly_score"   : None,
    "device"          : "DeviceUsed",
    "detect"          : lambda df: "IsFraudulent" in df.columns and "MerchantID" in df.columns
}

FRAUD_TYPE_LABELS = {
    0: "Normal",
    1: "Money Laundering",
    2: "Account Takeover",
    3: "Card Fraud",
    4: "Smurfing / Structuring",
    5: "Phishing / Social Engineering",
}

FEATURE_COLS = [
    "amount", "log_amount",
    "hour", "day_of_week", "is_weekend", "month",
    "is_night",
    "is_early_morning",
    "is_round_amount",
    "is_near_threshold",
    "is_large_amount",
    "balance_before", "balance_after",
    "balance_delta", "balance_utilization",
    "balance_zeroed_out",
    "amount_to_balance_ratio",
    "merchant_encoded", "channel_encoded", "txn_type_encoded",
    "anomaly_score_raw",
]

def _calibrate_score(raw: float | np.ndarray) -> float | np.ndarray:
        """Shared sigmoid calibration used by both MLScorer and FusionLayer."""
        k = CONFIG.CALIBRATION_K
        stretched = 100.0 / (1.0 + np.exp(-k * (raw - 50.0)))
        calibrated = CONFIG.CALIBRATION_STRETCH_WEIGHT * stretched + CONFIG.CALIBRATION_RAW_WEIGHT * raw
        return np.clip(calibrated, 0.0, 100.0)

# ===========================================================================
# 4. ENGINEER FEATURES STANDALONE FUNCTION
# ===========================================================================

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes and engineers derived features for both rules and ML.
    Guarantees all 10 derived columns are present and created exactly once.
    """
    df = df.copy()

    # 1. Map 'amount'
    if "amount" not in df.columns:
        for c in ["Amount", "TransactionAmount", "amt", "Transaction Amount"]:
            if c in df.columns:
                df["amount"] = df[c]
                break
    if "amount" not in df.columns:
        df["amount"] = 0.0
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    # 2. Map 'date' and 'time'
    date_dt = None
    for c in ["transactionTimestamp", "date", "timestamp", "Date", "TransactionDate", "Transaction Date"]:
        if c in df.columns:
            date_dt = pd.to_datetime(df[c], errors="coerce")
            break
    
    if date_dt is None or date_dt.isna().all():
        date_dt = pd.Series([pd.Timestamp.now()] * len(df), index=df.index)

    df["date"] = date_dt

    if "time" not in df.columns:
        for c in ["Time", "transactionTimestamp", "timestamp", "date", "Date", "TransactionDate"]:
            if c in df.columns:
                try:
                    ts = pd.to_datetime(df[c], errors="coerce")
                    df["time"] = ts.dt.strftime("%H:%M:%S").fillna("12:00:00")
                except Exception:
                    df["time"] = "12:00:00"
                break
    if "time" not in df.columns:
        df["time"] = "12:00:00"
    df["time"] = df["time"].astype(str).fillna("12:00:00")

    # Extract date parts
    df["hour"] = date_dt.dt.hour.fillna(12).astype(int)
    df["day_of_week"] = date_dt.dt.dayofweek.fillna(0).astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["month"] = date_dt.dt.month.fillna(1).astype(int)

    # 3. Map 'balance_after'
    if "balance_after" not in df.columns:
        for c in ["balance", "currentBalance", "Balance", "AccountBalance", "Account Balance"]:
            if c in df.columns:
                df["balance_after"] = df[c]
                break
    if "balance_after" not in df.columns:
        df["balance_after"] = df["amount"] * 5
    df["balance_after"] = pd.to_numeric(df["balance_after"], errors="coerce").fillna(0.0)

    if "balance" not in df.columns:
        df["balance"] = df["balance_after"]

    # 4. Map categoricals and raw encodings
    if "merchant" not in df.columns:
        for c in ["Merchant", "MerchantID", "merchant_category", "narration", "description"]:
            if c in df.columns:
                df["merchant"] = df[c]
                break
    if "mode" not in df.columns and "transaction_type" in df.columns:
        df["mode"] = df["transaction_type"]
    df["merchant"] = df["merchant"].fillna("UNKNOWN").astype(str)

    if "narration" not in df.columns:
        for c in ["narration", "description", "Merchant", "merchant"]:
            if c in df.columns:
                df["narration"] = df[c]
                break
    if "narration" not in df.columns and "merchant" in df.columns:
        df["narration"] = df["merchant"]
    df["narration"] = df["narration"].fillna("UNKNOWN").astype(str)

    if "mode" not in df.columns:
        for c in ["mode", "Channel", "payment_channel", "TransactionType", "type", "transaction_type"]:
            if c in df.columns:
                df["mode"] = df[c]
                break
    if "mode" not in df.columns:
        df["mode"] = "UNKNOWN"
    df["mode"] = df["mode"].fillna("UNKNOWN").astype(str)

    if "transaction_type" not in df.columns:
        for c in ["transaction_type", "TransactionType", "txn_type", "type", "mode"]:
            if c in df.columns:
                df["transaction_type"] = df[c]
                break
    if "transaction_type" not in df.columns:
        df["transaction_type"] = "DEBIT"
    df["transaction_type"] = df["transaction_type"].fillna("DEBIT").astype(str)

    if "debit_credit" not in df.columns:
        for c in ["debit_credit", "debit/credit", "type"]:
            if c in df.columns:
                df["debit_credit"] = df[c]
                break
    if "debit_credit" not in df.columns:
        df["debit_credit"] = "DEBIT"
    df["debit_credit"] = df["debit_credit"].fillna("DEBIT").astype(str)

    # Encodings
    for col_out, src in [
        ("merchant_encoded", "merchant"),
        ("channel_encoded", "mode"),
        ("txn_type_encoded", "transaction_type"),
    ]:
        if src in df.columns:
            df[col_out] = LabelEncoder().fit_transform(df[src].astype(str).fillna("UNK"))
        else:
            df[col_out] = 0

    if "anomaly_score_raw" not in df.columns:
        if "anomaly_score" in df.columns:
            df["anomaly_score_raw"] = pd.to_numeric(df["anomaly_score"], errors="coerce").fillna(0.0)
        else:
            df["anomaly_score_raw"] = 0.0

    # 5. Compute the 10 derived columns
    df["log_amount"] = np.log1p(df["amount"])
    df["is_night"] = ((df["hour"] >= 23) | (df["hour"] <= 5)).astype(int)
    df["is_early_morning"] = ((df["hour"] >= 0) & (df["hour"] <= 6)).astype(int)
    df["is_round_amount"] = ((df["amount"] % 1000) == 0).astype(int)
    df["is_near_threshold"] = ((df["amount"] >= 9000) & (df["amount"] <= 9999)).astype(int)
    
    p95 = df["amount"].quantile(0.95)
    if pd.isna(p95):
        p95 = 10000.0
    df["is_large_amount"] = (df["amount"] > p95).astype(int)

   # For debits: balance_before = balance_after + amount
   # For credits: balance_before = balance_after - amount
    is_credit = df["debit_credit"].str.upper().str.strip().isin({"CREDIT", "CR", "C"})
    df["balance_before"] = np.where(
        is_credit,
        df["balance_after"] - df["amount"],
        df["balance_after"] + df["amount"]
    )
    df["balance_zeroed_out"] = (df["balance_after"] <= 0).astype(int)
    df["amount_to_balance_ratio"] = (df["amount"] / (df["balance_before"] + 1)).clip(upper=10)
    df["balance_utilization"] = (df["amount"] / (df["balance_before"] + 1)).clip(upper=10)
    df["balance_delta"] = df["balance_before"] - df["balance_after"]

    # Fill any missing feature columns with 0.0
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0

    return df


# ===========================================================================
# 5. DATASET LOADER CLASS
# ===========================================================================

class DatasetLoader:
    """
    Loads raw banking datasets and maps them to a unified format.
    """
    def load(self, filepath: str, sample: Optional[int] = None) -> tuple[pd.DataFrame, str]:
        print(f"\n{'='*55}")
        print(f"  Loading: {os.path.basename(filepath)}")
        print(f"{'='*55}")

        df = pd.read_csv(filepath, low_memory=False)
        print(f"  Rows   : {len(df):,}")
        print(f"  Cols   : {list(df.columns)}")

        if sample and sample < len(df):
            df = df.sample(sample, random_state=42).reset_index(drop=True)
            print(f"  Sampled: {len(df):,} rows")

        # Detect dataset format
        if ARYAN_COLS["detect"](df):
            name = "aryan208"
            print("  Dataset: aryan208 (financial_fraud_detection_dataset)")
            unified = self._map(df, ARYAN_COLS)
        elif VALA_COLS["detect"](df):
            name = "valakhorasani"
            print("  Dataset: valakhorasani (bank_transactions_data_2)")
            unified = self._map(df, VALA_COLS)
        else:
            name = "unknown"
            print("  Dataset: unknown format - using generic mapping")
            unified = self._generic(df)

        fraud_n = unified["is_fraud"].sum()
        print(f"\n  Fraud   : {fraud_n:,} / {len(unified):,}  ({fraud_n/len(unified)*100:.2f}%)")
        return unified, name

    def _map(self, df: pd.DataFrame, cols: dict) -> pd.DataFrame:
        out = pd.DataFrame()
        out["amount"] = pd.to_numeric(df[cols["amount"]], errors="coerce").fillna(0)
        out["is_fraud"] = pd.to_numeric(df[cols["label"]], errors="coerce").fillna(0).astype(int)

        if cols.get("fraud_type_col") and cols["fraud_type_col"] in df.columns:
            le_ft = LabelEncoder()
            ft_raw = df[cols["fraud_type_col"]].astype(str).fillna("Normal")
            ft_encoded = le_ft.fit_transform(ft_raw)
            out["fraud_type_label"] = np.where(out["is_fraud"] == 0, 0, ft_encoded + 1)
            self._fraud_type_classes = {i+1: cls for i, cls in enumerate(le_ft.classes_)}
            self._fraud_type_classes[0] = "Normal"
        else:
            out["fraud_type_label"] = out["is_fraud"].astype(int)
            self._fraud_type_classes = FRAUD_TYPE_LABELS

        if cols.get("timestamp") and cols["timestamp"] in df.columns:
            ts = pd.to_datetime(df[cols["timestamp"]], errors="coerce")
            out["date"] = ts
            out["time"] = ts.dt.strftime("%H:%M:%S").fillna("12:00:00")
            out["hour"] = ts.dt.hour.fillna(12).astype(int)
            out["day_of_week"] = ts.dt.dayofweek.fillna(0).astype(int)
            out["is_weekend"] = (out["day_of_week"] >= 5).astype(int)
            out["month"] = ts.dt.month.fillna(1).astype(int)
        else:
            out["date"] = pd.Series([pd.Timestamp.now()] * len(df), index=df.index)
            out["time"] = "12:00:00"
            out["hour"] = 12
            out["day_of_week"] = 0
            out["is_weekend"] = 0
            out["month"] = 1

        if cols.get("balance_after") and cols["balance_after"] in df.columns:
            out["balance_after"] = pd.to_numeric(df[cols["balance_after"]], errors="coerce").fillna(0)
        else:
            out["balance_after"] = out["amount"] * 5

        out["balance_before"] = out["balance_after"] + out["amount"]

        if cols.get("merchant") and cols["merchant"] in df.columns:
            out["merchant"] = df[cols["merchant"]].astype(str)
        else:
            out["merchant"] = "UNKNOWN"

        if cols.get("channel") and cols["channel"] in df.columns:
            out["mode"] = df[cols["channel"]].astype(str)
        else:
            out["mode"] = "UNKNOWN"

        if cols.get("txn_type") and cols["txn_type"] in df.columns:
            out["transaction_type"] = df[cols["txn_type"]].astype(str)
        else:
            out["transaction_type"] = "DEBIT"

        out["narration"] = out["merchant"]
        out["debit_credit"] = "DEBIT"

        for out_col, src_col in [
            ("merchant_encoded", cols.get("merchant")),
            ("channel_encoded",  cols.get("channel")),
            ("txn_type_encoded", cols.get("txn_type")),
        ]:
            if src_col and src_col in df.columns:
                out[out_col] = LabelEncoder().fit_transform(df[src_col].astype(str).fillna("UNK"))
            else:
                out[out_col] = 0

        if cols.get("anomaly_score") and cols["anomaly_score"] in df.columns:
            out["anomaly_score_raw"] = pd.to_numeric(df[cols["anomaly_score"]], errors="coerce").fillna(0.0)
        else:
            out["anomaly_score_raw"] = 0.0

        return out

    def _generic(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame()
        out["amount"] = pd.to_numeric(df.get("amount", df.get("Amount", pd.Series([0]*len(df)))), errors="coerce").fillna(0)
        for lbl in ["is_fraud", "isFraud", "IsFraudulent", "Class", "fraud"]:
            if lbl in df.columns:
                out["is_fraud"] = pd.to_numeric(df[lbl], errors="coerce").fillna(0).astype(int)
                break
        else:
            out["is_fraud"] = 0

        out["fraud_type_label"] = out["is_fraud"]
        
        for tc in ["timestamp", "transactionTimestamp", "date", "Date", "TransactionDate"]:
            if tc in df.columns:
                ts = pd.to_datetime(df[tc], errors="coerce")
                out["date"] = ts
                out["time"] = ts.dt.strftime("%H:%M:%S").fillna("12:00:00")
                out["hour"] = ts.dt.hour.fillna(12).astype(int)
                out["day_of_week"] = ts.dt.dayofweek.fillna(0).astype(int)
                out["is_weekend"] = (out["day_of_week"] >= 5).astype(int)
                out["month"] = ts.dt.month.fillna(1).astype(int)
                break
        else:
            out["date"] = pd.Series([pd.Timestamp.now()] * len(df), index=df.index)
            out["time"] = "12:00:00"
            out["hour"] = 12
            out["day_of_week"] = 0
            out["is_weekend"] = 0
            out["month"] = 1

        for bc in ["balance", "currentBalance", "Balance", "AccountBalance"]:
            if bc in df.columns:
                out["balance_after"] = pd.to_numeric(df[bc], errors="coerce").fillna(0)
                break
        else:
            out["balance_after"] = out["amount"] * 5

        out["balance_before"] = out["balance_after"] + out["amount"]
        out["merchant"] = "UNKNOWN"
        out["mode"] = "UNKNOWN"
        out["transaction_type"] = "DEBIT"
        out["narration"] = "UNKNOWN"
        out["debit_credit"] = "DEBIT"
        out["merchant_encoded"] = 0
        out["channel_encoded"] = 0
        out["txn_type_encoded"] = 0
        out["anomaly_score_raw"] = 0.0
        self._fraud_type_classes = FRAUD_TYPE_LABELS
        return out


# ===========================================================================
# 6. FRAUD MODEL TRAINER CLASS
# ===========================================================================

class FraudModelTrainer:
    """
    Trains and registers the ML models (Random Forest, XGBoost, Isolation Forest).
    """
    def __init__(self) -> None:
        self.rf = None
        self.xgb = None
        self.iso = None
        self.xgb_type = None
        self.scaler = StandardScaler()
        self.results = {}

    def train(self, df: pd.DataFrame, fraud_type_classes: dict[int, str]) -> dict[str, Any]:
        df = engineer_features(df)
        X = df[FEATURE_COLS].fillna(0.0)
        y = df["is_fraud"]
        y_type = df["fraud_type_label"]

        self._print_class_dist(y)
        X_bal, y_bal = self._balance(X, y)

        X_tr, X_te, y_tr, y_te = train_test_split(
            X_bal, y_bal, test_size=0.2, random_state=42, stratify=y_bal
        )
        X_tr_sc = self.scaler.fit_transform(X_tr)
        X_te_sc = self.scaler.transform(X_te)

        print(f"\n  Train : {len(X_tr):,}   Test : {len(X_te):,}")
        print("-"*55)

        # 1. Random Forest
        self._train_rf(X_tr, X_te, y_tr, y_te)
        # 2. XGBoost
        self._train_xgb(X_tr, X_te, y_tr, y_te)
        # 3. Isolation Forest
        self._train_iso(X_tr_sc, X_te_sc, y_tr, y_te)
        # 4. Multi-class XGBoost
        if y_type.nunique() > 2:
            self._train_fraud_type(X, y_type, fraud_type_classes)

        self._save(fraud_type_classes)
        return self.results

    def _train_rf(self, X_tr, X_te, y_tr, y_te):
        print("\n  [1/3] Random Forest")
        self.rf = RandomForestClassifier(
            n_estimators=200, max_depth=12,
            min_samples_leaf=5, class_weight="balanced",
            n_jobs=-1, random_state=42
        )
        self.rf.fit(X_tr, y_tr)
        prob = self.rf.predict_proba(X_te)
        proba = prob[:, 1] if prob.shape[1] > 1 else np.zeros(len(X_te))
        self.results["random_forest"] = self._eval(
            y_te, self.rf.predict(X_te), proba, "Random Forest"
        )

    def _train_xgb(self, X_tr, X_te, y_tr, y_te):
        if not HAS_XGB:
            return
        print("\n  [2/3] XGBoost (binary)")
        spw = int((y_tr == 0).sum()) / max(int((y_tr == 1).sum()), 1)
        self.xgb = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=spw, eval_metric="aucpr",
            random_state=42, n_jobs=-1, verbosity=0
        )
        self.xgb.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
        from sklearn.calibration import CalibratedClassifierCV
        self.xgb = CalibratedClassifierCV(self.xgb, cv=3, method='isotonic')
        self.xgb.fit(X_tr, y_tr)
        prob = self.xgb.predict_proba(X_te)
        proba = prob[:, 1] if prob.shape[1] > 1 else np.zeros(len(X_te))
        self.results["xgboost"] = self._eval(
            y_te, self.xgb.predict(X_te), proba, "XGBoost"
        )

    def _train_iso(self, X_tr_sc, X_te_sc, y_tr, y_te):
        print("\n  [3/3] Isolation Forest")
        contam = min(0.1, max(0.001, (y_tr == 1).sum() / len(y_tr)))
        self.iso = IsolationForest(
            n_estimators=200, contamination=contam,
            max_features=0.8, n_jobs=-1, random_state=42
        )
        normal_mask = (y_tr == 0)
        self.iso.fit(X_tr_sc[normal_mask])
        raw = self.iso.decision_function(X_te_sc)
        pred = (self.iso.predict(X_te_sc) == -1).astype(int)
        score = 1.0 - (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)
        self.results["isolation_forest"] = self._eval(y_te, pred, score, "Isolation Forest")

    def _train_fraud_type(self, X, y_type, fraud_type_classes):
        if not HAS_XGB:
            return
        print("\n  [+]  XGBoost Fraud TYPE classifier")
        self.xgb_type = xgb.XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.1,
            n_jobs=-1, random_state=42, verbosity=0,
            num_class=y_type.nunique(), objective="multi:softprob",
            eval_metric="mlogloss"
        )
        self.xgb_type.fit(X, y_type, verbose=False)

    def _eval(self, y_true, y_pred, y_proba, name):
        try:
            auc_roc = float(roc_auc_score(y_true, y_proba))
            auc_pr  = float(average_precision_score(y_true, y_proba))
        except Exception:
            auc_roc = auc_pr = 0.0
        f1   = float(f1_score(y_true, y_pred, zero_division=0))
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec  = float(recall_score(y_true, y_pred, zero_division=0))
        cm   = confusion_matrix(y_true, y_pred)
        tn, fp, fn, tp = cm.ravel() if cm.shape == (2,2) else (0,0,0,0)

        print(f"\n  [+] {name} Evaluation:")
        print(f"     AUC-PR    {auc_pr:.4f}")
        print(f"     AUC-ROC   {auc_roc:.4f}")
        print(f"     F1        {f1:.4f}   Precision {prec:.4f}   Recall {rec:.4f}")
        print(f"     TP={int(tp):,}  FP={int(fp):,}  FN={int(fn):,}  TN={int(tn):,}")
        print("  " + "-"*47)
        
        return dict(model=name, auc_pr=auc_pr, auc_roc=auc_roc,
                    f1=f1, precision=prec, recall=rec,
                    tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn))

    def _save(self, fraud_type_classes: dict[int, str]):
        if self.rf:
            joblib.dump(self.rf, os.path.join(CONFIG.MODELS_DIR, "random_forest.pkl"))
            feat_imp = dict(zip(FEATURE_COLS, self.rf.feature_importances_))
            joblib.dump(feat_imp, os.path.join(CONFIG.MODELS_DIR, "feature_importance.pkl"))
        if self.xgb:
            joblib.dump(self.xgb, os.path.join(CONFIG.MODELS_DIR, "xgboost.pkl"))
        if self.iso:
            joblib.dump(self.iso, os.path.join(CONFIG.MODELS_DIR, "isolation_forest.pkl"))
        if self.xgb_type:
            joblib.dump(self.xgb_type, os.path.join(CONFIG.MODELS_DIR, "xgboost_fraud_type.pkl"))
        joblib.dump(self.scaler, os.path.join(CONFIG.MODELS_DIR, "scaler.pkl"))
        joblib.dump(fraud_type_classes, os.path.join(CONFIG.MODELS_DIR, "fraud_type_classes.pkl"))

        with open(os.path.join(CONFIG.RESULTS_DIR, "training_results.json"), "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n  [OK] Models saved -> ./{CONFIG.MODELS_DIR}/")

    def _balance(self, X, y):
        fraud_n = int(y.sum())
        if HAS_SMOTE and fraud_n > 10:
            try:
                sm = SMOTE(random_state=42, k_neighbors=min(5, fraud_n - 1))
                Xr, yr = sm.fit_resample(X, y)
                return Xr, yr
            except Exception as e:
                logger.warning(f"SMOTE skipped: {e}")
        return X, y

    def _print_class_dist(self, y):
        n = len(y)
        f = int(y.sum())
        print(f"\n  Class distribution:")
        print(f"    Normal : {n-f:>10,}  ({(n-f)/n*100:.2f}%)")
        print(f"    Fraud  : {f:>10,}  ({f/n*100:.2f}%)")


# ===========================================================================
# 7. RULE ENGINE CLASS
# ===========================================================================

_TRAILING_ID_RE = re.compile(r"[/\s_-]?\d{4,}$")

def _safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()

def _has_time(df: pd.DataFrame) -> bool:
    if "time" not in df.columns:
        return False
    populated = df["time"].dropna()
    return not populated[populated.astype(str).str.strip() != ""].empty

def _resolve_merchant_key(merchant: Any, mode: Any, narration: Any) -> str | None:
    m = _safe_str(merchant)
    if m:
        return m.upper()
    mo = _safe_str(mode).upper()
    nar = _safe_str(narration).upper()
    nar = _TRAILING_ID_RE.sub("", nar).strip()
    if mo and nar:
        return f"{mo}::{nar}"
    if mo:
        return mo
    if nar:
        return nar
    return None

def _extract_channel(mode: Any, narration: Any) -> str:
    mo = _safe_str(mode).upper()
    if mo and mo not in ("", "OTHERS"):
        return mo
    nar = _safe_str(narration).upper()
    if nar:
        token = re.split(r"[/\s]", nar)[0]
        if token:
            return token
    return "UNKNOWN"


class RuleEngine:
    """
    Ported Rule-based Detection Engine with exactly 7 rules.
    """
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df.copy()
        self.n_rows = len(df)
        self._risk: dict[Any, dict[str, Any]] = {}
        self._counts: dict[str, int] = {flag: 0 for flag in CONFIG.RULE_POINTS}

        self._amounts = pd.to_numeric(self.df.get("amount", pd.Series(dtype=float)), errors="coerce")
        self._dates = pd.to_datetime(self.df.get("date", pd.Series(dtype="datetime64[ns]")), errors="coerce")
        self._balances = pd.to_numeric(
            self.df.get("balance", self.df.get("balance_after", pd.Series(dtype=float))),
            errors="coerce"
        )

        mode_col = self.df.get("mode", pd.Series("", index=self.df.index))
        narration_col = self.df.get("narration", pd.Series("", index=self.df.index))
        merchant_col = self.df.get("merchant", pd.Series("", index=self.df.index))

        self._channels = pd.Series(
            [_extract_channel(mode_col.get(i, ""), narration_col.get(i, "")) for i in self.df.index],
            index=self.df.index,
        )
        self._merchant_keys = pd.Series(
            [_resolve_merchant_key(merchant_col.get(i, ""), mode_col.get(i, ""), narration_col.get(i, "")) for i in self.df.index],
            index=self.df.index,
        )

    def _flag(self, idx: Any, flag_name: str, reason: str) -> None:
        if idx not in self._risk:
            self._risk[idx] = {"flags": [], "reasons": [], "score": 0}
        entry = self._risk[idx]
        if flag_name not in entry["flags"]:
            entry["flags"].append(flag_name)
            entry["reasons"].append(reason)
            entry["score"] += CONFIG.RULE_POINTS[flag_name]
            self._counts[flag_name] += 1

    def detect_high_value_transactions(self) -> None:
        flag = "HIGH_VALUE_TRANSACTION"
        work = pd.DataFrame({
            "amount": self._amounts,
            "channel": self._channels,
        }, index=self.df.index).dropna(subset=["amount"])

        if work.empty:
            return

        channel_medians: dict[str, float] = work.groupby("channel")["amount"].median().to_dict()
        for idx in self.df.index:
            amt = self._amounts.loc[idx] if idx in self._amounts.index else np.nan
            if pd.isna(amt):
                continue
            channel = self._channels.loc[idx] if idx in self._channels.index else "UNKNOWN"
            median_c = channel_medians.get(channel)
            if median_c is None or median_c == 0:
                continue

            threshold = CONFIG.HIGH_VALUE_MULTIPLIER * median_c
            if amt > threshold and amt > CONFIG.HIGH_VALUE_FLOOR:
                self._flag(
                    idx, flag,
                    f"Amount {amt:,.2f} exceeds {CONFIG.HIGH_VALUE_MULTIPLIER}x "
                    f"{channel} channel median ({median_c:,.2f}) "
                    f"and absolute floor ({CONFIG.HIGH_VALUE_FLOOR:,.0f})",
                )

    def detect_spending_spikes(self) -> None:
        flag = "SPENDING_SPIKE"
        unique_days = self._dates.dropna().dt.normalize().nunique()
        if unique_days < CONFIG.SPENDING_SPIKE_MIN_DAYS:
            return

        work = pd.DataFrame({
            "amount": self._amounts,
            "date": self._dates.dt.normalize(),
        }, index=self.df.index).dropna(subset=["date"])

        daily_totals = work.groupby("date")["amount"].sum()
        median_daily = daily_totals.median()
        threshold = CONFIG.SPENDING_SPIKE_MULTIPLIER * median_daily

        spike_dates = set(
            daily_totals[
                (daily_totals > threshold) & (daily_totals > CONFIG.SPENDING_SPIKE_FLOOR)
            ].index
        )

        for idx in self.df.index:
            d = self._dates.loc[idx] if idx in self._dates.index else pd.NaT
            if pd.isna(d):
                continue
            day = d.normalize()
            if day in spike_dates:
                self._flag(
                    idx, flag,
                    f"Daily spend {daily_totals[day]:,.2f} on {day.date()} "
                    f"exceeded {CONFIG.SPENDING_SPIKE_MULTIPLIER}× median daily spend "
                    f"({median_daily:,.2f}) and floor ({CONFIG.SPENDING_SPIKE_FLOOR:,.0f})",
                )

    def detect_repeated_transactions(self) -> None:
        flag = "REPEATED_TRANSACTION"
        work = pd.DataFrame({
            "key": self._merchant_keys,
            "amount": self._amounts,
            "date": self._dates,
        }, index=self.df.index).dropna(subset=["date", "amount"])
        work = work[work["key"].notna() & (work["key"] != "")]

        if work.empty:
            return

        work = work.sort_values("date")
        window_td = pd.Timedelta(hours=CONFIG.REPEATED_WINDOW_HOURS)

        for key, grp in work.groupby("key"):
            if len(grp) < CONFIG.REPEATED_MIN_COUNT:
                continue

            timestamps = grp["date"].tolist()
            amounts = grp["amount"].tolist()
            indices = grp.index.tolist()

            for i, (ts_i, amt_i, idx_i) in enumerate(zip(timestamps, amounts, indices)):
                similar = [
                    idx_j
                    for j, (ts_j, amt_j, idx_j) in enumerate(zip(timestamps, amounts, indices))
                    if i != j
                    and abs((ts_i - ts_j).total_seconds()) <= window_td.total_seconds()
                    and (
                        abs(amt_i - amt_j) / amt_i <= CONFIG.REPEATED_AMOUNT_TOLERANCE
                        if amt_i != 0 else amt_j == 0
                    )
                ]

                if len(similar) >= CONFIG.REPEATED_MIN_COUNT - 1:
                    self._flag(
                        idx_i, flag,
                        f"Key '{key}' with amount ~{amt_i:,.2f} repeated "
                        f"{len(similar)+1}x within {CONFIG.REPEATED_WINDOW_HOURS}h "
                        f"(+/- {CONFIG.REPEATED_AMOUNT_TOLERANCE*100:.0f}% tolerance)",
                    )

    def detect_excessive_withdrawals(self) -> None:
        flag = "EXCESSIVE_WITHDRAWAL"
        txn_type_col = self.df.get("transaction_type", pd.Series("", index=self.df.index))
        narration_col = self.df.get("narration", pd.Series("", index=self.df.index))

        def _is_withdrawal(idx: Any) -> bool:
            combined = (
                _safe_str(txn_type_col.get(idx, "")).lower()
                + " "
                + _safe_str(narration_col.get(idx, "")).lower()
            )
            return any(kw in combined for kw in CONFIG.WITHDRAWAL_KEYWORDS)

        is_withdrawal = pd.Series({idx: _is_withdrawal(idx) for idx in self.df.index})
        work = pd.DataFrame({
            "is_withdrawal": is_withdrawal,
            "date": self._dates.dt.normalize(),
        }, index=self.df.index)

        withdrawal_rows = work[work["is_withdrawal"] & work["date"].notna()]
        if withdrawal_rows.empty:
            return

        daily_counts = withdrawal_rows.groupby("date").size()
        flagged_dates = set(daily_counts[daily_counts >= CONFIG.EXCESSIVE_WITHDRAWAL_THRESHOLD].index)

        for idx in withdrawal_rows.index:
            day = withdrawal_rows.loc[idx, "date"]
            if day in flagged_dates:
                self._flag(
                    idx, flag,
                    f"{int(daily_counts[day])} withdrawals on {day.date()} "
                    f"(threshold: {CONFIG.EXCESSIVE_WITHDRAWAL_THRESHOLD})",
                )

    def detect_rapid_transactions(self) -> None:
        flag = "RAPID_TRANSACTION"
        if not _has_time(self.df):
            return

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

        if len(work) < CONFIG.RAPID_BURST_THRESHOLD:
            return

        work = work.sort_values("ts")
        ts_list = work["ts"].tolist()
        idx_list = work.index.tolist()
        window = pd.Timedelta(minutes=CONFIG.RAPID_WINDOW_MINUTES)

        for i, (ts_i, idx_i) in enumerate(zip(ts_list, idx_list)):
            count_in_window = sum(
                1 for ts_j in ts_list
                if abs((ts_i - ts_j).total_seconds()) <= window.total_seconds() / 2
            )
            if count_in_window >= CONFIG.RAPID_BURST_THRESHOLD:
                self._flag(
                    idx_i, flag,
                    f"{count_in_window} transactions within "
                    f"{CONFIG.RAPID_WINDOW_MINUTES}-minute window "
                    f"(threshold: {CONFIG.RAPID_BURST_THRESHOLD})",
                )

    def detect_late_night_transactions(self) -> None:
        flag = "LATE_NIGHT_TRANSACTION"
        if not _has_time(self.df):
            return

        for idx in self.df.index:
            amt = self._amounts.loc[idx] if idx in self._amounts.index else np.nan
            if pd.isna(amt) or amt < CONFIG.LATE_NIGHT_MIN_AMOUNT:
                continue

            t_raw = _safe_str(self.df.loc[idx].get("time", ""))
            if not t_raw:
                continue

            try:
                hour = int(t_raw.split(":")[0])
            except (ValueError, IndexError):
                continue

            is_night = (hour >= CONFIG.LATE_NIGHT_START_HOUR) or (hour < CONFIG.LATE_NIGHT_END_HOUR)
            if is_night:
                self._flag(
                    idx, flag,
                    f"Transaction of {amt:,.2f} at {t_raw} falls in "
                    f"late-night window "
                    f"({CONFIG.LATE_NIGHT_START_HOUR}:00-{CONFIG.LATE_NIGHT_END_HOUR}:00), "
                    f"min amount {CONFIG.LATE_NIGHT_MIN_AMOUNT:,.0f}",
                )

    def detect_balance_drop(self) -> None:
        flag = "BALANCE_DROP_ALERT"
        if self._balances.isna().all():
            return

        work = pd.DataFrame({
            "balance": self._balances,
            "amount": self._amounts,
            "date": self._dates.dt.normalize(),
            "ts": self._dates,
        }, index=self.df.index).dropna(subset=["date", "balance"])

        if work.empty:
            return

        opening_balance: dict[Any, float] = (
            work.sort_values("ts")
                .groupby("date")["balance"]
                .first()
                .to_dict()
        )

        for idx in work.index:
            amt = work.loc[idx, "amount"]
            day = work.loc[idx, "date"]
            opening = opening_balance.get(day)

            if pd.isna(amt) or opening is None or opening <= 0:
                continue

            drop_pct = amt / opening
            if drop_pct > CONFIG.BALANCE_DROP_PCT_THRESHOLD:
                self._flag(
                    idx, flag,
                    f"Transaction of {amt:,.2f} is {drop_pct*100:.1f}% of "
                    f"opening balance {opening:,.2f} on {day.date()} "
                    f"(threshold: {CONFIG.BALANCE_DROP_PCT_THRESHOLD*100:.0f}%)",
                )

    def run(self) -> tuple[pd.Series, pd.Series, pd.Series]:
        if not self.df.empty:
            self.detect_high_value_transactions()
            self.detect_spending_spikes()
            self.detect_repeated_transactions()
            self.detect_excessive_withdrawals()
            self.detect_rapid_transactions()
            self.detect_late_night_transactions()
            self.detect_balance_drop()

        scores = []
        flags = []
        reasons = []

        for idx in self.df.index:
            if idx in self._risk:
                scores.append(self._risk[idx]["score"])
                flags.append(self._risk[idx]["flags"])
                reasons.append(self._risk[idx]["reasons"])
            else:
                scores.append(0)
                flags.append([])
                reasons.append([])

        return (
            pd.Series(scores, index=self.df.index, dtype=int),
            pd.Series(flags, index=self.df.index, dtype=object),
            pd.Series(reasons, index=self.df.index, dtype=object)
        )


# ===========================================================================
# 8. ML SCORER CLASS
# ===========================================================================

class MLScorer:
    """
    Computes a 5-component ML-based risk score (0-100) using engineered features.
    """
    def __init__(self, model_dir: str = CONFIG.MODELS_DIR) -> None:
        self.model_dir = model_dir
        self.xgb = self._load("xgboost.pkl")
        self.rf = self._load("random_forest.pkl")
        self.iso = self._load("isolation_forest.pkl")
        self.scaler = self._load("scaler.pkl")
        self.xgb_type = self._load("xgboost_fraud_type.pkl")
        self.ft_map = self._load("fraud_type_classes.pkl") or FRAUD_TYPE_LABELS
    
        self.rules_only = not any([
            self.xgb,
            self.rf,
            self.iso
        ])

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        return _calibrate_score(raw)
    
    def _load(self, fname: str) -> Any:
        p = os.path.join(self.model_dir, fname)
        try:
            return joblib.load(p) if os.path.exists(p) else None
        except Exception as e:
            logger.warning(f"Failed to load model {fname}: {e}")
            return None

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        k = CONFIG.CALIBRATION_K
        stretched = 100.0 / (1.0 + np.exp(-k * (raw - 50.0)))
        calibrated = CONFIG.CALIBRATION_STRETCH_WEIGHT * stretched + CONFIG.CALIBRATION_RAW_WEIGHT * raw
        return np.clip(calibrated, 0.0, 100.0)

    def _get_xgb_prob(self, X: pd.DataFrame) -> np.ndarray:
        if self.xgb:
            prob = self.xgb.predict_proba(X)
            return prob[:, 1] if prob.shape[1] > 1 else np.zeros(len(X))
        return self._rule_fallback_prob(X)

    def _get_rf_prob(self, X: pd.DataFrame, xgb_prob: np.ndarray) -> np.ndarray:
        if self.rf:
            prob = self.rf.predict_proba(X)
            return prob[:, 1] if prob.shape[1] > 1 else xgb_prob
        return xgb_prob

    def _rule_fallback_prob(self, X: pd.DataFrame) -> np.ndarray:
        score = np.zeros(len(X))
        score += X.get("is_large_amount", pd.Series([0]*len(X))).values * 0.25
        score += X.get("is_night", pd.Series([0]*len(X))).values * 0.20
        score += X.get("balance_zeroed_out", pd.Series([0]*len(X))).values * 0.25
        score += X.get("is_near_threshold", pd.Series([0]*len(X))).values * 0.20
        score += X.get("is_round_amount", pd.Series([0]*len(X))).values * 0.10
        return np.clip(score, 0.0, 1.0)

    def _velocity_score(self, df: pd.DataFrame, X: pd.DataFrame) -> np.ndarray:
        if "velocity_score" in df.columns:
            v = pd.to_numeric(df["velocity_score"], errors="coerce").fillna(0.0).values
            return np.clip(v / (v.max() + 1e-9), 0.0, 1.0)

        if "date" in df.columns:
            ts = pd.to_datetime(df["date"], errors="coerce")
            diff = ts.diff().dt.total_seconds().fillna(3600.0)
            vel = np.where(diff < 60, 1.0,
                  np.where(diff < 300, 0.7,
                  np.where(diff < 900, 0.4,
                  np.where(diff < 3600, 0.2, 0.0))))
            return vel
        return X["is_near_threshold"].values.astype(float)

    def _spending_deviation(self, df: pd.DataFrame, X: pd.DataFrame) -> np.ndarray:
        if "spending_deviation_score" in df.columns:
            s = pd.to_numeric(df["spending_deviation_score"], errors="coerce").fillna(0.0).values
            return np.clip(s / (s.max() + 1e-9), 0.0, 1.0)

        geo = np.zeros(len(df))
        if "geo_anomaly_score" in df.columns:
            g = pd.to_numeric(df["geo_anomaly_score"], errors="coerce").fillna(0.0).values
            geo = np.clip(g / (g.max() + 1e-9), 0.0, 1.0)

        amt = X["amount"].values
        mean = np.mean(amt) if len(amt) > 0 else 0.0
        std = np.std(amt) + 1e-9 if len(amt) > 0 else 1.0
        z = np.abs((amt - mean) / std)
        z_norm = np.clip(z / 5.0, 0.0, 1.0)
        return np.clip((z_norm + geo) / 2.0, 0.0, 1.0)

    def _time_context_score(self, X: pd.DataFrame) -> np.ndarray:
        score = np.zeros(len(X))
        score += X["is_night"].values * 0.40
        score += X["is_early_morning"].values * 0.25
        score += X["is_round_amount"].values * 0.15
        score += X["is_near_threshold"].values * 0.20
        return np.clip(score, 0.0, 1.0)

    def _get_fraud_type(self, X: pd.DataFrame, scores: np.ndarray) -> list[str]:
        if self.xgb_type:
            preds = self.xgb_type.predict(X)
            return [
                self.ft_map.get(int(p), "Unknown Fraud")
                if scores[i] >= 41 else "Normal"
                for i, p in enumerate(preds)
            ]
        return self._heuristic_fraud_type(X, scores)

    def _heuristic_fraud_type(self, X: pd.DataFrame, scores: np.ndarray) -> list[str]:
        types = []
        for i, s in enumerate(scores):
            if s < 41:
                types.append("Normal")
                continue
            row = X.iloc[i]
            if row.get("is_near_threshold", 0):
                types.append("Smurfing / Structuring")
            elif row.get("is_early_morning", 0) and row.get("is_large_amount", 0):
                types.append("Account Takeover")
            elif row.get("balance_zeroed_out", 0):
                types.append("Account Draining")
            elif row.get("amount_to_balance_ratio", 0) > 2:
                types.append("Overdraft Fraud")
            elif row.get("is_large_amount", 0) and row.get("is_round_amount", 0):
                types.append("Money Laundering")
            elif row.get("is_night", 0):
                types.append("Unauthorized Access")
            else:
                types.append("General Fraud")
        return types

    def score(self, df: pd.DataFrame) -> dict[str, Any]:
        X = df[FEATURE_COLS].fillna(0.0)
        n = len(df)

        if self.rules_only:
            fallback_probs = self._rule_fallback_prob(X)
            calibrated_fallback = self._calibrate(fallback_probs * 100.0)
            return {
                "ml_score": calibrated_fallback,
                "xgb_component": fallback_probs * 27.5,
                "rf_component": fallback_probs * 7.5,
                "velocity_component": self._velocity_score(df, X) * 7.5,
                "spending_dev_component": self._spending_deviation(df, X) * 5.0,
                "time_context_component": self._time_context_score(X) * 2.5,
                "fraud_type": self._heuristic_fraud_type(X, calibrated_fallback),
                "fraud_probability": calibrated_fallback / 100.0,
                "shap_top_feature": ["N/A"] * n,
                "confidence_score": [1.0] * n,
            }

        xgb_prob = self._get_xgb_prob(X)
        c1 = xgb_prob * 55.0

        rf_prob = self._get_rf_prob(X, xgb_prob)
        agreement = 1.0 - np.abs(xgb_prob - rf_prob)
        c2 = rf_prob * agreement * 15.0

        if self.rf:
            tree_preds = np.array([t.predict_proba(X)[:, 1] for t in self.rf.estimators_])
            confidence = (1.0 - tree_preds.std(axis=0)).tolist()
        else:
            confidence = [1.0] * len(X)

        c3 = self._velocity_score(df, X) * 15.0
        c4 = self._spending_deviation(df, X) * 10.0
        c5 = self._time_context_score(X) * 5.0

        raw_score = c1 + c2 + c3 + c4 + c5
        calibrated = self._calibrate(raw_score)
        fraud_types = self._get_fraud_type(X, calibrated)

        if HAS_SHAP and self.xgb:
            try:
                exp = shap.TreeExplainer(self.xgb)
                sv = exp.shap_values(X)
                shap_top = [f"{X.columns[int(np.argmax(np.abs(sv[i])))]}" for i in range(len(X))]
            except Exception:
                shap_top = ["N/A"] * len(X)
        else:
            shap_top = ["N/A"] * len(X)

        return {
            "ml_score": calibrated,
            "xgb_component": c1,
            "rf_component": c2,
            "velocity_component": c3,
            "spending_dev_component": c4,
            "time_context_component": c5,
            "fraud_type": fraud_types,
            "fraud_probability": calibrated / 100.0,
            "shap_top_feature": shap_top,
            "confidence_score": confidence,
        }


# ===========================================================================
# 9. FUSION LAYER CLASS
# ===========================================================================

class FusionLayer:
    """
    Fuses ML risk scores with rule-based boost values and applies overrides/suppression.
    """
    def __init__(self, config: EngineConfig = CONFIG) -> None:
        self.config = config

    def _calibrate(self, raw: float) -> float:
        return float(_calibrate_score(raw))

    def fuse(self, ml_score: float, rule_flags: list[str], rules_only_mode: bool = False) -> dict[str, Any]:
        base_score = ml_score
        rule_points_map = self.config.RULE_POINTS
        fired_points = sorted([rule_points_map[flag] for flag in rule_flags if flag in rule_points_map], reverse=True)
        diminishing_sum = 0.0
        
        for idx, pts in enumerate(fired_points):
            if idx == 0:
                factor = 1.0
            elif idx == 1:
                factor = 0.50
            elif idx == 2:
                factor = 0.25
            else:
                factor = 0.10
            diminishing_sum += pts * factor

        rule_boost = min(diminishing_sum, 35.0)

        flags_set = set(rule_flags)
        hard_override_applied = False
        override_rule = None
        override_min_score = 0.0

        if {"BALANCE_DROP_ALERT", "RAPID_TRANSACTION", "LATE_NIGHT_TRANSACTION"}.issubset(flags_set):
            override_min_score = max(override_min_score, 75.0)
            hard_override_applied = True
            override_rule = "BALANCE_DROP_ALERT + RAPID_TRANSACTION + LATE_NIGHT_TRANSACTION"
        if {"EXCESSIVE_WITHDRAWAL", "RAPID_TRANSACTION"}.issubset(flags_set):
            override_min_score = max(override_min_score, 70.0)
            hard_override_applied = True
            override_rule = "EXCESSIVE_WITHDRAWAL + RAPID_TRANSACTION"
        if {"HIGH_VALUE_TRANSACTION", "LATE_NIGHT_TRANSACTION", "BALANCE_DROP_ALERT"}.issubset(flags_set):
            override_min_score = max(override_min_score, 80.0)
            hard_override_applied = True
            override_rule = "HIGH_VALUE_TRANSACTION + LATE_NIGHT_TRANSACTION + BALANCE_DROP_ALERT"
        if {"REPEATED_TRANSACTION", "RAPID_TRANSACTION"}.issubset(flags_set):
            override_min_score = max(override_min_score, 65.0)
            hard_override_applied = True
            override_rule = "REPEATED_TRANSACTION + RAPID_TRANSACTION"

        suppression_applied = False
        if len(rule_flags) == 1:
            fired_rule = rule_flags[0]
            if ml_score < 15.0 and fired_rule in ("LATE_NIGHT_TRANSACTION", "SPENDING_SPIKE"):
                rule_boost *= 0.2
                suppression_applied = True
            elif ml_score < 20.0:
                rule_boost *= 0.4
                suppression_applied = True

        if rules_only_mode:
            dominant = "RULES"
        else:
            if rule_boost > 8.0 and ml_score < 50.0:
                dominant = "RULES"
            elif ml_score > 60.0 and rule_boost < 5.0:
                dominant = "ML"
            else:
                dominant = "BOTH"

        raw_final = base_score + rule_boost
        if hard_override_applied:
            raw_final = max(raw_final, override_min_score)

        final_score = float(np.clip(raw_final, 0.0, 100.0))

        return {
            "final_score": final_score,
            "rule_boost": rule_boost,
            "hard_override_applied": hard_override_applied,
            "override_rule": override_rule,
            "suppression_applied": suppression_applied,
            "dominant_signal": dominant,
        }


# ===========================================================================
# 11. REPORT BUILDER CLASS
# ===========================================================================

class ReportBuilder:
    """
    Synthesizes portfolio summaries, attack episode clusters, and the LLM prompt.
    """
    def build_report(self, scored_df: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        total_tx = len(scored_df)
        flagged_df = scored_df[scored_df["final_risk_score"] >= 61.0].copy()
        flagged_count = len(flagged_df)
        flag_rate_pct = (flagged_count / total_tx * 100.0) if total_tx > 0 else 0.0
        total_amount_at_risk = float(flagged_df["amount"].sum()) if flagged_count > 0 else 0.0
        avg_final_risk_score = float(scored_df["final_risk_score"].mean()) if total_tx > 0 else 0.0
        max_final_risk_score = float(scored_df["final_risk_score"].max()) if total_tx > 0 else 0.0

        # Risk distribution
        risk_dist = {"Very Low": 0, "Low": 0, "Medium": 0, "High": 0, "Very High": 0, "Critical": 0}
        for cat in scored_df["risk_category"]:
            if cat in risk_dist:
                risk_dist[cat] += 1

        # Fraud type breakdown
        fraud_type_counts = flagged_df["fraud_type_predicted"].value_counts().to_dict()
        
        # Rule trigger counts
        rule_trigger_counts = {r: 0 for r in CONFIG.RULE_POINTS}
        for flags_list in scored_df["rule_flags"]:
            for flag in flags_list:
                if flag in rule_trigger_counts:
                    rule_trigger_counts[flag] += 1

        # Dominant signal counts
        dominant_signal_counts = {"ML": 0, "RULES": 0, "BOTH": 0}
        if flagged_count > 0:
            for sig in flagged_df["dominant_signal"]:
                if sig in dominant_signal_counts:
                    dominant_signal_counts[sig] += 1

        # Peak fraud hour
        peak_fraud_hour = -1
        if flagged_count > 0 and "hour" in flagged_df.columns:
            peak_fraud_hour = int(flagged_df["hour"].mode().iloc[0])

        # Peak fraud day
        peak_fraud_day = "None"
        if flagged_count > 0 and "date" in flagged_df.columns:
            try:
                days = pd.to_datetime(flagged_df["date"]).dt.day_name()
                if not days.empty:
                    peak_fraud_day = str(days.mode().iloc[0])
            except Exception:
                pass

        # Caught stats
        ml_only_caught = int((flagged_df["rule_flags"].apply(len) == 0).sum()) if flagged_count > 0 else 0
        rules_only_caught = int(((flagged_df["rule_flags"].apply(len) > 0) & (flagged_df["ml_score"] < 41.0)).sum()) if flagged_count > 0 else 0
        both_caught = int(((flagged_df["rule_flags"].apply(len) > 0) & (flagged_df["ml_score"] >= 41.0)).sum()) if flagged_count > 0 else 0

        portfolio_summary = {
            "total_transactions": int(total_tx),
            "flagged_count": int(flagged_count),
            "flag_rate_pct": float(flag_rate_pct),
            "total_amount_at_risk": float(total_amount_at_risk),
            "avg_final_risk_score": float(avg_final_risk_score),
            "max_final_risk_score": float(max_final_risk_score),
            "risk_distribution": risk_dist,
            "fraud_type_breakdown": fraud_type_counts,
            "rule_trigger_counts": rule_trigger_counts,
            "dominant_signal_counts": dominant_signal_counts,
            "peak_fraud_hour": peak_fraud_hour,
            "peak_fraud_day": peak_fraud_day,
            "ml_only_caught": ml_only_caught,
            "rules_only_caught": rules_only_caught,
            "both_caught": both_caught
        }

        # Episode timeline clustering
        episodes_list = []
        if flagged_count > 0:
            def combine_dt(row):
                try:
                    d = row["date"]
                    t = row["time"]
                    return pd.to_datetime(f"{d.date()} {t}")
                except Exception:
                    return pd.Timestamp.now()

            flagged_df["timestamp_full"] = flagged_df.apply(combine_dt, axis=1)
            flagged_df = flagged_df.sort_values("timestamp_full")

            episode_ids = []
            current_id = 1
            prev_ts = None

            for ts in flagged_df["timestamp_full"]:
                if prev_ts is not None:
                    if (ts - prev_ts) > pd.Timedelta(hours=24):
                        current_id += 1
                episode_ids.append(current_id)
                prev_ts = ts

            flagged_df["episode_id"] = episode_ids

            for ep_id, grp in flagged_df.groupby("episode_id"):
                grp = grp.sort_values("timestamp_full")
                first_ts = grp["timestamp_full"].iloc[0]
                last_ts = grp["timestamp_full"].iloc[-1]
                duration_min = (last_ts - first_ts).total_seconds() / 60.0

                rules_fired = set()
                for r_list in grp["rule_flags"]:
                    rules_fired.update(r_list)
                rules_fired_list = sorted(list(rules_fired))

                is_near_pct = (grp["is_near_threshold"] == 1).mean()
                bal_zeroed_any = (grp["balance_zeroed_out"] == 1).any()
                
                card_testing = False
                if len(grp) > 1:
                    first_amt = grp["amount"].iloc[0]
                    subsequent_amts = grp["amount"].iloc[1:]
                    if first_amt < 500 and (subsequent_amts > 5000).any():
                        card_testing = True

                fraud_types = grp["fraud_type_predicted"].value_counts()
                dominant_fraud_type = fraud_types.index[0] if not fraud_types.empty else "Normal"

                if is_near_pct > 0.50:
                    pattern = "Smurfing"
                elif bal_zeroed_any and duration_min < 30.0:
                    pattern = "Account Draining"
                elif len(grp) > 5 and duration_min < 20.0:
                    pattern = "Coordinated Burst"
                elif card_testing:
                    pattern = "Card Testing"
                elif duration_min > 1440.0 and grp["amount"].mean() < 2000.0:
                    pattern = "Slow Bleed"
                elif "LATE_NIGHT_TRANSACTION" in rules_fired and "HIGH_VALUE_TRANSACTION" in rules_fired:
                    pattern = "Account Takeover"
                else:
                    pattern = "Unknown Pattern"

                episodes_list.append({
                    "episode_id": int(ep_id),
                    "txn_count": int(len(grp)),
                    "total_amount": float(grp["amount"].sum()),
                    "duration_minutes": float(duration_min),
                    "avg_final_score": float(grp["final_risk_score"].mean()),
                    "max_final_score": float(grp["final_risk_score"].max()),
                    "dominant_fraud_type": str(dominant_fraud_type),
                    "rules_fired_in_episode": rules_fired_list,
                    "ml_avg_score": float(grp["ml_score"].mean()),
                    "rule_avg_score": float(grp["rule_score"].mean()),
                    "attack_pattern": pattern
                })

        top_episodes = sorted(episodes_list, key=lambda e: e["max_final_score"], reverse=True)[:3]

        # Select top 10 flagged transactions
        top_flagged = flagged_df.sort_values("final_risk_score", ascending=False).head(10)
        top_tx_evidence = []
        for idx, row in top_flagged.iterrows():
            tx_ev = {
                "transaction_index": idx,
                "date": str(row["date"]),
                "time": str(row["time"]),
                "amount": float(row["amount"]),
                "merchant": str(row["merchant"]),
                "mode": str(row["mode"]),
                "ml_score": float(row["ml_score"]),
                "rule_score": float(row["rule_score"]),
                "final_risk_score": float(row["final_risk_score"]),
                "risk_category": str(row["risk_category"]),
                "dominant_signal": str(row["dominant_signal"]),
                "combined_reason": str(row["combined_reason"]),
                "rule_flags": list(row["rule_flags"]),
                "rule_reasons": list(row["rule_reasons"]),
                "fraud_type_predicted": str(row["fraud_type_predicted"]),
                "fraud_probability": float(row["fraud_probability"])
            }
            top_tx_evidence.append(tx_ev)

        # Build prompt
        llm_prompt = f"""
You are an expert financial forensic analyst and fraud investigator.
Below is the output data from our Bank Fraud Detection System, consisting of three levels of context:
1. Portfolio Summary (macro level)
2. Episode Clusters (mid level, grouped timeline of attacks)
3. Top 10 Flagged Transactions (micro level evidence packets)

Please write a comprehensive, publication-quality narrative report based on this data.

### REPORT STRUCTURE TO FOLLOW:
1. EXECUTIVE SUMMARY: A high-level overview of the portfolio, flagging rate, risk distribution, and overall risk posture. Synthesize, do not just repeat the numbers. Explain the overall severity and risk.
2. PER-EPISODE ATTACK NARRATIVE: A narrative detail of the top attack episodes detected. Explain the attack patterns (e.g., Smurfing, Account Takeover, Account Draining) with causal reasoning of what the fraudster was attempting.
3. PER-TRANSACTION EXPLANATIONS: Deep-dive explanation for the top 10 flagged transactions. Discuss why they were flagged, the fusion of ML and Rule signals, and the dominant signal. Acknowledge uncertainty on medium scores.

---
### LEVEL 1: PORTFOLIO SUMMARY
{json.dumps(portfolio_summary, indent=2)}

---
### LEVEL 2: TOP 3 EPISODES OF ATTACK
{json.dumps(top_episodes, indent=2)}

---
### LEVEL 3: TOP 10 FLAGGED TRANSACTIONS WITH EVIDENCE
{json.dumps(top_tx_evidence, indent=2)}

---
### INSTRUCTIONS FOR YOUR ANALYSIS:
- SYNTHESIZE, DO NOT DESCRIBE: Connect the dots between episodes and transaction behaviors rather than just reciting lists of numbers.
- CAUSAL REASONING: Explain *how* and *why* these behaviors signal specific fraud types (e.g., why round amounts combined with late-night times point to money laundering or account takeover).
- PRIORITIZE BY RISK: Focus heaviest attention on Critical and High risk categories.
- ACKNOWLEDGE UNCERTAINTY: For medium/moderate scores, clearly state what additional context would be needed to make a definitive judgment.
"""

        return portfolio_summary, episodes_list, llm_prompt


# ===========================================================================
# 12. UNIFIED FRAUD ENGINE CLASS
# ===========================================================================

class UnifiedFraudEngine:
    """
    Main orchestrator for the unified fraud engine.
    """
    def __init__(self, model_dir: str = CONFIG.MODELS_DIR) -> None:
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(CONFIG.RESULTS_DIR, exist_ok=True)
        self.ml_scorer = MLScorer(model_dir=model_dir)
        self.fusion_layer = FusionLayer()

    def train(self, df: pd.DataFrame, fraud_type_classes: Optional[dict[int, str]] = None) -> dict[str, Any]:
        """
        Trains models and reloads components.
        """
        if fraud_type_classes is None:
            fraud_type_classes = FRAUD_TYPE_LABELS
        trainer = FraudModelTrainer()
        results = trainer.train(df, fraud_type_classes)
        self.ml_scorer = MLScorer(model_dir=self.model_dir)
        return results

    def run(self, df: pd.DataFrame) -> FraudResult:
        logger.info("UnifiedFraudEngine: starting pipeline run.")
        
        # Stage 1: Feature Engineering (called once)
        df_engineered = engineer_features(df)

        # Stage 2: Rule Engine
        rule_engine = RuleEngine(df_engineered)
        rule_scores, rule_flags, rule_reasons = rule_engine.run()

        # Stage 3: ML Scoring
        ml_results = self.ml_scorer.score(df_engineered)
        
        ml_scores = ml_results["ml_score"]
        xgb_comps = ml_results["xgb_component"]
        rf_comps = ml_results["rf_component"]
        vel_comps = ml_results["velocity_component"]
        spend_comps = ml_results["spending_dev_component"]
        time_comps = ml_results["time_context_component"]
        fraud_types = ml_results["fraud_type"]
        fraud_probs = ml_results["fraud_probability"]

        # Lists for Stage 7 columns
        final_risk_scores = []
        risk_categories = []
        risk_icons = []
        risk_descriptions = []
        rule_boosts_applied = []
        hard_overrides_applied = []
        suppressions_applied = []
        dominant_signals = []
        combined_reasons = []
        is_fraud_predicted_list = []

        for i, idx in enumerate(df_engineered.index):
            # Stage 4: Fusion Layer
            fused = self.fusion_layer.fuse(
                ml_score=ml_scores[i],
                rule_flags=rule_flags[idx],
                rules_only_mode=self.ml_scorer.rules_only
            )
            
            final_score = fused["final_score"]
            rule_boost = fused["rule_boost"]
            hard_override = fused["hard_override_applied"]
            suppression = fused["suppression_applied"]
            dominant = fused["dominant_signal"]

            cat, icon, desc = get_risk_category(final_score)

            # Combined Reason Field Logic
            if dominant == "BOTH":
                top_2 = rule_reasons[idx][:2]
                top_2_str = "; ".join(top_2) if top_2 else "no rule flags"
                combined_reason = f"ML model flagged as {fraud_types[i]} ({ml_scores[i]:.0f}/100) + Rules confirmed: {top_2_str}"
            elif dominant == "ML":
                components_list = [
                    ("XGBoost", xgb_comps[i], 55.0),
                    ("Random Forest", rf_comps[i], 15.0),
                    ("Velocity", vel_comps[i], 15.0),
                    ("Spending Deviation", spend_comps[i], 10.0),
                    ("Time Context", time_comps[i], 5.0)
                ]
                top_comp = max(components_list, key=lambda x: x[1])
                top_shap_or_component = f"dominant component: {top_comp[0]} ({top_comp[1]:.1f}/{top_comp[2]} pts)"
                
                rule_flags_str = ", ".join(rule_flags[idx]) if rule_flags[idx] else "no rule flags"
                combined_reason = f"ML model: {fraud_types[i]} — {top_shap_or_component}. Rules: {rule_flags_str}"
            else:  # dominant == "RULES"
                all_reasons_str = "; ".join(rule_reasons[idx]) if rule_reasons[idx] else "no rule flags"
                combined_reason = f"Rule-based flags: {all_reasons_str}. ML score below threshold ({ml_scores[i]:.0f}/100)"

            final_risk_scores.append(final_score)
            risk_categories.append(cat)
            risk_icons.append(icon)
            risk_descriptions.append(desc)
            rule_boosts_applied.append(rule_boost)
            hard_overrides_applied.append(hard_override)
            suppressions_applied.append(suppression)
            dominant_signals.append(dominant)
            combined_reasons.append(combined_reason)
            is_fraud_predicted_list.append(1 if final_score >= 61.0 else 0)

        # Stage 7: Assign Columns to scored DataFrame
        scored_df = df_engineered.copy()
        scored_df["rule_score"] = rule_scores
        scored_df["rule_flags"] = rule_flags
        scored_df["rule_reasons"] = rule_reasons
        scored_df["ml_score"] = ml_scores
        scored_df["score_xgb_component"] = xgb_comps
        scored_df["score_rf_component"] = rf_comps
        scored_df["score_velocity"] = vel_comps
        scored_df["score_spending_dev"] = spend_comps
        scored_df["score_time_context"] = time_comps
        scored_df["fraud_type_predicted"] = fraud_types
        scored_df["fraud_probability"] = fraud_probs
        scored_df["shap_top_feature"] = ml_results["shap_top_feature"]
        scored_df["confidence_score"] = ml_results["confidence_score"]
        scored_df["final_risk_score"] = final_risk_scores
        scored_df["risk_category"] = risk_categories
        scored_df["risk_icon"] = risk_icons
        scored_df["risk_description"] = risk_descriptions
        scored_df["rule_boost_applied"] = rule_boosts_applied
        scored_df["hard_override_applied"] = hard_overrides_applied
        scored_df["suppression_applied"] = suppressions_applied
        scored_df["dominant_signal"] = dominant_signals
        scored_df["combined_reason"] = combined_reasons
        scored_df["is_fraud_predicted"] = is_fraud_predicted_list

        # Attach engineered features for standard visibility
        for col in ["amount", "merchant", "mode", "date", "time", "hour", "day_of_week", "is_weekend", "month", "balance_before", "balance_after", "balance_delta", "balance_utilization", "balance_zeroed_out", "amount_to_balance_ratio", "is_night", "is_early_morning", "is_round_amount", "is_near_threshold", "is_large_amount"]:
            if col not in scored_df.columns:
                scored_df[col] = df_engineered[col]

        # Stage 6: Report Builder
        report_builder = ReportBuilder()
        portfolio_summary, episodes_list, llm_prompt = report_builder.build_report(scored_df)

        flagged_df = scored_df[scored_df["final_risk_score"] >= 61.0].sort_values("final_risk_score", ascending=False)

        return FraudResult(
            scored_df=scored_df,
            portfolio_summary=portfolio_summary,
            episodes=episodes_list,
            llm_prompt=llm_prompt,
            flagged_df=flagged_df
        )


# ===========================================================================
# 13. FRAUD RESULT DATACLASS
# ===========================================================================

@dataclass
class FraudResult:
    scored_df: pd.DataFrame
    portfolio_summary: dict[str, Any]
    episodes: list[dict[str, Any]]
    llm_prompt: str
    flagged_df: pd.DataFrame


# ===========================================================================
# 14. QUICK RUN FUNCTION
# ===========================================================================

def quick_run(df: pd.DataFrame) -> FraudResult:
    """
    Convenience function that loads models, runs the pipeline, and returns results.
    """
    engine = UnifiedFraudEngine()
    return engine.run(df)

# ===========================================================================
# 14b. APP.PY INTERFACE
# ===========================================================================

def run(df: pd.DataFrame, report: dict) -> dict:
    """
    Entry point called by app.py's step_optional_services().
    Merged into report["fraud"] by app.py.

    Converts FraudResult into a JSON-serializable dict matching the
    established output contract:
        {
            "summary":               { portfolio-level numbers },
            "flagged_transactions":  [ list of per-transaction dicts ],
            "episodes":              [ attack episode clusters ],
            "llm_prompt":            str
        }
    Also saves a standalone fraud_report.json for inspection.
    """
    engine = UnifiedFraudEngine()
    result = engine.run(df)

    # Serialize flagged transactions from flagged_df
    flagged_records = []
    for idx, row in result.flagged_df.iterrows():
        flagged_records.append({
            "transaction_index":    int(idx) if isinstance(idx, (int, float)) else str(idx),
            "date":                 str(row.get("date", "")),
            "time":                 str(row.get("time", "")),
            "merchant":             str(row.get("merchant", "")),
            "mode":                 str(row.get("mode", "")),
            "amount":               float(row["amount"]) if pd.notna(row.get("amount")) else None,
            "debit_credit":         str(row.get("debit_credit", "")),
            "rule_score":           int(row.get("rule_score", 0)),
            "ml_score":             float(row.get("ml_score", 0.0)),
            "final_risk_score":     float(row.get("final_risk_score", 0.0)),
            "risk_category":        str(row.get("risk_category", "")),
            "dominant_signal":      str(row.get("dominant_signal", "")),
            "fraud_type_predicted": str(row.get("fraud_type_predicted", "")),
            "fraud_probability":    float(row.get("fraud_probability", 0.0)),
            "flags":                list(row.get("rule_flags", [])),
            "reasons":              list(row.get("rule_reasons", [])),
            "combined_reason":      str(row.get("combined_reason", "")),
        })

    output = {
        "summary":              result.portfolio_summary,
        "flagged_transactions": flagged_records,
        "episodes":             result.episodes,
        "llm_prompt":           result.llm_prompt,
    } 

    return output

# ===========================================================================
# 15. CLI MAIN FUNCTION
# ===========================================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset",    help="Single labeled dataset CSV for training")
    p.add_argument("--train-both", action="store_true",
                   help="Train on both aryan208 + valakhorasani merged")
    p.add_argument("--aryan",      help="Path to financial_fraud_detection_dataset.csv")
    p.add_argument("--vala",       help="Path to bank_transactions_data_2.csv")
    p.add_argument("--predict",    help="User bank statement CSV (no is_fraud needed)")
    p.add_argument("--sample",     type=int, default=None,
                   help="Sample N rows  (e.g. --sample 100000 for quick test)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    loader = DatasetLoader()

    if args.dataset:
        df, name = loader.load(args.dataset, sample=args.sample)
        ft_map = getattr(loader, "_fraud_type_classes", FRAUD_TYPE_LABELS)
        engine = UnifiedFraudEngine()
        results = engine.train(df, ft_map)
        
        print(f"\n{'='*55}")
        print(f"  FINAL MODEL COMPARISON")
        print(f"{'='*55}")
        print(f"  {'Model':<22} {'AUC-PR':>7} {'F1':>7} {'Recall':>7}")
        print(f"  {'-'*22} {'-'*7} {'-'*7} {'-'*7}")
        for r in results.values():
            print(f"  {r['model']:<22} {r['auc_pr']:>7.4f} {r['f1']:>7.4f} {r['recall']:>7.4f}")
        print(f"{'='*55}")
        best = max(results.values(), key=lambda x: x["auc_pr"])
        print(f"  Best model: {best['model']}  (AUC-PR {best['auc_pr']:.4f})")

    elif args.train_both:
        if not args.aryan or not args.vala:
            print("ERROR: --train-both needs --aryan <file> --vala <file>")
            sys.exit(1)
        df1, _ = loader.load(args.aryan, sample=args.sample)
        ft_map = getattr(loader, "_fraud_type_classes", FRAUD_TYPE_LABELS)
        df2, _ = loader.load(args.vala)
        shared = [c for c in df1.columns if c in df2.columns]
        df_all = pd.concat([df1[shared], df2[shared]], ignore_index=True)
        df_all = df_all.sample(frac=1, random_state=42).reset_index(drop=True)
        print(f"\n  Combined dataset: {len(df_all):,} rows")
        engine = UnifiedFraudEngine()
        results = engine.train(df_all, ft_map)
        
        print(f"\n{'='*55}")
        print(f"  FINAL MODEL COMPARISON")
        print(f"{'='*55}")
        print(f"  {'Model':<22} {'AUC-PR':>7} {'F1':>7} {'Recall':>7}")
        print(f"  {'-'*22} {'-'*7} {'-'*7} {'-'*7}")
        for r in results.values():
            print(f"  {r['model']:<22} {r['auc_pr']:>7.4f} {r['f1']:>7.4f} {r['recall']:>7.4f}")
        print(f"{'='*55}")
        best = max(results.values(), key=lambda x: x["auc_pr"])
        print(f"  Best model: {best['model']}  (AUC-PR {best['auc_pr']:.4f})")

    elif args.predict:
        df = pd.read_csv(args.predict)
        engine = UnifiedFraudEngine()
        result = engine.run(df)

        scored_df = result.scored_df
        flagged = (scored_df["is_fraud_predicted"] == 1)
        
        print(f"\n{'='*55}")
        print(f"  PREDICTION SUMMARY")
        print(f"{'='*55}")
        print(f"  Total transactions   : {len(scored_df):,}")
        print(f"  Flagged as fraud     : {flagged.sum():,}  ({flagged.mean()*100:.1f}%)")
        print(f"\n  Risk level breakdown :")
        for lo, hi, label, icon, _ in RISK_CATEGORIES:
            n = (scored_df["risk_category"] == label).sum()
            bar = "#" * min(int(n / max(len(scored_df), 1) * 50), 50)
            print(f"    {label:8s}  {n:>5,}  {bar}")

        if flagged.sum() > 0:
            print(f"\n  Top flagged transactions:")
            cols_show = ["amount", "risk_category", "final_risk_score", "fraud_type_predicted", "combined_reason"]
            top = scored_df[flagged].sort_values("final_risk_score", ascending=False).head(10)
            print(top[cols_show].to_string(index=False))

            type_counts = scored_df[flagged]["fraud_type_predicted"].value_counts()
            print(f"\n  Fraud types detected:")
            for ft, cnt in type_counts.items():
                print(f"    {ft:35s}  {cnt:,}")

        out_path = os.path.join(CONFIG.RESULTS_DIR, "predictions.csv")
        scored_df.to_csv(out_path, index=False)
        print(f"\n  [OK] Full results saved -> {out_path}")

    else:
        p.print_help()


if __name__ == "__main__":
    main()
