"""PDFGenerator — exports InsightReport to a styled PDF using reportlab or weasyprint.

Real-time design:
    PDF generation runs in a thread pool executor. The generator emits
    ``report:page_complete`` Socket.IO events as each section is rendered
    so the frontend shows "Generating page 1/4…" progress during exports.

Rendering strategy (priority order):
    1. weasyprint (HTML→PDF) — best quality; requires wkhtmltopdf binary
    2. reportlab — pure Python; available everywhere
    3. Fallback — returns a plain-text PDF-like bytes blob

PDF structure (4 pages):
    Page 1: Cover — dataset name, date, completeness score
    Page 2: Executive Summary + KPIs
    Page 3: Insights (5 ranked)
    Page 4: Recommendations + Anomaly count
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def export_to_pdf(
    report: dict[str, Any],
    dataset_name: str = "Dataset",
    sio: Any = None,
    dataset_id: str = "",
) -> bytes:
    """Generate a PDF from an InsightReport dict.

    Args:
        report:       InsightReport.to_dict() output.
        dataset_name: Human-readable dataset name for the cover page.
        sio:          Socket.IO server for progress events.
        dataset_id:   Dataset UUID for room targeting.

    Returns:
        Raw PDF bytes.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _render_pdf, report, dataset_name, sio, dataset_id, loop
    )


def _render_pdf(
    report: dict,
    dataset_name: str,
    sio,
    dataset_id: str,
    loop,
) -> bytes:
    """Synchronous PDF rendering (runs in thread pool)."""

    def _emit(page: int, label: str) -> None:
        if sio and dataset_id:
            try:
                asyncio.run_coroutine_threadsafe(
                    sio.emit(
                        "report:page_complete",
                        {"dataset_id": dataset_id, "page": page, "label": label},
                        room=f"dataset:{dataset_id}",
                    ),
                    loop,
                )
            except Exception:
                pass

    # Try reportlab first (most commonly available)
    try:
        return _render_reportlab(report, dataset_name, _emit)
    except ImportError:
        pass

    # Fallback: plain-text pseudo-PDF
    return _render_text_fallback(report, dataset_name)


def _render_reportlab(report: dict[str, Any], dataset_name: str, emit_fn: Any) -> bytes:
    """Render using reportlab (pure Python PDF library)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    violet = colors.HexColor("#5B4FE8")
    navy = colors.HexColor("#1A1A3E")
    light = colors.HexColor("#F5F4F1")

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    story  = []

    # ── Styles ────────────────────────────────────────────────────────────
    h1 = ParagraphStyle("H1", parent=styles["Heading1"],
                         textColor=navy, fontSize=22, spaceAfter=12)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"],
                         textColor=violet, fontSize=14, spaceAfter=8)
    body = ParagraphStyle("Body", parent=styles["Normal"],
                          fontSize=10, leading=14, spaceAfter=6)

    # ── Cover ─────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 3*cm),
        Paragraph("DataPilot Analysis Report", h1),
        Paragraph(dataset_name, ParagraphStyle(
            "Subtitle", parent=h1, fontSize=16, textColor=violet
        )),
        Spacer(1, 1*cm),
        Paragraph(
            f"Generated: {datetime.utcnow().strftime('%B %d, %Y')} | "
            f"Insights: {report.get('insight_count', len(report.get('insights', [])))} | "
            f"Anomalies: {len(report.get('anomaly_alerts', []))}",
            body
        ),
        HRFlowable(width="100%", color=violet, thickness=2),
        Spacer(1, 2*cm),
    ]
    emit_fn(1, "Cover")

    # ── Executive Summary ─────────────────────────────────────────────────
    story += [Paragraph("Executive Summary", h2)]
    summary = report.get("executive_summary", "No summary available.")
    for para in summary.split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), body))

    story.append(Spacer(1, 0.5*cm))

    # KPIs table
    kpis = report.get("kpis", [])[:6]
    if kpis:
        story.append(Paragraph("Key Metrics", h2))
        kpi_data = [["Metric", "Value"]] + [
            [k.get("name", ""), str(k.get("value", ""))]
            for k in kpis
        ]
        kpi_table = Table(kpi_data, colWidths=[8*cm, 8*cm])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), VIOLET),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, colors.white]),
            ("GRID",       (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ]))
        story.append(kpi_table)

    story.append(Spacer(1, 0.5*cm))
    emit_fn(2, "Executive Summary")

    # ── Insights ──────────────────────────────────────────────────────────
    story.append(Paragraph("Key Insights", h2))
    for i, ins in enumerate(report.get("insights", [])[:5], start=1):
        impact = ins.get("business_impact", "medium").upper()
        story += [
            Paragraph(f"{i}. {ins.get('headline', '')}", ParagraphStyle(
                f"InsH{i}", parent=body, fontName="Helvetica-Bold",
                textColor=VIOLET if i == 1 else NAVY
            )),
            Paragraph(
                f"{ins.get('explanation', '')} "
                f"[Impact: {impact} | Confidence: {float(ins.get('confidence', 0.8)):.0%}]",
                body
            ),
            Spacer(1, 0.3*cm),
        ]
    emit_fn(3, "Insights")

    # ── Recommendations ───────────────────────────────────────────────────
    story.append(Paragraph("Recommendations", h2))
    for i, rec in enumerate(report.get("recommendations", []), start=1):
        impact = rec.get("estimated_impact", {})
        impact_str = (
            f"{impact.get('min_pct', 0):.0f}–{impact.get('max_pct', 0):.0f}%"
            if isinstance(impact, dict) else str(impact)
        )
        story += [
            Paragraph(
                f"{i}. [{rec.get('priority', '').upper()}] {rec.get('title', '')}",
                ParagraphStyle(f"RecH{i}", parent=body, fontName="Helvetica-Bold", textColor=NAVY)
            ),
            Paragraph(rec.get("action", ""), body),
            Paragraph(f"Estimated improvement: {impact_str}", ParagraphStyle(
                f"ImpactP{i}", parent=body, textColor=VIOLET
            )),
            Spacer(1, 0.3*cm),
        ]
    emit_fn(4, "Recommendations")

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _render_text_fallback(report: dict, dataset_name: str) -> bytes:
    """Minimal text-based PDF fallback when reportlab is not installed."""
    lines = [
        "DATAPILOT ANALYSIS REPORT",
        f"Dataset: {dataset_name}",
        f"Generated: {datetime.utcnow().isoformat()}",
        "",
        "EXECUTIVE SUMMARY",
        report.get("executive_summary", ""),
        "",
        "KEY INSIGHTS",
    ]
    for i, ins in enumerate(report.get("insights", [])[:5], start=1):
        lines.append(f"{i}. {ins.get('headline', '')}")
        lines.append(f"   {ins.get('explanation', '')}")
    return "\n".join(lines).encode("utf-8")
