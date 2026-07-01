"""
services/llm_sender.py
-----------------------
Selects specific fields from the analytics, fraud, and cashflow report dicts
and assembles a compact, LLM-ready payload.

This module is NOT responsible for calling the LLM.
That is llm_summary.py's job.

This module's only job:
    - Receive the full merged report dict from app.py
    - Extract only the fields the LLM needs
    - Return a clean Python dict
    - Save that dict to results/llm_input.json for inspection

Fields extracted:

    From analytics:
        total_transactions, total_debits, total_credits,
        net_cash_flow, top_5_merchants

    From fraud:
        flagged_count, amount_at_risk, risk_distribution,
        top_10_flagged_transactions

    From cashflow:
        current_balance, runway_days, risk_level, warnings

Public interface (called by app.py):
    run(df, report) -> dict
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Where to write the inspection file
OUTPUT_PATH = Path("results/llm_input.json")


# ===========================================================================
# Extractors — one per source module, each reads from the real key paths
# confirmed from the actual JSON output files.
# ===========================================================================

def _extract_analytics(report: dict[str, Any]) -> dict[str, Any]:
    """
    Pull fields from report["statistics"] (the analytics block).

    Key paths confirmed from analytics_output.json:
        report["statistics"]["transaction_count"]
        report["statistics"]["total_debit"]
        report["statistics"]["total_credit"]
        report["statistics"]["net_cash_flow"]
        report["statistics"]["merchant_summary"]["merchants"]  -> top 5
    """
    stats = report.get("statistics", {})

    # Top 5 merchants — keep only name and total_amount for the LLM
    raw_merchants = stats.get("merchant_summary", {}).get("merchants", [])
    top_5_merchants = [
        {
            "merchant":     m.get("merchant", "Unknown"),
            "total_amount": m.get("total_amount", 0.0),
            "count":        m.get("count", 0),
        }
        for m in raw_merchants[:5]
    ]

    return {
        "total_transactions": stats.get("transaction_count"),
        "total_debits":       stats.get("total_debit"),
        "total_credits":      stats.get("total_credit"),
        "net_cash_flow":      stats.get("net_cash_flow"),
        "top_5_merchants":    top_5_merchants,
    }


def _extract_fraud(report: dict[str, Any]) -> dict[str, Any]:
    """
    Pull fields from report["fraud"].

    Key paths confirmed from fraud_output.json:
        report["fraud"]["summary"]["flagged_count"]
        report["fraud"]["summary"]["total_amount_at_risk"]   <- actual key name
        report["fraud"]["summary"]["risk_distribution"]
        report["fraud"]["flagged_transactions"]              -> top 10
    """
    fraud = report.get("fraud", {})
    summary = fraud.get("summary", {})

    # Top 10 flagged — keep the fields useful to the LLM, drop raw ML internals
    raw_flagged = fraud.get("flagged_transactions", [])
    top_10_flagged = [
        {
            "transaction_index": t.get("transaction_index"),
            "date":              t.get("date"),
            "merchant":          t.get("merchant"),
            "amount":            t.get("amount"),
            "risk_category":     t.get("risk_category"),
            "final_risk_score":  t.get("final_risk_score"),
            "fraud_type":        t.get("fraud_type_predicted"),
            "flags":             t.get("flags", []),
            "reason":            t.get("combined_reason"),
        }
        for t in raw_flagged[:10]
    ]

    return {
        "flagged_count":            summary.get("flagged_count"),
        "amount_at_risk":           summary.get("total_amount_at_risk"),
        "risk_distribution":        summary.get("risk_distribution", {}),
        "top_10_flagged_transactions": top_10_flagged,
    }


def _extract_cashflow(report: dict[str, Any]) -> dict[str, Any]:
    """
    Pull fields from report["cashflow"].

    Key paths confirmed from cashflow_output.json:
        report["cashflow"]["metrics"]["current_balance"]
        report["cashflow"]["forecast"]["runway_days"]
        report["cashflow"]["forecast"]["risk_classification"]
        report["cashflow"]["warnings"]
    """
    cashflow = report.get("cashflow", {})
    metrics  = cashflow.get("metrics",  {})
    forecast = cashflow.get("forecast", {})

    return {
        "current_balance": metrics.get("current_balance"),
        "runway_days":     forecast.get("runway_days"),
        "risk_level":      forecast.get("risk_classification"),
        "warnings":        cashflow.get("warnings", []),
    }


# ===========================================================================
# Public API
# ===========================================================================

def build_llm_payload(report: dict[str, Any]) -> dict[str, Any]:
    """
    Assemble the compact LLM-ready payload from the full merged report.

    Parameters
    ----------
    report : dict
        The full merged report dict from app.py containing all module outputs.

    Returns
    -------
    dict with keys: analytics, fraud, cashflow
    """
    payload = {
        "analytics": _extract_analytics(report),
        "fraud":     _extract_fraud(report),
        "cashflow":  _extract_cashflow(report),
    }

    logger.info(
        "llm_sender: payload built — "
        "analytics(%d fields) fraud(%d fields) cashflow(%d fields)",
        len(payload["analytics"]),
        len(payload["fraud"]),
        len(payload["cashflow"]),
    )

    return payload


def run(df: Any, report: dict[str, Any]) -> dict[str, Any]:
    """
    Entry point called by app.py's step_optional_services().
    Merged into report["llm_input"] by app.py.

    Parameters
    ----------
    df     : pd.DataFrame — not used here, present for pipeline contract
    report : dict         — full merged report from app.py

    Returns
    -------
    dict — the compact LLM payload, saved to results/llm_input.json
    """
    payload = build_llm_payload(report)

    # Save for inspection — app.py owns all other JSON writes,
    # but this file is specifically the LLM's input, kept separate
    # so llm_summary.py can also load it directly if needed.
    try:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        logger.info("LLM input payload saved → %s", OUTPUT_PATH.resolve())
    except Exception as exc:
        logger.warning("Could not save llm_input.json: %s", exc)

    return payload
