"""
services/cloud_gemini.py
-------------------------
Sends the llm_sender payload to Gemini and returns the raw AI summary.

Pipeline position:
    llm_sender → cloud_gemini (THIS) → report_generator

Public interface (called by app.py):
    run(df, report) -> dict

Output merged into report["gemini"] by app.py:
    {
        "summary":       str,   # raw Gemini response, no parsing
        "generated_at":  str,   # UTC ISO timestamp
        "model_used":    str,
        "status":        str,   # "success" | "fallback"
    }
"""

import logging
import os
import json
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from google import genai

logger = logging.getLogger(__name__)

# Load .env from project root (one level above services/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..","..", ".env"))

MODEL = "gemini-2.5-flash-lite"


# ===========================================================================
# Prompt — edit this freely, structure however you want
# ===========================================================================

def build_prompt(payload: dict[str, Any]) -> str:
    """
    Build the prompt from the llm_sender payload.
    Modify this function to change what the LLM sees or how it responds.
    Full payload is passed as-is — no filtering done here.
    """
    

    return f"""You are a senior financial analyst.
Analyze the following bank statement intelligence report.
Generate a detailed professional evidence-ready report.

Include all of the following sections:
1. Executive Summary
2. Financial Health Assessment
3. Fraud & Risk Analysis (explain WHY each flagged transaction was flagged using the flags and reasons provided)
4. Cashflow Analysis
5. Spending Behaviour Analysis
6. Recommendations

Requirements:
- Use professional business language.
- Explain conclusions using the provided data.
- Discuss the most significant flagged transactions and explain why they were flagged using the provided flags, risk scores, and reasons.
- Highlight unusual patterns.
- Mention potential risks.
- Mention positive findings where relevant.
- Do not invent facts not present in the data.
- Target length: 300-500 words.

DATA:
{json.dumps(payload, indent=2)}
"""


# ===========================================================================
# Core call
# ===========================================================================

def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Call Gemini with the payload and return a dict with the raw response.
    No parsing, no forced structure — whatever Gemini returns goes into "summary".
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("cloud_gemini: GEMINI_API_KEY not set in .env — returning fallback.")
        return {
            "summary":      "AI summary unavailable: GEMINI_API_KEY not configured.",
            "generated_at": timestamp,
            "model_used":   MODEL,
            "status":       "fallback",
        }

    try:
        client   = genai.Client(api_key=api_key)
        prompt   = build_prompt(payload)
        response = client.models.generate_content(model=MODEL, contents=prompt)

        logger.info("cloud_gemini: response received successfully.")
        return {
            "summary":      response.text,
            "generated_at": timestamp,
            "model_used":   MODEL,
            "status":       "success",
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud_gemini: Gemini call failed: %s", exc)
        return {
            "summary":      f"AI summary unavailable: {exc}",
            "generated_at": timestamp,
            "model_used":   MODEL,
            "status":       "fallback",
        }


# ===========================================================================
# app.py interface
# ===========================================================================

def run(df: Any, report: dict[str, Any]) -> dict[str, Any]:
    """
    Called by app.py. Reads report["llm_input"] (from llm_sender),
    calls Gemini, returns summary dict merged into report["gemini"].
    """
    payload = report.get("llm_input", {})

    if not payload:
        logger.warning(
            "cloud_gemini: report['llm_input'] is empty — "
            "ensure llm_sender runs before cloud_gemini in app.py."
        )
        return {
            "summary":      "AI summary unavailable: llm_sender output missing.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_used":   MODEL,
            "status":       "fallback",
        }

    return summarize(payload)
