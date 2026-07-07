"""Report agent — multi-format report rendering and S3 upload.

Formats: PDF (reportlab, 4 pages), XLSX (openpyxl, 5 sheets),
         PPTX (python-pptx, 7 slides), JSON (raw InsightReport dict).
All rendering runs in ThreadPoolExecutor; emits page/sheet/slide events.
ReportAgent uploads to S3 and emits report:ready with a 15-minute presigned URL.
"""

from backend.agents.output.report.excel_exporter import export_to_excel
from backend.agents.output.report.pdf_generator import export_to_pdf
from backend.agents.output.report.pptx_generator import export_to_pptx
from backend.agents.output.report.report_agent import ReportAgent

__all__ = ["ReportAgent", "export_to_pdf", "export_to_excel", "export_to_pptx"]
