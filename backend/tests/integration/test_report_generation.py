"""Integration test: report rendering (XLSX/JSON without Bedrock)."""

import pytest


@pytest.mark.integration
class TestReportRendering:
    @pytest.mark.asyncio
    async def test_json_render(self) -> None:
        from backend.infrastructure.job_queue.tasks.report_tasks import _render_report

        sample = {
            "id": "r1",
            "dataset_id": "d1",
            "session_id": "s1",
            "executive_summary": "Test summary.",
            "insights": [{"headline": "Revenue is growing", "business_impact": "high"}],
            "kpis": [],
            "anomaly_alerts": [],
            "forecasts": [],
            "recommendations": [],
        }
        rendered = await _render_report(sample, "json")
        import json

        data = json.loads(rendered.decode())
        assert data["executive_summary"] == "Test summary."

    @pytest.mark.asyncio
    async def test_xlsx_render_produces_bytes(self) -> None:
        from backend.infrastructure.job_queue.tasks.report_tasks import _render_xlsx

        sample = {
            "kpis": [{"name": "Revenue", "value": {"raw": 1000}}],
            "insights": [],
            "anomaly_alerts": [],
            "recommendations": [],
        }
        try:
            rendered = await _render_xlsx(sample)
            assert len(rendered) > 0
            assert rendered[:4] == b"PK\x03\x04"  # XLSX is a ZIP
        except ImportError:
            pytest.skip("openpyxl not installed")


@pytest.mark.integration
class TestResultFormatter:
    def test_markdown_table_from_rows(self) -> None:
        from backend.analytics_engine.sql_engine.result_formatter import ResultFormatter

        rows = [{"region": "North", "revenue": 5000}, {"region": "South", "revenue": 3000}]
        md = ResultFormatter().to_markdown_table(rows)
        assert "North" in md
        assert "revenue" in md
        assert "---" in md

    def test_summarise_single_value(self) -> None:
        from backend.analytics_engine.sql_engine.result_formatter import ResultFormatter

        rows = [{"total": 42000}]
        summary = ResultFormatter().summarise(rows)
        assert "42000" in summary or "Result" in summary
