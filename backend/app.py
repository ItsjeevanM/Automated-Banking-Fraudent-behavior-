"""
app.py
------
Top-level orchestrator for the AI-Powered Bank Statement Analysis Platform.

Responsibility: wire the pipeline together. Zero business logic lives here.
Every analytical, risk, or AI concern belongs in its own service module.

Pipeline:
    CSV file
      │
      ▼  services/normalizer.py
    Standardized records  (list[dict])
      │
      ▼  pandas
    DataFrame
      │
      ▼  services/analytics.py
    Analytics report  (dict)
      │
      ▼  services/risk_engine.py        (optional – skipped if absent)
      ▼  services/anomaly_detector.py   (optional – skipped if absent)
      ▼  services/llm_summary.py        (optional – skipped if absent)
      ▼  services/report_generator.py   (optional – skipped if absent)
      │
      ▼
    analytics_report.json  +  terminal summary

Usage:
    python app.py <path/to/bank_statement.csv>
    python app.py <path/to/bank_statement.csv> --output reports/june.json
    python app.py <path/to/bank_statement.csv> --log-level DEBUG
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Logging — one configuration for the entire process tree.
# Every service module calls logging.getLogger(__name__) and inherits this.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ===========================================================================
# PIPELINE STEPS
# Each step is a single-purpose function. Adding a new stage = adding one
# function here and one line in main(). Nothing else changes.
# ===========================================================================

def step_validate_file(csv_path: Path) -> None:
    """
    Gate 1 — fail fast if the file is unusable before any module is loaded.

    Raises
    ------
    FileNotFoundError  if the path does not exist.
    ValueError         if the path is not a regular file or is 0 bytes.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not csv_path.is_file():
        raise ValueError(f"Not a regular file: {csv_path}")
    if csv_path.stat().st_size == 0:
        raise ValueError(f"File is empty (0 bytes): {csv_path}")
    logger.info(
        "File OK — %s  (%.1f KB)",
        csv_path.name,
        csv_path.stat().st_size / 1024,
    )


def step_standardize(csv_path: Path) -> list[dict]:
    """
    Gate 2 — delegate to services/normalizer.py and validate the output.

    The normalizer is imported lazily so the rest of the app still loads
    even if the file is temporarily missing (useful in test environments).

    Returns
    -------
    list[dict]
        Non-empty list of standardised transaction records.

    Raises
    ------
    ImportError  if normalizer.py is not on sys.path.
    ValueError   if the normalizer returns an empty list.
    """
    from services import normalizer  # lazy, loosely coupled

    logger.info("Standardizing: %s", csv_path)
    records: list[dict] = normalizer.standardize(str(csv_path))

    if not records:
        raise ValueError(
            "Normalizer returned 0 records — verify the CSV has data rows "
            "and at least one column name the synonym map recognises."
        )
    logger.info("Standardized %d record(s).", len(records))
    return records


def step_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """
    Gate 3 — convert records to a typed Pandas DataFrame.

    Type coercion is the *only* responsibility of this step.
    No analysis, no filtering.

    Returns
    -------
    pd.DataFrame
        DataFrame with date → datetime64, amount/balance → float64.
    """
    df = pd.DataFrame(records)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    if "balance" in df.columns:
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce")

    logger.info(
        "DataFrame ready — %d rows × %d cols  [%s → %s]",
        len(df),
        len(df.columns),
        df["date"].min().date() if "date" in df.columns and df["date"].notna().any() else "?",
        df["date"].max().date() if "date" in df.columns and df["date"].notna().any() else "?",
    )
    return df


def step_analytics(df: pd.DataFrame) -> dict[str, Any]:
    """
    Gate 4 — core analytics via services/analytics.py.

    Returns
    -------
    dict with keys: "statistics", "insights", "charts"
    """
    from services import analytics  # lazy import

    logger.info("Running analytics…")
    report = analytics.generate_analytics_report(df)

    if not isinstance(report, dict):
        raise TypeError(
            f"analytics.generate_analytics_report() must return dict, "
            f"got {type(report).__name__!r}."
        )
    logger.info("Analytics complete (%d top-level keys).", len(report))
    return report


def step_optional_services(
    df: pd.DataFrame,
    report: dict[str, Any],
) -> dict[str, Any]:
    """
    Gate 5 — run any optional service modules that are present on disk.

    Convention: every optional service must expose:
        def run(df: pd.DataFrame, report: dict) -> dict

    The returned dict is merged into *report* under a namespaced key so
    modules never clobber each other.

    To add a new module, just drop it in services/ — no changes to app.py.
    """
    # (module_import_path, namespace_key_in_report)
    optional: list[tuple[str, str]] = [
        ("services.unified_fraud_engine", "fraud"),   # replaces risk_engine + anomaly_detector
        ("services.llm_summary",          "llm"),
        ("services.report_generator",     "formatted_report"),
        ("services.cashflow_predictor",   "cashflow"),
    ]

    for import_path, report_key in optional:
        try:
            import importlib
            mod = importlib.import_module(import_path)
            if not hasattr(mod, "run"):
                logger.warning(
                    "Optional module '%s' has no run() — skipped.", import_path
                )
                continue
            logger.info("Running optional module: %s", import_path)
            result = mod.run(df, report)
            if isinstance(result, dict):
                report[report_key] = result
                logger.info(
                    "'%s' added %d key(s) under report['%s'].",
                    import_path, len(result), report_key,
                )
        except ModuleNotFoundError:
            logger.debug("Optional module '%s' not installed — skipped.", import_path)
        except Exception as exc:  # noqa: BLE001
            # Never let an optional module crash the pipeline.
            logger.warning(
                "Optional module '%s' raised an error and was skipped: %s",
                import_path, exc,
            )

    return report


def step_save_report(report: dict[str, Any], output_path: Path) -> None:
    """Gate 6 — persist the report to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    logger.info("Report saved → %s", output_path.resolve())


def step_print_summary(report: dict[str, Any], df: pd.DataFrame) -> None:
    """Gate 7 — human-readable terminal summary. Read-only; never mutates."""
    stats    = report.get("statistics", {})
    insights = report.get("insights",   {})

    sep = "─" * 62
    print(f"\n{sep}")
    print("   BANK STATEMENT ANALYSIS — SUMMARY")
    print(sep)
    print(f"  Total transactions    : {stats.get('transaction_count', len(df)):,}")

    if "date" in df.columns and df["date"].notna().any():
        print(
            f"  Date range            : "
            f"{df['date'].min().date()}  →  {df['date'].max().date()}"
        )

    if "total_debit" in insights:
        print(f"  Total debits          : {insights['total_debit']:,.2f}")
    if "total_credit" in insights:
        print(f"  Total credits         : {insights['total_credit']:,.2f}")
    if "net_cash_flow" in insights:
        print(f"  Net cash flow         : {insights['net_cash_flow']:,.2f}")
    closing_balance = insights.get("closing_balance")

    if closing_balance is not None:
        print(f"  Closing balance       : {closing_balance:,.2f}")
    else:
        print("  Closing balance       : N/A")
    avg = insights.get("average_daily_spending")
    if avg is not None:
        print(f"  Avg daily spending    : {avg:,.2f}")
    else:
        print("  Avg daily spending    : N/A")
    if "top_merchants" in insights and insights["top_merchants"]:
        top = insights["top_merchants"]
        top_name = top[0].get("merchant", "—") if isinstance(top[0], dict) else top[0]
        print(f"  Top merchant          : {top_name}")

    # Optional module results
    if "risk" in report:
        risk_summary = report['risk'].get('summary', report['risk'])
        flag_count = risk_summary.get('flagged_count', risk_summary.get('flag_count', '—'))
        print(f"  Risk flags            : {flag_count}")
    if "anomalies" in report:
        print(f"  Anomalies detected    : {report['anomalies'].get('anomaly_count', '—')}")
    if "llm" in report and report["llm"].get("summary"):
        snippet = str(report["llm"]["summary"])[:280]
        print(f"\n  AI Summary:\n  {snippet}")

    print(sep)
    print(f"  Full report           : analytics_report.json")
    print(f"{sep}\n")


# ===========================================================================
# CLI
# ===========================================================================

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="app.py",
        description="AI-Powered Bank Statement Analysis Platform",
    )
    parser.add_argument(
        "csv_path",
        type=Path,
        help="Path to the bank-statement CSV file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("analytics_report.json"),
        metavar="FILE",
        help="Output path for the JSON report (default: analytics_report.json).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args(argv)


# ===========================================================================
# MAIN
# ===========================================================================

def main(argv: list[str] | None = None) -> int:
    """
    Orchestrate the full pipeline. Returns 0 on success, 1 on handled error.

    All business logic is delegated to service modules.
    This function only sequences steps and handles top-level exceptions.
    """
    args = _parse_args(argv)
    logging.getLogger().setLevel(args.log_level.upper())

    logger.info("=== Bank Statement Analysis Platform — START ===")

    try:
        step_validate_file(args.csv_path)
        records = step_standardize(args.csv_path)
        df      = step_to_dataframe(records)
        report  = step_analytics(df)
        report  = step_optional_services(df, report)
        step_save_report(report, args.output)
        step_print_summary(report, df)

    except FileNotFoundError as exc:
        logger.error("File error: %s", exc)
        return 1
    except ValueError as exc:
        logger.error("Validation error: %s", exc)
        return 1
    except TypeError as exc:
        logger.error("Type contract violated: %s", exc)
        return 1
    except ImportError as exc:
        logger.error(
            "Missing service module — ensure services/ is in the same "
            "directory as app.py and contains __init__.py.\n  Detail: %s", exc
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: %s", exc)
        return 1

    logger.info("=== Bank Statement Analysis Platform — DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
