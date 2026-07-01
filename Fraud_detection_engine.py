"""
============================================================
  FRAUD DETECTION ENGINE  v2
  Automated Bank Statement Analyzer
============================================================
  YOUR FILES:
    TRAIN 1 → financial_fraud_detection_dataset.csv   (aryan208,  5M rows)
    TRAIN 2 → bank_transactions_data_2.csv            (valakhorasani, 2.5K rows)

  PREDICT  → any bank statement CSV  (no is_fraud needed)

  COMMANDS:
    # Quick test (100K rows, ~2 min)
    python fraud_detection_engine.py --dataset financial_fraud_detection_dataset.csv --sample 100000

    # Full aryan208 training (~20 min)
    python fraud_detection_engine.py --dataset financial_fraud_detection_dataset.csv

    # Train on valakhorasani (fast, 2.5K rows)
    python fraud_detection_engine.py --dataset bank_transactions_data_2.csv

    # Train on BOTH combined (recommended)
    python fraud_detection_engine.py --train-both \
        --aryan financial_fraud_detection_dataset.csv \
        --vala  bank_transactions_data_2.csv \
        --sample 200000

    # Predict on user bank statement
    python fraud_detection_engine.py --predict bank_statement.csv
============================================================
"""

import os, sys, argparse, warnings, json
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import joblib
from datetime import datetime

from sklearn.ensemble        import RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing   import LabelEncoder, StandardScaler
from sklearn.metrics         import (
    classification_report, confusion_matrix,
    roc_auc_score, average_precision_score,
    f1_score, precision_score, recall_score
)

try:
    import xgboost as xgb
    XGB = True
except ImportError:
    XGB = False
    print("[WARN] pip install xgboost")

try:
    from imblearn.over_sampling import SMOTE
    HAS_SMOTE = True
except ImportError:
    HAS_SMOTE = False
    print("[WARN] pip install imbalanced-learn")

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False
    print("[WARN] pip install shap")

MODELS_DIR  = "models"
RESULTS_DIR = "results"
os.makedirs(MODELS_DIR,  exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════
#  KNOWN COLUMN MAPS  (exact columns in your two CSV files)
# ══════════════════════════════════════════════════════════════

# financial_fraud_detection_dataset.csv  (aryan208)
ARYAN_COLS = {
    "amount"          : "amount",
    "timestamp"       : "timestamp",
    "txn_type"        : "transaction_type",
    "merchant"        : "merchant_category",
    "channel"         : "payment_channel",
    "label"           : "is_fraud",
    "fraud_type_col"  : "fraud_type",          # multi-class label ← bonus
    "anomaly_score"   : "anomaly_score",        # pre-computed, use as feature
    "device"          : "device_used",
    "detect"          : lambda df: "fraud_type" in df.columns and "sender_account" in df.columns
}

# bank_transactions_data_2.csv  (valakhorasani)
VALA_COLS = {
    "amount"          : "TransactionAmount",
    "timestamp"       : "TransactionDate",
    "txn_type"        : "TransactionType",
    "merchant"        : "MerchantID",
    "channel"         : "Channel",
    "balance_after"   : "AccountBalance",
    "label"           : "IsFraudulent",
    "fraud_type_col"  : None,                  # not available in this dataset
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


# ══════════════════════════════════════════════════════════════
#  STEP 1 — DATASET LOADER
# ══════════════════════════════════════════════════════════════

class DatasetLoader:

    def load(self, filepath: str, sample: int = None) -> tuple:
        """
        Returns (unified_df, dataset_name)
        unified_df always has these columns:
            amount, hour, day_of_week, is_weekend, month,
            balance_before, balance_after, balance_delta,
            balance_utilization, merchant_encoded,
            channel_encoded, txn_type_encoded,
            anomaly_score_raw,              ← 0 if not available
            is_fraud,                       ← binary label
            fraud_type_label                ← int label (0=normal, 1-5=fraud types)
        """
        print(f"\n{'='*55}")
        print(f"  Loading: {os.path.basename(filepath)}")
        print(f"{'='*55}")

        df = pd.read_csv(filepath, low_memory=False)
        print(f"  Rows   : {len(df):,}")
        print(f"  Cols   : {list(df.columns)}")

        if sample and sample < len(df):
            df = df.sample(sample, random_state=42).reset_index(drop=True)
            print(f"  Sampled: {len(df):,} rows")

        # Detect dataset
        if ARYAN_COLS["detect"](df):
            name = "aryan208"
            print(f"  Dataset: aryan208 (financial_fraud_detection_dataset)")
            unified = self._map(df, ARYAN_COLS)
        elif VALA_COLS["detect"](df):
            name = "valakhorasani"
            print(f"  Dataset: valakhorasani (bank_transactions_data_2)")
            unified = self._map(df, VALA_COLS)
        else:
            name = "unknown"
            print(f"  Dataset: unknown format — using generic mapping")
            unified = self._generic(df)

        fraud_n = unified["is_fraud"].sum()
        print(f"\n  Fraud   : {fraud_n:,} / {len(unified):,}  ({fraud_n/len(unified)*100:.2f}%)")
        return unified, name

    def _map(self, df: pd.DataFrame, cols: dict) -> pd.DataFrame:
        out = pd.DataFrame()

        # ── Amount ──────────────────────────────────────────
        out["amount"] = pd.to_numeric(df[cols["amount"]], errors="coerce").fillna(0)

        # ── Binary label ────────────────────────────────────
        out["is_fraud"] = pd.to_numeric(df[cols["label"]], errors="coerce").fillna(0).astype(int)

        # ── Fraud type (multi-class) ─────────────────────────
        if cols.get("fraud_type_col") and cols["fraud_type_col"] in df.columns:
            le_ft = LabelEncoder()
            ft_raw = df[cols["fraud_type_col"]].astype(str).fillna("Normal")
            ft_encoded = le_ft.fit_transform(ft_raw)
            # Shift so fraud=0 stays 0, fraud types become 1-N
            out["fraud_type_label"] = np.where(
                out["is_fraud"] == 0, 0, ft_encoded + 1
            )
            # Save label map for later
            self._fraud_type_classes = {i+1: cls for i, cls in enumerate(le_ft.classes_)}
            self._fraud_type_classes[0] = "Normal"
        else:
            out["fraud_type_label"] = out["is_fraud"].astype(int)
            self._fraud_type_classes = FRAUD_TYPE_LABELS

        # ── Timestamp ───────────────────────────────────────
        if cols.get("timestamp") and cols["timestamp"] in df.columns:
            ts = pd.to_datetime(df[cols["timestamp"]], errors="coerce")
            out["hour"]        = ts.dt.hour.fillna(12).astype(int)
            out["day_of_week"] = ts.dt.dayofweek.fillna(0).astype(int)
            out["is_weekend"]  = (out["day_of_week"] >= 5).astype(int)
            out["month"]       = ts.dt.month.fillna(1).astype(int)
        else:
            out["hour"] = 12; out["day_of_week"] = 0
            out["is_weekend"] = 0; out["month"] = 1

        # ── Balances ─────────────────────────────────────────
        if cols.get("balance_after") and cols["balance_after"] in df.columns:
            out["balance_after"]  = pd.to_numeric(df[cols["balance_after"]], errors="coerce").fillna(0)
            out["balance_before"] = out["balance_after"] + out["amount"]
        else:
            out["balance_before"] = out["amount"] * 10
            out["balance_after"]  = (out["balance_before"] - out["amount"]).clip(lower=0)

        out["balance_delta"]       = out["balance_before"] - out["balance_after"]
        out["balance_utilization"] = (out["amount"] / (out["balance_before"] + 1)).clip(upper=10)

        # ── Encoded categoricals ─────────────────────────────
        for out_col, src_col in [
            ("merchant_encoded", cols.get("merchant")),
            ("channel_encoded",  cols.get("channel")),
            ("txn_type_encoded", cols.get("txn_type")),
        ]:
            if src_col and src_col in df.columns:
                out[out_col] = LabelEncoder().fit_transform(
                    df[src_col].astype(str).fillna("UNK")
                )
            else:
                out[out_col] = 0

        # ── Pre-computed anomaly score (aryan208 only) ───────
        if cols.get("anomaly_score") and cols["anomaly_score"] in df.columns:
            out["anomaly_score_raw"] = pd.to_numeric(
                df[cols["anomaly_score"]], errors="coerce"
            ).fillna(0)
        else:
            out["anomaly_score_raw"] = 0.0

        return out

    def _generic(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fallback for unknown CSV formats."""
        out = pd.DataFrame()
        out["amount"]    = pd.to_numeric(df.get("amount", df.get("Amount", pd.Series([0]*len(df)))), errors="coerce").fillna(0)
        for lbl in ["is_fraud","isFraud","IsFraudulent","Class","fraud"]:
            if lbl in df.columns:
                out["is_fraud"] = pd.to_numeric(df[lbl], errors="coerce").fillna(0).astype(int)
                break
        else:
            out["is_fraud"] = 0
        out["fraud_type_label"]    = out["is_fraud"]
        out["hour"]                = 12
        out["day_of_week"]         = 0
        out["is_weekend"]          = 0
        out["month"]               = 1
        out["balance_before"]      = out["amount"] * 10
        out["balance_after"]       = out["amount"] * 9
        out["balance_delta"]       = out["amount"]
        out["balance_utilization"] = 0.1
        out["merchant_encoded"]    = 0
        out["channel_encoded"]     = 0
        out["txn_type_encoded"]    = 0
        out["anomaly_score_raw"]   = 0.0
        self._fraud_type_classes   = FRAUD_TYPE_LABELS
        return out


# ══════════════════════════════════════════════════════════════
#  STEP 2 — FEATURE ENGINEER
# ══════════════════════════════════════════════════════════════

FEATURE_COLS = [
    "amount", "log_amount",
    "hour", "day_of_week", "is_weekend", "month",
    "is_night",                 # 11 PM – 5 AM
    "is_early_morning",         # 12 AM – 6 AM  (tighter window)
    "is_round_amount",          # % 1000 == 0
    "is_near_threshold",        # within 10% of 10000 (smurfing signal)
    "is_large_amount",          # > 95th percentile
    "balance_before", "balance_after",
    "balance_delta", "balance_utilization",
    "balance_zeroed_out",       # balance drops to 0
    "amount_to_balance_ratio",
    "merchant_encoded", "channel_encoded", "txn_type_encoded",
    "anomaly_score_raw",        # pre-computed score (aryan208)
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["log_amount"]           = np.log1p(df["amount"])
    df["is_night"]             = ((df["hour"] >= 23) | (df["hour"] <= 5)).astype(int)
    df["is_early_morning"]     = ((df["hour"] >= 0)  & (df["hour"] <= 6)).astype(int)
    df["is_round_amount"]      = ((df["amount"] % 1000) == 0).astype(int)
    df["is_near_threshold"]    = (
        (df["amount"] >= 9000) & (df["amount"] <= 9999)
    ).astype(int)   # stays just below ₹10,000 reporting threshold
    df["is_large_amount"]      = (df["amount"] > df["amount"].quantile(0.95)).astype(int)
    df["balance_zeroed_out"]   = (df["balance_after"] <= 0).astype(int)
    df["amount_to_balance_ratio"] = (df["amount"] / (df["balance_before"] + 1)).clip(upper=10)

    # fill any missing feature columns
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0
    return df


# ══════════════════════════════════════════════════════════════
#  STEP 3 — MODEL TRAINER
# ══════════════════════════════════════════════════════════════

class FraudModelTrainer:

    def __init__(self):
        self.rf  = None
        self.xgb = None
        self.iso = None
        self.xgb_type = None          # multi-class fraud type model
        self.scaler   = StandardScaler()
        self.results  = {}

    # ── Public entry ────────────────────────────────────────
    def train(self, df: pd.DataFrame, fraud_type_classes: dict):
        df = engineer_features(df)
        X  = df[FEATURE_COLS].fillna(0)
        y  = df["is_fraud"]
        y_type = df["fraud_type_label"]

        self._print_class_dist(y)

        # SMOTE
        X_bal, y_bal = self._balance(X, y)

        X_tr, X_te, y_tr, y_te = train_test_split(
            X_bal, y_bal, test_size=0.2, random_state=42, stratify=y_bal
        )
        X_tr_sc = self.scaler.fit_transform(X_tr)
        X_te_sc = self.scaler.transform(X_te)

        print(f"\n  Train : {len(X_tr):,}   Test : {len(X_te):,}")
        print("─"*55)

        # 1 · Random Forest
        self._train_rf(X_tr, X_te, y_tr, y_te)
        # 2 · XGBoost (binary)
        self._train_xgb(X_tr, X_te, y_tr, y_te)
        # 3 · Isolation Forest
        self._train_iso(X_tr_sc, X_te_sc, y_tr, y_te)
        # 4 · XGBoost multi-class fraud type  (only if fraud_type data available)
        if y_type.nunique() > 2:
            self._train_fraud_type(X, y_type, fraud_type_classes)

        self._save()
        return self.results

    # ── Random Forest ────────────────────────────────────────
    def _train_rf(self, X_tr, X_te, y_tr, y_te):
        print("\n  [1/3] Random Forest")
        self.rf = RandomForestClassifier(
            n_estimators=200, max_depth=12,
            min_samples_leaf=5, class_weight="balanced",
            n_jobs=-1, random_state=42
        )
        self.rf.fit(X_tr, y_tr)
        self.results["random_forest"] = self._eval(
            y_te, self.rf.predict(X_te),
            self.rf.predict_proba(X_te)[:,1], "Random Forest"
        )

    # ── XGBoost binary ───────────────────────────────────────
    def _train_xgb(self, X_tr, X_te, y_tr, y_te):
        if not XGB:
            return
        print("\n  [2/3] XGBoost  (binary fraud detector)")
        spw = int((y_tr==0).sum()) / max(int((y_tr==1).sum()), 1)
        self.xgb = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=spw, eval_metric="aucpr",
            random_state=42, n_jobs=-1, verbosity=0
        )
        self.xgb.fit(X_tr, y_tr,
                     eval_set=[(X_te, y_te)], verbose=False)
        self.results["xgboost"] = self._eval(
            y_te, self.xgb.predict(X_te),
            self.xgb.predict_proba(X_te)[:,1], "XGBoost"
        )

    # ── Isolation Forest ─────────────────────────────────────
    def _train_iso(self, X_tr_sc, X_te_sc, y_tr, y_te):
        print("\n  [3/3] Isolation Forest  (unsupervised fallback)")
        contam = min(0.1, max(0.001, (y_tr==1).sum()/len(y_tr)))
        self.iso = IsolationForest(
            n_estimators=200, contamination=contam,
            max_features=0.8, n_jobs=-1, random_state=42
        )
        normal_mask = (y_tr == 0)
        self.iso.fit(X_tr_sc[normal_mask])
        raw  = self.iso.decision_function(X_te_sc)
        pred = (self.iso.predict(X_te_sc) == -1).astype(int)
        score = 1 - (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)
        self.results["isolation_forest"] = self._eval(
            y_te, pred, score, "Isolation Forest"
        )

    # ── XGBoost multi-class fraud type ───────────────────────
    def _train_fraud_type(self, X, y_type, fraud_type_classes):
        if not XGB:
            return
        print("\n  [+]  XGBoost Fraud TYPE classifier  (multi-class)")
        print(f"       Classes: {dict(list(fraud_type_classes.items())[:6])}")
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y_type, test_size=0.2, random_state=42, stratify=y_type
        )
        self.xgb_type = xgb.XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.1,
            n_jobs=-1, random_state=42, verbosity=0,
            num_class=y_type.nunique(), objective="multi:softprob",
            eval_metric="mlogloss"
        )
        self.xgb_type.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
        acc = (self.xgb_type.predict(X_te) == y_te).mean()
        print(f"       Accuracy: {acc:.4f}")
        joblib.dump(fraud_type_classes,
                    os.path.join(MODELS_DIR, "fraud_type_classes.pkl"))

    # ── Evaluation ───────────────────────────────────────────
    def _eval(self, y_true, y_pred, y_proba, name):
        try:
            auc_roc = roc_auc_score(y_true, y_proba)
            auc_pr  = average_precision_score(y_true, y_proba)
        except Exception:
            auc_roc = auc_pr = 0.0
        f1   = f1_score(y_true, y_pred, zero_division=0)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec  = recall_score(y_true, y_pred, zero_division=0)
        cm   = confusion_matrix(y_true, y_pred)
        tn,fp,fn,tp = cm.ravel() if cm.shape==(2,2) else (0,0,0,0)

        print(f"\n  ┌─ {name} ─────────────────────────────")
        print(f"  │  AUC-PR    {auc_pr:.4f}  ← key metric (imbalanced)")
        print(f"  │  AUC-ROC   {auc_roc:.4f}")
        print(f"  │  F1        {f1:.4f}   Precision {prec:.4f}   Recall {rec:.4f}")
        print(f"  │  TP={int(tp):,}  FP={int(fp):,}  FN={int(fn):,}  TN={int(tn):,}")
        print(f"  └{'─'*45}")
        return dict(model=name, auc_pr=auc_pr, auc_roc=auc_roc,
                    f1=f1, precision=prec, recall=rec,
                    tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn))

    # ── Save ─────────────────────────────────────────────────
    def _save(self):
        if self.rf:
            joblib.dump(self.rf,  f"{MODELS_DIR}/random_forest.pkl")
        if self.xgb:
            joblib.dump(self.xgb, f"{MODELS_DIR}/xgboost.pkl")
        if self.iso:
            joblib.dump(self.iso, f"{MODELS_DIR}/isolation_forest.pkl")
        if self.xgb_type:
            joblib.dump(self.xgb_type, f"{MODELS_DIR}/xgboost_fraud_type.pkl")
        joblib.dump(self.scaler, f"{MODELS_DIR}/scaler.pkl")
        with open(f"{RESULTS_DIR}/training_results.json","w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n  ✅ Models saved → ./{MODELS_DIR}/")
        print(f"     random_forest.pkl  |  xgboost.pkl  |  isolation_forest.pkl")
        print(f"     xgboost_fraud_type.pkl  |  scaler.pkl")

    # ── Balance ──────────────────────────────────────────────
    def _balance(self, X, y):
        fraud_n = int(y.sum())
        if HAS_SMOTE and fraud_n > 10:
            print(f"\n  Applying SMOTE  (fraud={fraud_n:,}) ...")
            try:
                sm = SMOTE(random_state=42,
                           k_neighbors=min(5, fraud_n - 1))
                Xr, yr = sm.fit_resample(X, y)
                print(f"  After SMOTE: {len(Xr):,} rows  fraud={yr.sum():,}")
                return Xr, yr
            except Exception as e:
                print(f"  SMOTE skipped: {e}")
        return X, y

    def _print_class_dist(self, y):
        n = len(y); f = int(y.sum())
        print(f"\n  Class distribution:")
        print(f"    Normal : {n-f:>10,}  ({(n-f)/n*100:.2f}%)")
        print(f"    Fraud  : {f:>10,}  ({f/n*100:.2f}%)")
        print(f"    Ratio  : 1 fraud per {n//max(f,1)} transactions")


# ══════════════════════════════════════════════════════════════
#  STEP 4 — PREDICTOR  (for user-uploaded bank statements)
# ══════════════════════════════════════════════════════════════

class FraudPredictor:
    """
    Loads saved models.
    Input : user's bank statement CSV  — NO is_fraud column needed
    Output: same CSV + fraud prediction columns added
    """

    def __init__(self):
        self.rf        = self._load("random_forest.pkl")
        self.xgb       = self._load("xgboost.pkl")
        self.iso       = self._load("isolation_forest.pkl")
        self.xgb_type  = self._load("xgboost_fraud_type.pkl")
        self.scaler    = self._load("scaler.pkl")
        self.ft_map    = self._load("fraud_type_classes.pkl") or FRAUD_TYPE_LABELS

    def _load(self, f):
        p = f"{MODELS_DIR}/{f}"
        return joblib.load(p) if os.path.exists(p) else None

    def predict(self, csv_path: str) -> pd.DataFrame:
        print(f"\n  Loading bank statement: {csv_path}")
        df_orig = pd.read_csv(csv_path)
        print(f"  Rows: {len(df_orig):,}   Columns: {list(df_orig.columns)}")

        # ── Map to unified schema ────────────────────────────
        df_uni = self._map_user_file(df_orig)
        df_eng = engineer_features(df_uni)
        X      = df_eng[FEATURE_COLS].fillna(0)

        scores = {}
        if self.rf:
            scores["rf"]  = self.rf.predict_proba(X)[:,1]
        if self.xgb:
            scores["xgb"] = self.xgb.predict_proba(X)[:,1]
        if self.iso and self.scaler:
            X_sc = self.scaler.transform(X)
            raw  = self.iso.decision_function(X_sc)
            scores["iso"] = 1-(raw-raw.min())/(raw.max()-raw.min()+1e-9)

        # Ensemble: XGB 45% · RF 40% · ISO 15%
        wt = {"xgb":0.45, "rf":0.40, "iso":0.15}
        ens = np.zeros(len(X))
        tot = 0
        for k,s in scores.items():
            ens += wt.get(k,0.33)*s; tot += wt.get(k,0.33)
        ens /= tot

        # ── Fraud type prediction ────────────────────────────
        if self.xgb_type:
            type_pred = self.xgb_type.predict(X)
            type_prob = self.xgb_type.predict_proba(X).max(axis=1)
            fraud_type_name = [
                self.ft_map.get(int(t), "Unknown") for t in type_pred
            ]
        else:
            fraud_type_name = ["Unknown"] * len(X)
            type_prob       = np.zeros(len(X))

        # ── Build output ─────────────────────────────────────
        df_orig["fraud_probability"]   = np.round(ens, 4)
        df_orig["is_fraud_predicted"]  = (ens > 0.50).astype(int)
        df_orig["risk_level"]          = pd.cut(
            ens, bins=[-0.001,0.30,0.60,0.80,1.001],
            labels=["LOW","MEDIUM","HIGH","CRITICAL"]
        ).astype(str)
        df_orig["fraud_type_predicted"] = np.where(
            ens > 0.30, fraud_type_name, "Normal"
        )
        df_orig["fraud_type_confidence"] = np.where(
            ens > 0.30, np.round(type_prob,3), 1-ens
        )
        df_orig["fraud_reason"]         = self._reasons(df_eng, X, ens)

        if HAS_SHAP and self.rf:
            try:
                exp  = shap.TreeExplainer(self.rf)
                sv   = exp.shap_values(X)
                sv1  = sv[1] if isinstance(sv, list) else sv
                df_orig["top_risk_feature"] = [
                    f"{X.columns[np.argmax(np.abs(r))]}  ({sv1[i,np.argmax(np.abs(r))]:+.3f})"
                    for i, r in enumerate(sv1)
                ]
            except Exception as e:
                print(f"  [SHAP skipped: {e}]")

        # ── Print summary ────────────────────────────────────
        flagged = (df_orig["is_fraud_predicted"] == 1)
        print(f"\n{'='*55}")
        print(f"  PREDICTION SUMMARY")
        print(f"{'='*55}")
        print(f"  Total transactions   : {len(df_orig):,}")
        print(f"  Flagged as fraud     : {flagged.sum():,}  ({flagged.mean()*100:.1f}%)")
        print(f"\n  Risk level breakdown :")
        for lvl in ["CRITICAL","HIGH","MEDIUM","LOW"]:
            n = (df_orig["risk_level"]==lvl).sum()
            bar = "█" * min(int(n/max(len(df_orig),1)*50),50)
            print(f"    {lvl:8s}  {n:>5,}  {bar}")

        if flagged.sum() > 0:
            print(f"\n  Top flagged transactions:")
            cols_show = [c for c in [
                "amount","risk_level","fraud_probability",
                "fraud_type_predicted","fraud_reason"
            ] if c in df_orig.columns]
            top = df_orig[flagged].sort_values(
                "fraud_probability", ascending=False
            ).head(10)
            print(top[cols_show].to_string(index=False))

            # Fraud type breakdown
            type_counts = df_orig[flagged]["fraud_type_predicted"].value_counts()
            print(f"\n  Fraud types detected:")
            for ft, cnt in type_counts.items():
                print(f"    {ft:35s}  {cnt:,}")

        out_path = f"{RESULTS_DIR}/predictions.csv"
        df_orig.to_csv(out_path, index=False)
        print(f"\n  ✅ Full results saved → {out_path}")
        return df_orig

    def _map_user_file(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Map any user-uploaded bank statement to unified schema.
        Handles your app's standardized columns automatically.
        """
        out = pd.DataFrame()

        # amount
        out["amount"] = pd.to_numeric(
            df.get("amount", df.get("Amount", df.get("TransactionAmount",
            pd.Series([0]*len(df))))), errors="coerce"
        ).fillna(0)

        # timestamp
        for tc in ["transactionTimestamp","date","Date","timestamp","TransactionDate"]:
            if tc in df.columns:
                ts = pd.to_datetime(df[tc], errors="coerce")
                out["hour"]        = ts.dt.hour.fillna(12).astype(int)
                out["day_of_week"] = ts.dt.dayofweek.fillna(0).astype(int)
                out["is_weekend"]  = (out["day_of_week"] >= 5).astype(int)
                out["month"]       = ts.dt.month.fillna(1).astype(int)
                break
        else:
            out["hour"]=12; out["day_of_week"]=0
            out["is_weekend"]=0; out["month"]=1

        # balance
        for bc in ["balance","currentBalance","Balance","AccountBalance"]:
            if bc in df.columns:
                out["balance_after"]  = pd.to_numeric(df[bc], errors="coerce").fillna(0)
                break
        else:
            out["balance_after"] = out["amount"] * 5
        out["balance_before"]      = out["balance_after"] + out["amount"]
        out["balance_delta"]       = out["amount"]
        out["balance_utilization"] = (out["amount"]/(out["balance_before"]+1)).clip(upper=10)

        # categorical encodings
        for out_col, candidates in [
            ("merchant_encoded", ["narration","Merchant","merchant","MerchantID","description"]),
            ("channel_encoded",  ["transaction_type","mode","Channel","TransactionType","type"]),
            ("txn_type_encoded", ["debit_credit","type","TransactionType","debit_credit"]),
        ]:
            col = next((c for c in candidates if c in df.columns), None)
            out[out_col] = LabelEncoder().fit_transform(
                df[col].astype(str).fillna("UNK")
            ) if col else 0

        out["anomaly_score_raw"] = 0.0
        out["is_fraud"]          = 0
        out["fraud_type_label"]  = 0
        return out

    def _reasons(self, df, X, scores):
        reasons = []
        for i, s in enumerate(scores):
            if s < 0.30:
                reasons.append("No significant fraud signals")
                continue
            r = []
            row = X.iloc[i]
            if row.get("is_night",0):        r.append("Night-time transaction")
            if row.get("is_early_morning",0): r.append("Early morning (12–6 AM)")
            if row.get("is_large_amount",0):  r.append("Amount in top 5% of all transactions")
            if row.get("balance_zeroed_out",0): r.append("Account balance drained to zero")
            if row.get("balance_utilization",0)>0.8: r.append("Uses >80% of account balance")
            if row.get("is_round_amount",0):  r.append("Suspiciously round amount")
            if row.get("is_near_threshold",0): r.append("Amount just below ₹10,000 (smurfing)")
            if row.get("amount_to_balance_ratio",0)>2: r.append("Amount exceeds available balance")
            if not r: r.append("Multiple weak anomaly signals combined")
            reasons.append(" | ".join(r))
        return reasons


# ══════════════════════════════════════════════════════════════
#  STREAMLIT HELPER  (drop into your existing app)
# ══════════════════════════════════════════════════════════════

class FraudEngineForStreamlit:
    def __init__(self, model_dir="models"):
        global MODELS_DIR
        MODELS_DIR = model_dir
        self.predictor = None
        self._ready    = False

    def load(self) -> bool:
        try:
            self.predictor = FraudPredictor()
            self._ready = (self.predictor.rf is not None or
                           self.predictor.xgb is not None or
                           self.predictor.iso is not None)
            return self._ready
        except Exception as e:
            print(f"[FraudEngine] load failed: {e}")
            return False

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._ready:
            return self._rule_fallback(df)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f, index=False); tmp = f.name
        try:
            return self.predictor.predict(tmp)
        finally:
            os.unlink(tmp)

    def _rule_fallback(self, df):
        df = df.copy()
        s  = np.zeros(len(df))
        for ac in ["amount","Amount"]:
            if ac in df.columns:
                a = pd.to_numeric(df[ac], errors="coerce").fillna(0)
                s += (a > a.quantile(0.95)).astype(float)*25
                s += ((a%1000)==0).astype(float)*10
                break
        for tc in ["transactionTimestamp","date","timestamp"]:
            if tc in df.columns:
                h = pd.to_datetime(df[tc], errors="coerce").dt.hour
                s += (((h>=23)|(h<=5)).astype(float)*20)
                break
        df["fraud_probability"]   = (s/100).clip(0,1)
        df["is_fraud_predicted"]  = (df["fraud_probability"]>0.5).astype(int)
        df["risk_level"]          = pd.cut(df["fraud_probability"],
            bins=[-0.001,0.30,0.60,0.80,1.001],
            labels=["LOW","MEDIUM","HIGH","CRITICAL"]).astype(str)
        df["fraud_reason"]        = "Rule-based: " + df["risk_level"]
        df["fraud_type_predicted"]= "Unknown"
        return df


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

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

    loader = DatasetLoader()

    # ── TRAIN on single dataset ──────────────────────────────
    if args.dataset:
        df, name = loader.load(args.dataset, sample=args.sample)
        ft_map   = getattr(loader, "_fraud_type_classes", FRAUD_TYPE_LABELS)
        df_eng   = engineer_features(df)
        X        = df_eng[FEATURE_COLS].fillna(0)
        trainer  = FraudModelTrainer()
        results  = trainer.train(df, ft_map)
        _print_summary(results)

    # ── TRAIN on BOTH datasets merged ────────────────────────
    elif args.train_both:
        if not args.aryan or not args.vala:
            print("ERROR: --train-both needs --aryan <file> --vala <file>")
            sys.exit(1)
        df1, _ = loader.load(args.aryan, sample=args.sample)
        ft_map  = getattr(loader, "_fraud_type_classes", FRAUD_TYPE_LABELS)
        df2, _ = loader.load(args.vala)
        # Align columns
        shared = [c for c in df1.columns if c in df2.columns]
        df_all = pd.concat([df1[shared], df2[shared]], ignore_index=True)
        df_all = df_all.sample(frac=1, random_state=42).reset_index(drop=True)
        print(f"\n  Combined dataset: {len(df_all):,} rows")
        trainer = FraudModelTrainer()
        results = trainer.train(df_all, ft_map)
        _print_summary(results)

    # ── PREDICT on user bank statement ───────────────────────
    elif args.predict:
        pred = FraudPredictor()
        pred.predict(args.predict)

    else:
        p.print_help()
        print("""
  ─────────────────────────────────────────────────
  QUICK START COMMANDS:
  ─────────────────────────────────────────────────

  # 1. Quick test — aryan208, 100K rows (~2 min)
  python fraud_detection_engine.py \\
      --dataset financial_fraud_detection_dataset.csv \\
      --sample 100000

  # 2. Full aryan208 training (~15–20 min)
  python fraud_detection_engine.py \\
      --dataset financial_fraud_detection_dataset.csv

  # 3. Train valakhorasani (2.5K rows, instant)
  python fraud_detection_engine.py \\
      --dataset bank_transactions_data_2.csv

  # 4. Train BOTH combined (recommended)
  python fraud_detection_engine.py \\
      --train-both \\
      --aryan financial_fraud_detection_dataset.csv \\
      --vala  bank_transactions_data_2.csv \\
      --sample 200000

  # 5. Predict on your bank_statements.csv
  python fraud_detection_engine.py \\
      --predict bank_statements.csv
  ─────────────────────────────────────────────────
        """)


def _print_summary(results):
    print(f"\n{'='*55}")
    print(f"  FINAL MODEL COMPARISON")
    print(f"{'='*55}")
    print(f"  {'Model':<22} {'AUC-PR':>7} {'F1':>7} {'Recall':>7}")
    print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*7}")
    for r in results.values():
        print(f"  {r['model']:<22} {r['auc_pr']:>7.4f} {r['f1']:>7.4f} {r['recall']:>7.4f}")
    print(f"{'='*55}")
    best = max(results.values(), key=lambda x: x["auc_pr"])
    print(f"  Best model: {best['model']}  (AUC-PR {best['auc_pr']:.4f})")


if __name__ == "__main__":
    main()