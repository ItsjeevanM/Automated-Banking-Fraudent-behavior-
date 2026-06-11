"""
services/report_generator.py
----------------------------
Formats, organizes, and generates the final structured analysis report.

This module is strictly a presentation layer. It does not compute statistics,
perform analysis, or recalculate values from the raw DataFrame. It consumes
the aggregated findings from analytics, risk, and anomaly engines to build
a comprehensive human- and machine-readable document.
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class StructuredReport:
    """Defines the final structured output schema of the report generator."""
    executive_summary: str
    financial_insights: str
    merchant_analysis: str
    trend_analysis: str
    transaction_type_analysis: str
    risk_assessment: str
    anomaly_summary: str
    suspicious_transactions: list[dict[str, Any]]
    recommendations: list[str]


class ReportGenerator:
    """
    Consumes pipeline analytics and generates structured reports.
    Designed for extensibility: individual build_* methods can easily be 
    swapped out for LLM-generated strings in the future.
    """

    def __init__(self, data: dict[str, Any]):
        """
        Initialize the generator with the aggregated pipeline data.
        """
        self.data = data
        self.insights = data.get("insights", {})
        self.stats = data.get("statistics", {})
        self.risk = data.get("risk", {})
        self.anomalies = data.get("anomalies", {})
        self.llm_data = data.get("llm", {})
        
        # Defensively search for suspicious transactions across all likely namespaces
        self.suspicious = (
            data.get("suspicious_transactions") 
            or self.risk.get("suspicious_transactions") 
            or self.anomalies.get("suspicious_transactions") 
            or []
        )

    def build_executive_summary(self) -> str:
        """Construct the executive summary using key metrics."""
        if "executive_summary" in self.llm_data:
            return self.llm_data["executive_summary"]

        count = self.stats.get("transaction_count", "N/A")
        debit = self.insights.get("total_debit") or self.stats.get("total_debit", 0.0)
        credit = self.insights.get("total_credit") or self.stats.get("total_credit", 0.0)
        net_flow = self.insights.get("net_cash_flow") or self.stats.get("net_cash_flow", 0.0)
        risk_level = self.risk.get("risk_level") or self.risk.get("level", "Unknown")

        summary = (
            f"The analyzed statement contains {count} transactions. "
            f"Total cash outflow (debits) amounted to {debit:,.2f}, while total inflow (credits) "
            f"was {credit:,.2f}, resulting in a net cash flow of {net_flow:,.2f}. "
            f"The preliminary automated risk assessment has classified this account's "
            f"activity as '{risk_level}' risk."
        )
        return summary

    def build_financial_insights(self) -> str:
        """Construct a detailed overview of basic transaction metrics and balances."""
        if "financial_insights" in self.llm_data:
            return self.llm_data["financial_insights"]

        avg_txn = self.insights.get("average_transaction") or self.stats.get("average_transaction") or 0.0
        med_txn = self.insights.get("median_transaction") or self.stats.get("median_transaction") or 0.0
        largest_debit = self.insights.get("largest_debit") or self.stats.get("largest_debit") or 0.0
        largest_credit = self.insights.get("largest_credit") or self.stats.get("largest_credit") or 0.0
        
        # New additions
        closing_balance = self.insights.get("closing_balance") or self.stats.get("closing_balance")
        avg_daily = self.insights.get("average_daily_spending") or self.stats.get("average_daily_spending")

        lines = [
            "Financial Overview & Key Values:",
            f"• Average Transaction Amount: {avg_txn:,.2f}",
            f"• Median Transaction Amount: {med_txn:,.2f}",
            f"• Largest Debit Amount: {largest_debit:,.2f}",
            f"• Largest Credit Amount: {largest_credit:,.2f}",
        ]
        
        if closing_balance is not None:
            lines.append(f"• Closing Balance: {closing_balance:,.2f}")
        if avg_daily is not None:
            lines.append(f"• Average Daily Spending: {avg_daily:,.2f}")

        return "\n".join(lines)

    def build_merchant_analysis(self) -> str:
        """Construct an overview of counterparty/merchant volume and frequency."""
        if "merchant_analysis" in self.llm_data:
            return self.llm_data["merchant_analysis"]
            
        merchant_summary = self.stats.get("merchant_summary", {})
        top_merchants = self.insights.get("top_merchants", [])
        
        total_unique = merchant_summary.get("total_unique_merchants", 0)
        
        lines = [
            f"Total Unique Merchants Identified: {total_unique}",
            "",
            "Top Merchants by Volume:"
        ]
        
        if not top_merchants:
            lines.append("• No specific merchant data available.")
        else:
            for i, m in enumerate(top_merchants, 1):
                name = m.get("merchant", "Unknown")
                total = m.get("total_amount", 0.0)
                count = m.get("count", 0)
                avg = m.get("avg_amount", 0.0)
                lines.append(
                    f"{i}. {name} — Total: {total:,.2f} | Txns: {count} | Avg: {avg:,.2f}"
                )
                
        return "\n".join(lines)

    def build_trend_analysis(self) -> str:
        """Constructs an overview of spending changes and monthly aggregates."""
        if "trend_analysis" in self.llm_data:
            return self.llm_data["trend_analysis"]
            
        wow_pct = self.insights.get("wow_change_pct")
        mom_pct = self.insights.get("mom_change_pct")
        monthly_trends = self.stats.get("monthly_transaction_trends", [])
        
        lines = ["Spending Momentum:"]
        
        if wow_pct is not None:
            direction = "increase" if wow_pct > 0 else "decrease"
            lines.append(f"• Week-over-Week Change: {abs(wow_pct)}% {direction}")
        if mom_pct is not None:
            direction = "increase" if mom_pct > 0 else "decrease"
            lines.append(f"• Month-over-Month Change: {abs(mom_pct)}% {direction}")
            
        lines.append("\nMonthly Aggregates:")
        if not monthly_trends:
            lines.append("• No monthly trends calculated.")
        else:
            for m in monthly_trends:
                month = m.get("month", "Unknown")
                debit = m.get("total_debit", 0.0)
                credit = m.get("total_credit", 0.0)
                net = m.get("net", 0.0)
                lines.append(f"• [{month}] Debits: {debit:,.2f} | Credits: {credit:,.2f} | Net Flow: {net:,.2f}")
                
        return "\n".join(lines)

    def build_transaction_type_analysis(self) -> str:
        """Constructs an overview of transaction categories (e.g., UPI, IMPS, POS)."""
        if "transaction_type_analysis" in self.llm_data:
            return self.llm_data["transaction_type_analysis"]
            
        tx_distribution = self.stats.get("transaction_type_distribution", [])
        
        lines = ["Transaction Type Distribution:"]
        
        if not tx_distribution:
            lines.append("• No transaction types identified.")
        else:
            for dist in tx_distribution:
                tx_type = dist.get("transaction_type", "Unknown")
                count = dist.get("count", 0)
                pct = dist.get("pct", 0.0)
                lines.append(f"• {tx_type}: {count} transactions ({pct}%)")
                
        return "\n".join(lines)

    def build_risk_assessment(self) -> str:
        """Format the findings from the risk engine using cautious language."""
        if "risk_assessment" in self.llm_data:
            return self.llm_data["risk_assessment"]

        score = self.risk.get("overall_risk_score") or self.risk.get("risk_score", "N/A")
        level = self.risk.get("risk_level") or self.risk.get("level", "Unknown")
        findings = self.risk.get("risk_findings") or self.risk.get("findings", [])

        lines = [
            f"Automated Risk Score: {score} / 100",
            f"Assessed Risk Level: {level}",
            "",
            "Observations requiring potential review:"
        ]

        if not findings:
            lines.append("• No immediate high-risk patterns observed.")
        else:
            for finding in findings:
                lines.append(f"• {finding}")
                
        lines.append("\nNote: These findings indicate unusual activity observed by automated rules "
                     "and require manual verification. They do not confirm illicit activity.")

        return "\n".join(lines)

    def build_anomaly_summary(self) -> str:
        """Summarizes anomalous behaviors detected by the anomaly engine."""
        if "anomaly_summary" in self.llm_data:
            return self.llm_data["anomaly_summary"]

        total = self.anomalies.get("anomaly_count", 0)
        high = self.anomalies.get("high_severity", 0)
        med = self.anomalies.get("medium_severity", 0)
        low = self.anomalies.get("low_severity", 0)

        return (
            f"Anomaly Detection identified {total} outlier events. "
            f"Severity breakdown — High: {high}, Medium: {med}, Low: {low}. "
            "These deviations from historical patterns may warrant further investigation."
        )

    def build_suspicious_transaction_section(self) -> list[dict[str, Any]]:
        """Returns the raw list of suspicious transactions, capped at 20."""
        safe_list = self.suspicious if isinstance(self.suspicious, list) else []
        return safe_list[:20]

    def build_recommendations(self) -> list[str]:
        """Generates actionable, generic recommendations."""
        if "recommendations" in self.llm_data:
            return self.llm_data["recommendations"]

        recommendations = []
        risk_level = str(self.risk.get("risk_level") or self.risk.get("level", "")).lower()
        anomaly_count = self.anomalies.get("anomaly_count", 0)
        suspicious_count = len(self.build_suspicious_transaction_section())

        recommendations.append("Conduct standard reconciliation of the provided statement.")

        if risk_level in ["high", "critical"]:
            recommendations.append("Prioritize an immediate manual review of all high-risk flagged transactions.")
            recommendations.append("Verify counterparties associated with large or unusual fund transfers.")
            
        if anomaly_count > 5:
            recommendations.append("Monitor unusual cash flow patterns; historical transaction baselines have been exceeded.")
            
        if suspicious_count > 0:
            recommendations.append(f"Investigate the {suspicious_count} specific transactions flagged with high combined risk scores.")

        return recommendations

    def generate_report(self) -> dict[str, Any]:
        """Aggregates all built sections into the final structured dictionary."""
        report = StructuredReport(
            executive_summary=self.build_executive_summary(),
            financial_insights=self.build_financial_insights(),
            merchant_analysis=self.build_merchant_analysis(),
            trend_analysis=self.build_trend_analysis(),
            transaction_type_analysis=self.build_transaction_type_analysis(),
            risk_assessment=self.build_risk_assessment(),
            anomaly_summary=self.build_anomaly_summary(),
            suspicious_transactions=self.build_suspicious_transaction_section(),
            recommendations=self.build_recommendations(),
        )
        return asdict(report)

    def export_text(self) -> str:
        """Converts the generated report dictionary into a human-readable text document."""
        data = self.generate_report()
        
        lines = [
            "==================================================",
            "      BANK STATEMENT ANALYSIS FINAL REPORT        ",
            "==================================================",
            "\n[ EXECUTIVE SUMMARY ]",
            data["executive_summary"],
            "\n[ FINANCIAL INSIGHTS ]",
            data["financial_insights"],
            "\n[ MERCHANT ANALYSIS ]",
            data["merchant_analysis"],
            "\n[ TREND ANALYSIS ]",
            data["trend_analysis"],
            "\n[ TRANSACTION TYPE ANALYSIS ]",
            data["transaction_type_analysis"],
            "\n[ RISK ASSESSMENT ]",
            data["risk_assessment"],
            "\n[ ANOMALY SUMMARY ]",
            data["anomaly_summary"],
            "\n[ SUSPICIOUS TRANSACTIONS ]"
        ]
        
        txns = data["suspicious_transactions"]
        if not txns:
            lines.append("No highly suspicious transactions flagged.")
        else:
            for t in txns:
                t_date = t.get("date", "Unknown Date")
                t_id = t.get("transaction_id", "Unknown ID")
                t_amt = t.get("amount", 0.0)
                t_score = t.get("combined_score", "N/A")
                t_flags = ", ".join(t.get("flags", []))
                lines.append(
                    f" - Date: {t_date} | ID: {t_id} | Amt: {t_amt} | "
                    f"Score: {t_score} | Flags: {t_flags}"
                )
        
        lines.append("\n[ RECOMMENDATIONS ]")
        for i, rec in enumerate(data["recommendations"], 1):
            lines.append(f"{i}. {rec}")
            
        lines.append("\n==================================================")
        return "\n".join(lines)

    def export_json(self) -> str:
        """Exports the structured report as a JSON string."""
        return json.dumps(self.generate_report(), indent=2, default=str)


def run(df: pd.DataFrame, report: dict[str, Any]) -> dict[str, Any]:
    """Standard entry point for app.py's optional service pipeline."""
    logger.info("Report Generator initialized.")
    generator = ReportGenerator(report)
    
    structured_output = generator.generate_report()
    structured_output["_text_render"] = generator.export_text()
    
    # Development override to output a standalone JSON file
    import json
    from pathlib import Path
    debug_file = Path("debug_report_generator_output.json") 
    with debug_file.open("w", encoding="utf-8") as f:
        json.dump(structured_output, f, indent=2, default=str)
        
    return structured_output