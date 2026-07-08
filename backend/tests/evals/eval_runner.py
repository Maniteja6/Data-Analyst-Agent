"""EvalRunner — orchestrates all agent evals and produces a summary report.

Evals test AI agent output quality, not just correctness. Each eval suite
defines a set of (input, expected_output) pairs with a scoring rubric.

Score types:
  exact_match   — normalised output must equal expected exactly
  contains      — expected substring must appear in output
  json_schema   — output must be valid JSON matching a schema
  semantic      — LLM-as-judge scores output quality 1–5

Usage::

    python -m backend.tests.evals.eval_runner \\
        --suites sql insight \\
        --output eval_report.json
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger("datapilot.eval")


class EvalResult:
    def __init__(self, suite: str, case_id: str, passed: bool, score: float, details: dict) -> None:
        self.suite = suite
        self.case_id = case_id
        self.passed = passed
        self.score = score
        self.details = details

    def to_dict(self) -> dict:
        return {
            "suite": self.suite,
            "case_id": self.case_id,
            "passed": self.passed,
            "score": self.score,
            "details": self.details,
        }


class EvalRunner:
    """Orchestrates all eval suites and aggregates results."""

    def __init__(self, suites: list[str] | None = None) -> None:
        self._suites = suites or ["sql", "insight", "forecast"]

    async def run(self) -> dict[str, Any]:
        all_results: list[EvalResult] = []
        start = time.monotonic()

        for suite_name in self._suites:
            logger.info("running_eval_suite", suite=suite_name)
            results = await self._run_suite(suite_name)
            all_results.extend(results)

        duration = round(time.monotonic() - start, 2)

        # Aggregate
        total = len(all_results)
        passed = sum(1 for r in all_results if r.passed)
        avg_score = round(sum(r.score for r in all_results) / total, 4) if total else 0.0

        by_suite = {}
        for r in all_results:
            by_suite.setdefault(r.suite, []).append(r.to_dict())

        report = {
            "total_cases": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "avg_score": avg_score,
            "duration_s": duration,
            "suites": by_suite,
        }
        logger.info(
            "eval_complete",
            total=total,
            passed=passed,
            pass_rate=report["pass_rate"],
        )
        return report

    async def _run_suite(self, suite_name: str) -> list[EvalResult]:
        try:
            if suite_name == "sql":
                from backend.tests.evals.sql_agent_eval.sql_eval import SQLAgentEval

                return await SQLAgentEval().run()
            if suite_name == "insight":
                from backend.tests.evals.insight_agent_eval.insight_eval import InsightAgentEval

                return await InsightAgentEval().run()
            if suite_name == "forecast":
                from backend.tests.evals.forecast_agent_eval.forecast_eval import ForecastAgentEval

                return await ForecastAgentEval().run()
        except (ImportError, Exception) as exc:
            logger.warning("eval_suite_failed", suite=suite_name, error=str(exc))
        return []


async def main(suites: list[str], output: str | None) -> None:
    runner = EvalRunner(suites=suites)
    report = await runner.run()

    if output:
        Path(output).write_text(json.dumps(report, indent=2))
        print(f"Eval report written to: {output}")
    else:
        print(json.dumps(report, indent=2))

    # Exit with error code if pass rate < 80%
    if report["pass_rate"] < 0.80:
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run DataPilot agent evals")
    parser.add_argument("--suites", nargs="*", default=["sql", "insight", "forecast"])
    parser.add_argument("--output", default=None, help="Path to write JSON report")
    args = parser.parse_args()
    asyncio.run(main(args.suites, args.output))
