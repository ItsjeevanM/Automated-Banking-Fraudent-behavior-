"""
services/report_generator.py
------------------------------
Presentation layer only. Reads structured dicts produced by upstream modules
and renders a professional PDF report using ReportLab Platypus + matplotlib.
No analytics, no fraud logic, no calculations belong here.

Public interface (called by app.py):
    run(df, report) -> dict
    Returns:
        { "generated": True, "pdf_path": str, "pages": int }
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette  (professional blue / grey)
# ---------------------------------------------------------------------------
C_NAVY      = colors.HexColor("#1B3A6B")
C_BLUE      = colors.HexColor("#2563EB")
C_LIGHT_BLUE= colors.HexColor("#EFF6FF")
C_GREY      = colors.HexColor("#6B7280")
C_LIGHT_GREY= colors.HexColor("#F3F4F6")
C_WHITE     = colors.white
C_RED       = colors.HexColor("#DC2626")
C_ORANGE    = colors.HexColor("#EA580C")
C_GREEN     = colors.HexColor("#16A34A")
C_YELLOW    = colors.HexColor("#D97706")

PDF_OUTPUT_DIR = Path("results")

# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------
def _styles() -> dict[str, ParagraphStyle]:
    """Return a dict of all custom paragraph styles."""
    base = getSampleStyleSheet()

    def _s(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "cover_title":   _s("CoverTitle",   fontSize=32, leading=40,
                             textColor=C_NAVY, alignment=TA_CENTER,
                             fontName="Helvetica-Bold", spaceAfter=8),
        "cover_sub":     _s("CoverSub",     fontSize=14, leading=20,
                             textColor=C_GREY, alignment=TA_CENTER,
                             fontName="Helvetica"),
        "cover_date":    _s("CoverDate",    fontSize=11, leading=16,
                             textColor=C_GREY, alignment=TA_CENTER),
        "section_head":  _s("SectionHead",  fontSize=16, leading=22,
                             textColor=C_NAVY, fontName="Helvetica-Bold",
                             spaceBefore=18, spaceAfter=6),
        "sub_head":      _s("SubHead",      fontSize=12, leading=18,
                             textColor=C_NAVY, fontName="Helvetica-Bold",
                             spaceBefore=10, spaceAfter=4),
        "body":          _s("Body",         fontSize=10, leading=15,
                             textColor=colors.black, alignment=TA_JUSTIFY),
        "body_small":    _s("BodySmall",    fontSize=9,  leading=13,
                             textColor=C_GREY),
        "warning":       _s("Warning",      fontSize=9,  leading=14,
                             textColor=C_RED, leftIndent=8),
        "kv_key":        _s("KVKey",        fontSize=10, leading=14,
                             textColor=C_GREY, fontName="Helvetica-Bold"),
        "kv_val":        _s("KVVal",        fontSize=11, leading=15,
                             textColor=C_NAVY, fontName="Helvetica-Bold"),
        "footer":        _s("Footer",       fontSize=8,  leading=12,
                             textColor=C_GREY, alignment=TA_CENTER),
    }

def _std_table_style(n_rows: int) -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),

        ("ROWBACKGROUNDS", (0, 1), (-1, n_rows-1),
         [C_WHITE, C_LIGHT_BLUE]),

        ("GRID", (0, 0), (-1, -1), 0.3, C_LIGHT_GREY),

        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),

        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),

        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])

def _divider() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5,
                      color=C_LIGHT_GREY, spaceAfter=6, spaceBefore=2)

def _na(value: Any, fmt: str = "{}") -> str:
    """Return formatted value or 'N/A' if falsy."""
    if value is None or value == "" or value != value:   # handles NaN
        return "N/A"
    try:
        return fmt.format(value)
    except Exception:
        return str(value)

def _currency(value: Any) -> str:
    try:
        return f"₹{float(value):,.2f}"
    except Exception:
        return "N/A"

def _risk_colour(risk: str) -> colors.Color:
    mapping = {
        "CRITICAL": C_RED, "Very High": C_RED,
        "HIGH":     C_ORANGE, "High": C_ORANGE,
        "MEDIUM":   C_YELLOW, "Medium": C_YELLOW,
        "LOW":      C_GREEN,  "Low": C_GREEN,
    }
    return mapping.get(str(risk).strip(), C_GREY)

# ---------------------------------------------------------------------------
# Chart generators  (each returns a tmp PNG path)
# ---------------------------------------------------------------------------
def _tmpfile(suffix: str = ".png") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path

def generate_bar_chart(
    labels: list[str],
    debit_vals: list[float],
    credit_vals: list[float],
    title: str,
    output_path: str,
) -> str:
    """Grouped bar chart: debits vs credits per label."""
    fig, ax = plt.subplots(figsize=(9, 3.6))
    x = range(len(labels))
    w = 0.38

    ax.bar([i - w / 2 for i in x], debit_vals,  width=w,
           color="#2563EB", label="Debits",  alpha=0.9)
    ax.bar([i + w / 2 for i in x], credit_vals, width=w,
           color="#16A34A", label="Credits", alpha=0.9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"₹{v/1000:.0f}k" if abs(v) >= 1000 else f"₹{v:.0f}"))

    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
    ax.legend(fontsize=8)

    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return output_path

def generate_line_chart(
    labels: list[str],
    values: list[float],
    title: str,
    output_path: str,
    colour: str = "#2563EB",
    fill: bool = True,
) -> str:
    """Simple line chart."""
    fig, ax = plt.subplots(figsize=(9, 3.0))

    ax.plot(range(len(labels)), values, color=colour,
            linewidth=2, marker="o", markersize=3)
    if fill:
        ax.fill_between(range(len(labels)), values,
                        alpha=0.12, color=colour)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"₹{v/1000:.0f}k" if abs(v) >= 1000 else f"₹{v:.0f}"))

    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)

    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return output_path

def generate_pie_chart(
    labels: list[str],
    values: list[float],
    title: str,
    output_path: str,
) -> str:
    """Pie / donut chart."""
    palette = ["#2563EB", "#16A34A", "#EA580C",
               "#D97706", "#7C3AED", "#0891B2"]

    fig, ax = plt.subplots(figsize=(5, 3.8))
    # pyrefly: ignore [bad-unpacking]
    wedges, texts, autotexts = ax.pie(
        values, labels=None, autopct="%1.1f%%",
        colors=palette[: len(values)],
        pctdistance=0.78,
        wedgeprops={"width": 0.55, "edgecolor": "white", "linewidth": 1.5},
    )

    for at in autotexts:
        at.set_fontsize(7)

    ax.legend(
        wedges, labels,
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        fontsize=7,
    )

    ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    fig.patch.set_facecolor("white")

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return output_path

# ---------------------------------------------------------------------------
# PDF section builders
# ---------------------------------------------------------------------------
def create_cover_page(story: list, st: dict, report_id: str) -> None:
    """Page 1 — cover."""
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Financial Intelligence Report", st["cover_title"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "AI-Powered Bank Statement Analysis Platform",
        st["cover_sub"],
    ))
    story.append(Spacer(1, 1.2 * cm))

    now = datetime.now(timezone.utc).strftime("%B %d, %Y  %H:%M UTC")
    story.append(Paragraph(f"Generated: {now}", st["cover_date"]))
    story.append(Paragraph(f"Report ID: {report_id}", st["cover_date"]))

    story.append(Spacer(1, 3 * cm))
    story.append(HRFlowable(
        width="60%", thickness=3, color=C_BLUE,
        hAlign="CENTER", spaceAfter=12,
    ))
    story.append(Paragraph(
        "CONFIDENTIAL — FOR AUTHORISED USE ONLY",
        st["cover_sub"],
    ))
    story.append(PageBreak())

def create_executive_summary(story: list, st: dict, llm_output: dict) -> None:
    """Page 2 — executive summary from LLM output."""
    story.append(Paragraph("Executive Summary", st["section_head"]))
    story.append(_divider())

    summary = llm_output.get("summary", "") or ""
    if not summary.strip():
        summary = "No AI summary available for this report."

    # 1. Escape HTML first so we don't break ReportLab XML parser
    summary_clean = html.escape(summary)

    # 2. Re-apply bold and italics safely
    summary_clean = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", summary_clean)
    summary_clean = re.sub(r"(?<!^)\*(.+?)\*(?!$)", r"<i>\1</i>", summary_clean, flags=re.MULTILINE)
    
    # 3. Remove markdown headings
    summary_clean = re.sub(r"#{1,6}\s*", "", summary_clean)

    for para in summary_clean.split("\n\n"):
        para = para.strip()
        if para:
            if para.startswith("* ") or para.startswith("-   ") or para.startswith("•"):
                for line in para.split("\n"):
                    line = line.lstrip("*-• \t")
                    if line:
                        story.append(Paragraph(f"• {line}", st["body"]))
                        story.append(Spacer(1, 2))
            else:
                story.append(Paragraph(para, st["body"]))
                story.append(Spacer(1, 6))

    story.append(PageBreak())

def create_financial_overview(
    story: list, st: dict, analytics: dict, tmp_files: list) -> None:
    """Page 3 — financial overview with KPI cards + charts."""
    story.append(Paragraph("Financial Overview", st["section_head"]))
    story.append(_divider())

    kpi_data = [
        ["Metric", "Value", "Metric", "Value"],
        ["Total Transactions",         _na(analytics.get("transaction_count"), "{:,}"),
         "Net Cash Flow",         _currency(analytics.get("net_cash_flow"))],
        ["Total Debits",         _currency(analytics.get("total_debit")),
         "Closing Balance",         _currency(analytics.get("closing_balance"))],
        ["Total Credits",         _currency(analytics.get("total_credit")),
         "Avg Daily Spending",         _currency(analytics.get("average_daily_spending"))],
        ["Largest Debit",         _currency(analytics.get("largest_debit")),
         "Largest Credit",         _currency(analytics.get("largest_credit"))],
        ["Median Transaction",         _currency(analytics.get("median_transaction")),
         "Avg Transaction",         _currency(analytics.get("average_transaction"))],
    ]

    kpi_style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("FONTNAME",      (1, 1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (1, 1), (-1, -1), C_NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_LIGHT_BLUE]),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_LIGHT_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])

    page_w = A4[0] - 3.6 * cm
    kpi_table = Table(kpi_data,
                      colWidths=[page_w * 0.28, page_w * 0.22,
                                 page_w * 0.28, page_w * 0.22])
    kpi_table.setStyle(kpi_style)
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    dc = analytics.get("debit_credit_breakdown", {})
    if dc.get("debit") and dc.get("credit"):
        story.append(Paragraph("Debit vs Credit Breakdown", st["sub_head"]))
        d_total = dc["debit"].get("total", 0)
        c_total = dc["credit"].get("total", 0)
        d_count = dc["debit"].get("count", 0)
        c_count = dc["credit"].get("count", 0)

        bar_data = [
            ["", "Debits", "Credits"],
            ["Total Amount", _currency(d_total), _currency(c_total)],
            ["Transaction Count", str(d_count), str(c_count)],
            ["% by Count",
             f"{dc['debit'].get('pct_by_count', 0):.1f}%",
             f"{dc['credit'].get('pct_by_count', 0):.1f}%"],
        ]

        small_style = TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_LIGHT_BLUE]),
            ("GRID",          (0, 0), (-1, -1), 0.3, C_LIGHT_GREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
        bt = Table(bar_data,
                   colWidths=[page_w * 0.33, page_w * 0.33, page_w * 0.33])
        bt.setStyle(small_style)
        story.append(bt)
        story.append(Spacer(1, 10))

    monthly = analytics.get("monthly_transaction_trends", [])
    if monthly:
        try:
            labels     = [m["month"] for m in monthly]
            deb_vals   = [m.get("total_debit", 0) for m in monthly]
            cred_vals  = [m.get("total_credit", 0) for m in monthly]

            img_path   = _tmpfile()
            tmp_files.append(img_path)
            generate_bar_chart(
                labels, deb_vals, cred_vals,
                "Monthly Debit vs Credit",
                img_path,
            )
            story.append(Paragraph("Monthly Transaction Trends", st["sub_head"]))
            story.append(Image(img_path, width=page_w, height=page_w * 0.38))
            story.append(Spacer(1, 10))
        except Exception as e:
            logger.warning("Monthly chart failed: %s", e)

    # ── Monthly spending trend (debit-only line chart) ───────────────────
    spending_trends = analytics.get("spending_trends", {})
    monthly_spending = spending_trends.get("monthly_spending", [])
    if monthly_spending and len(monthly_spending) > 1:
        try:
            sp_labels = [r["month"] for r in monthly_spending]
            sp_vals   = [r.get("total_debit", 0) for r in monthly_spending]

            img_path = _tmpfile()
            tmp_files.append(img_path)
            generate_line_chart(
                sp_labels, sp_vals,
                "Monthly Spending Trend (Debits)",
                img_path,
                colour="#EA580C",
                fill=True,
            )
            story.append(Paragraph("Monthly Spending Trend", st["sub_head"]))
            story.append(Image(img_path, width=page_w, height=page_w * 0.34))
            story.append(Spacer(1, 10))
        except Exception as e:
            logger.warning("Spending trend chart failed: %s", e)

    merchants = analytics.get("merchant_summary", {}).get("merchants", [])[:5]
    if merchants:
        try:
            m_labels = [m.get("merchant", "?")[:18] for m in merchants]
            m_vals   = [m.get("total_amount", 0) for m in merchants]

            img_path = _tmpfile()
            tmp_files.append(img_path)
            generate_bar_chart(
                m_labels, m_vals, [0] * len(m_vals),
                "Top 5 Merchants by Spend",
                img_path,
            )
            story.append(Paragraph("Top Merchants", st["sub_head"]))
            story.append(Image(img_path, width=page_w, height=page_w * 0.38))
            story.append(Spacer(1, 6))
        except Exception as e:
            logger.warning("Merchant chart failed: %s", e)

    txn_dist = analytics.get("transaction_type_distribution", [])
    if txn_dist:
        try:
            t_labels = [t.get("transaction_type", "?") for t in txn_dist]
            t_vals   = [t.get("count", 0) for t in txn_dist]

            img_path = _tmpfile()
            tmp_files.append(img_path)
            generate_pie_chart(
                t_labels, t_vals,
                "Transaction Type Distribution",
                img_path,
            )
            story.append(Paragraph("Transaction Type Distribution", st["sub_head"]))
            story.append(Image(img_path, width=page_w * 0.55,
                               height=page_w * 0.42, hAlign="CENTER"))
        except Exception as e:
            logger.warning("Pie chart failed: %s", e)

    story.append(PageBreak())

def create_fraud_section(
    story: list, st: dict, report_data: dict, tmp_files: list) -> None:
    """Fraud & Risk analysis — reads only from report_data."""
    story.append(Paragraph("Fraud & Risk Analysis", st["section_head"]))
    story.append(_divider())

    fraud = report_data.get("fraud", {})
    flagged_count = fraud.get("flagged_count", "N/A")
    amount_at_risk = fraud.get("amount_at_risk")
    risk_dist = fraud.get("risk_distribution", {})

    summary_data = [
        ["Flagged Transactions", "Amount at Risk"],
        [
            _na(flagged_count, "{:,}") if isinstance(flagged_count, int) else str(flagged_count),
            _currency(amount_at_risk),
        ],
    ]

    page_w = A4[0] - 3.6 * cm
    sum_style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 10),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 1), (-1, -1), 16),
        ("TEXTCOLOR",     (0, 1), (-1, -1), C_NAVY),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_LIGHT_GREY),
    ])

    st_table = Table(summary_data, colWidths=[page_w * 0.5, page_w * 0.5])
    st_table.setStyle(sum_style)
    story.append(st_table)
    story.append(Spacer(1, 12))

    if risk_dist:
        story.append(Paragraph("Risk Distribution", st["sub_head"]))
        rd_data = [["Risk Category", "Transaction Count"]]
        for level, count in risk_dist.items():
            rd_data.append([level, str(count)])

        rd_style = _std_table_style(n_rows=len(rd_data))
        rd_table = Table(rd_data, colWidths=[page_w * 0.55, page_w * 0.45])
        rd_table.setStyle(rd_style)

        for i, (level, _) in enumerate(risk_dist.items(), start=1):
            rc = _risk_colour(level)
            rd_table.setStyle(TableStyle([
                ("TEXTCOLOR", (0, i), (0, i), rc),
                ("FONTNAME",  (0, i), (0, i), "Helvetica-Bold"),
            ]))

        try:
            pie_labels = list(risk_dist.keys())
            pie_vals   = [float(v) for v in risk_dist.values()]
            if any(v > 0 for v in pie_vals):
                img_path = _tmpfile()
                tmp_files.append(img_path)
                generate_pie_chart(
                    pie_labels, pie_vals,
                    "Risk Distribution",
                    img_path,
                )
                combined = Table(
                    [[rd_table, Image(img_path, width=page_w * 0.46, height=page_w * 0.35)]],
                    colWidths=[page_w * 0.52, page_w * 0.48],
                )
                combined.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]))
                story.append(combined)
            else:
                story.append(rd_table)
        except Exception as e:
            logger.warning("Risk pie failed: %s", e)
            story.append(rd_table)
        story.append(Spacer(1, 14))

    top_txns = fraud.get("top_10_flagged_transactions", [])
    if top_txns:
        story.append(Paragraph("Top Flagged Transactions", st["sub_head"]))
        headers = ["#", "Date", "Merchant", "Amount",
                   "Risk Score", "Category", "Fraud Type", "Flags"]
        rows = [headers]

        for i, t in enumerate(top_txns, 1):
            date_str = str(t.get("date", ""))[:10]
            merchant = str(t.get("merchant", "N/A"))[:18]
            amount   = _currency(t.get("amount"))
            score    = f"{t.get('final_risk_score', 0):.1f}"
            category = str(t.get("risk_category", "N/A"))
            ftype    = str(t.get("fraud_type", "N/A"))[:16]
            
            # Catching either format of rules
            raw_flags = t.get("rule_flags", t.get("flags", []))
            if isinstance(raw_flags, str):
                flags_str = raw_flags
            else:
                flags_str = ", ".join(raw_flags)
            flags = flags_str.replace("_TRANSACTION", "").replace("_ALERT", "")

            rows.append([str(i), date_str, merchant, amount,
                         score, category, ftype, flags])

        col_w = [page_w * w for w in [0.04, 0.10, 0.15, 0.10, 0.09, 0.10, 0.13, 0.29]]
        txn_table = Table(rows, colWidths=col_w, repeatRows=1)
        txn_table.setStyle(_std_table_style(n_rows=len(rows)))

        for i, t in enumerate(top_txns, 1):
            rc = _risk_colour(t.get("risk_category", ""))
            txn_table.setStyle(TableStyle([
                ("TEXTCOLOR", (5, i), (5, i), rc),
                ("FONTNAME",  (5, i), (5, i), "Helvetica-Bold"),
            ]))

        story.append(txn_table)
        story.append(Spacer(1, 8))

        story.append(Paragraph("Transaction Reason Details", st["sub_head"]))
        for i, t in enumerate(top_txns, 1):
            reason = str(t.get("reason", "")).strip()
            if reason:
                safe_merchant = html.escape(str(t.get('merchant', '')))
                safe_reason = html.escape(reason)
                story.append(Paragraph(
                    f"<b>#{i} {safe_merchant}:</b> {safe_reason}",
                    st["body_small"],
                ))
                story.append(Spacer(1, 3))

    story.append(PageBreak())

def create_cashflow_section(
    story: list, st: dict, cashflow: dict, tmp_files: list) -> None:
    """Cashflow analysis — reads only from cashflow dict."""
    story.append(Paragraph("Cashflow Analysis", st["section_head"]))
    story.append(_divider())

    metrics  = cashflow.get("metrics",  {})
    forecast = cashflow.get("forecast", {})
    meta     = cashflow.get("metadata", {})
    warnings = cashflow.get("warnings", [])

    page_w = A4[0] - 3.6 * cm
    risk_level = forecast.get("risk_classification", "N/A")
    rc = _risk_colour(risk_level)

    cf_data = [
        ["Metric", "Value"],
        ["Current Balance",        _currency(metrics.get("current_balance"))],
        ["Estimated Daily Spending",_currency(metrics.get("estimated_daily_spending"))],
        ["Median Daily Spending",   _currency(metrics.get("median_daily_spending"))],
        ["Runway Days",             _na(forecast.get("runway_days"), "{:,}")],
        ["Depletion Date",          _na(forecast.get("depletion_date"))],
        ["Cashflow Risk Level",     str(risk_level)],
        ["Forecast Confidence",     _na(meta.get("confidence_level"))],
        ["Statement Period",         f"{_na(metrics.get('statement_start'))} → {_na(metrics.get('statement_end'))}"],
    ]

    cf_style = _std_table_style(n_rows=len(cf_data))
    cf_table = Table(cf_data, colWidths=[page_w * 0.55, page_w * 0.45])
    cf_table.setStyle(cf_style)

    for i, row in enumerate(cf_data):
        if row[0] == "Cashflow Risk Level":
            cf_table.setStyle(TableStyle([
                ("TEXTCOLOR", (1, i), (1, i), rc),
                ("FONTNAME",  (1, i), (1, i), "Helvetica-Bold"),
            ]))

    story.append(cf_table)
    story.append(Spacer(1, 12))

    proj = forecast.get("projected_balances", [])
    if proj and len(proj) > 1:
        try:
            p_labels = [p.get("date", "")[:10] for p in proj]
            p_vals   = [p.get("projected_balance", 0) for p in proj]

            img_path = _tmpfile()
            tmp_files.append(img_path)
            generate_line_chart(
                p_labels, p_vals,
                "Projected Balance (90-Day Forecast)",
                img_path,
                colour="#DC2626",
                fill=True,
            )
            story.append(Paragraph("Balance Forecast", st["sub_head"]))
            story.append(Image(img_path, width=page_w, height=page_w * 0.36))
            story.append(Spacer(1, 10))
        except Exception as e:
            logger.warning("Cashflow chart failed: %s", e)

    if warnings:
        story.append(Paragraph("Cashflow Warnings", st["sub_head"]))
        for w in warnings:
            story.append(Paragraph(f"⚠  {html.escape(w)}", st["warning"]))
            story.append(Spacer(1, 3))

    story.append(PageBreak())

def create_recommendation_section(
    story: list, st: dict, llm_output: dict) -> None:
    """Recommendations from LLM output."""
    story.append(Paragraph("Recommendations", st["section_head"]))
    story.append(_divider())

    summary = llm_output.get("summary", "") or ""
    
    rec_match = re.search(
        r"(?:6\.|###\s*6\.|Recommendations?)(.*)",
        summary,
        re.DOTALL | re.IGNORECASE,
    )
    rec_text = rec_match.group(1).strip() if rec_match else ""

    if rec_text:
        rec_clean = html.escape(rec_text)
        rec_clean = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", rec_clean)
        rec_clean = re.sub(r"#{1,6}\s*", "", rec_clean)

        for line in rec_clean.split("\n"):
            line = line.strip()
            if not line:
                continue

            if re.match(r"^\d+\.", line) or line.startswith("*") or line.startswith("-"):
                line = re.sub(r"^\d+\.\s*", "", line).lstrip("*- ").strip()
                story.append(Paragraph(f"• {line}", st["body"]))
                story.append(Spacer(1, 4))
            else:
                story.append(Paragraph(line, st["body"]))
                story.append(Spacer(1, 4))
    else:
        story.append(Paragraph(
            "Recommendations are embedded in the Executive Summary above.",
            st["body_small"],
        ))

    story.append(PageBreak())

def create_system_information(
    story: list, st: dict, llm_output: dict, report_id: str) -> None:
    """Final page — system metadata."""
    story.append(Paragraph("System Information", st["section_head"]))
    story.append(_divider())

    now = datetime.now(timezone.utc).isoformat()
    info = [
        ["Field", "Value"],
        ["Generated At",    now],
        ["Report ID",       report_id],
        ["Report Version",  "1.0.0"],
        ["LLM Provider",    llm_output.get("provider",
                            llm_output.get("model_used", "N/A"))],
        ["LLM Model",       llm_output.get("model_used",
                            llm_output.get("model", "N/A"))],
        ["LLM Status",      llm_output.get("status", "N/A")],
        ["Platform",        "AI-Powered Bank Statement Analysis Platform"],
    ]

    page_w = A4[0] - 3.6 * cm
    info_table = Table(info, colWidths=[page_w * 0.38, page_w * 0.62])
    info_table.setStyle(_std_table_style(n_rows=len(info)))
    story.append(info_table)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "This report was generated automatically. "
        "All findings should be verified by a qualified financial analyst before acting upon them.",
        st["body_small"],
    ))

# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------
def build_pdf(
    analytics:   dict[str, Any],
    cashflow:    dict[str, Any],
    report_data: dict[str, Any],
    llm_output:  dict[str, Any],
    output_path: Path,
) -> int:
    """Assemble all sections, build the PDF, return page count."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_id  = str(uuid.uuid4())[:8].upper()
    st         = _styles()
    tmp_files: list[str] = []

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
        title="Financial Intelligence Report",
        author="AI Bank Statement Analysis Platform",
    )

    story: list = []

    try:
        create_cover_page(story, st, report_id)
        create_executive_summary(story, st, llm_output)
        create_financial_overview(story, st, analytics, tmp_files)
        create_fraud_section(story, st, report_data, tmp_files)
        create_cashflow_section(story, st, cashflow, tmp_files)
        create_recommendation_section(story, st, llm_output)
        create_system_information(story, st, llm_output, report_id)
        
        doc.build(story)
    finally:
        for f in tmp_files:
            try:
                os.remove(f)
            except OSError:
                pass

    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(output_path)).pages)
    except Exception:
        pages = -1

    return pages

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run(df: Any, report: dict[str, Any]) -> dict[str, Any]:
    # ── analytics: the full statistics block (has monthly_transaction_trends,
    # merchant_summary, transaction_type_distribution, spending_trends, etc.)
    analytics = report.get("statistics", {})

    # ── cashflow: direct output of cashflow_predictor (metrics/forecast/warnings)
    cashflow = report.get("cashflow", {})

    # ── report_data for fraud section: build from the actual fraud block
    # app.py stores fraud under report["fraud"] with keys:
    #   summary.flagged_count, summary.total_amount_at_risk,
    #   summary.risk_distribution, flagged_transactions []
    # llm_sender compacts these into report["llm_input"]["fraud"] with keys:
    #   flagged_count, amount_at_risk, risk_distribution,
    #   top_10_flagged_transactions []
    # create_fraud_section expects the llm_sender compact format,
    # so prefer llm_input when available, fall back to building it.
    llm_input = report.get("llm_input", {})
    if llm_input.get("fraud"):
        report_data = llm_input
    else:
        # Synthesise the compact fraud dict from the raw fraud block
        raw_fraud = report.get("fraud", {})
        raw_summary = raw_fraud.get("summary", {})
        raw_flagged = raw_fraud.get("flagged_transactions", [])
        compact_fraud = {
            "flagged_count":               raw_summary.get("flagged_count",
                                           raw_summary.get("flagged_transactions", 0)),
            "amount_at_risk":              raw_summary.get("total_amount_at_risk"),
            "risk_distribution":           raw_summary.get("risk_distribution", {}),
            "top_10_flagged_transactions": [
                {
                    "transaction_index": t.get("transaction_index"),
                    "date":              t.get("date"),
                    "merchant":          t.get("merchant"),
                    "amount":            t.get("amount"),
                    "risk_category":     t.get("risk_category"),
                    "final_risk_score":  t.get("final_risk_score", t.get("risk_score", 0)),
                    "fraud_type":        t.get("fraud_type_predicted", t.get("transaction_type")),
                    "flags":             t.get("flags", t.get("reasons", [])),
                    "reason":            t.get("combined_reason",
                                         "; ".join(t.get("reasons", []))),
                }
                for t in raw_flagged[:10]
            ],
        }
        report_data = {"fraud": compact_fraud}

    # ── llm_output: the Gemini result dict (has summary, status, etc.)
    llm_output = report.get("gemini", report.get("llm", {}))
    # Normalise: create_executive_summary expects llm_output.get("summary")
    if not isinstance(llm_output, dict):
        llm_output = {"summary": str(llm_output)}
    elif "summary" not in llm_output and "text" in llm_output:
        llm_output = {**llm_output, "summary": llm_output["text"]}

    pdf_path = PDF_OUTPUT_DIR / "financial_intelligence_report.pdf"

    try:
        pages = build_pdf(
            analytics   = analytics,
            cashflow    = cashflow,
            report_data = report_data,
            llm_output  = llm_output,
            output_path = pdf_path,
        )

        logger.info(
            "report_generator: PDF saved → %s  (%d pages)",
            pdf_path.resolve(), pages,
        )

        return {
            "generated": True,
            "pdf_path":  str(pdf_path.resolve()),
            "pages":     pages,
        }
    except Exception as exc:
        logger.error("report_generator: PDF generation failed: %s", exc)
        return {
            "generated": False,
            "pdf_path":  None,
            "pages":     0,
            "error":     str(exc),
        }