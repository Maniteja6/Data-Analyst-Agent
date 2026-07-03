"""Forecast Agent eval suite — tests trend detection quality."""
from __future__ import annotations

import json
from pathlib import Path

import structlog

logger = structlog.get_logger("eval.forecast")


class ForecastAgentEval:
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
                    suite="forecast", case_id=case["id"], passed=False, score=0.0,
                    details={"error": str(exc)}
                ))
        return results

    async def _run_case(self, case: dict):
        from backend.tests.evals.eval_runner import EvalResult
        from backend.analytics_engine.statistics.trend_analyzer import TrendAnalyzer
        import pandas as pd

        data       = case["input"]["data"]
        date_col   = case["input"]["date_col"]
        value_col  = case["input"]["value_col"]
        expected   = case.get("expected_direction", "")

        df     = pd.DataFrame(data)
        result = TrendAnalyzer().detect_trend(df, date_col, value_col)
        direction = result.get("direction", "unknown")
        passed    = direction == expected

        return EvalResult(
            suite="forecast", case_id=case["id"], passed=passed,
            score=1.0 if passed else 0.0,
            details={"detected_direction": direction, "expected": expected, "r_squared": result.get("r_squared")}
        )
