"""Insight Agent eval suite — tests KPI and insight generation."""
from __future__ import annotations

import json
from pathlib import Path

import structlog

logger = structlog.get_logger("eval.insight")


class InsightAgentEval:
    TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"

    async def run(self):
        from backend.tests.evals.eval_runner import EvalResult
        cases   = json.loads(self.TEST_CASES_PATH.read_text())
        results = []
        for case in cases:
            try:
                results.append(await self._run_case(case))
            except Exception as exc:
                results.append(EvalResult(
                    suite="insight", case_id=case["id"], passed=False, score=0.0,
                    details={"error": str(exc)}
                ))
        return results

    async def _run_case(self, case: dict):
        from backend.tests.evals.eval_runner import EvalResult
        from backend.domain.insight.services.kpi_calculator import KPICalculator

        class _Profile:
            def __getattr__(self, k): return case["input"].get("profile", {}).get(k)
            @property
            def column_profiles(self): return []

        profile = _Profile()
        kpis    = KPICalculator().calculate("r1", profile)
        names   = [k.name for k in kpis]
        expected_names = case.get("expected_kpi_names", [])
        passed  = all(n in names for n in expected_names) if expected_names else len(kpis) > 0
        return EvalResult(
            suite="insight", case_id=case["id"], passed=passed, score=1.0 if passed else 0.0,
            details={"kpi_names": names, "expected": expected_names}
        )
