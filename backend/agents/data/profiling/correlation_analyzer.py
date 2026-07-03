"""CorrelationAnalyzer — computes and streams pairwise correlations.

Real-time design:
    For a dataset with 20 numeric columns, there are 190 pairwise correlations.
    Rather than computing all at once and emitting one event, the analyzer
    emits a ``correlation:pair_complete`` event after each significant pair
    is computed so the frontend can render a live-updating correlation heatmap.

    Results are filtered to |r| ≥ min_abs_r to avoid flooding the Socket.IO
    channel with weak correlations that the user doesn't care about.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from backend.analytics_engine.statistics.correlation_engine import (
    CorrelationEngine,
    CorrelationCoefficient,
)

logger = structlog.get_logger(__name__)


class CorrelationAnalyzer:
    """Computes pairwise Pearson correlations with real-time Socket.IO events.

    Args:
        min_abs_r:   Minimum |r| to report (default 0.3 to filter weak correlations).
        sio:         Socket.IO server for real-time pair events.
        dataset_id:  Dataset UUID for room targeting.
    """

    def __init__(
        self,
        min_abs_r: float = 0.3,
        sio: Any = None,
        dataset_id: str = "",
    ) -> None:
        self._engine    = CorrelationEngine(min_abs_r=min_abs_r)
        self._sio       = sio
        self._dataset_id = dataset_id

    async def analyze(
        self,
        df,
        numeric_columns: list[str],
    ) -> list[dict]:
        """Compute pairwise correlations and emit real-time pair events.

        Args:
            df:              Polars or pandas DataFrame.
            numeric_columns: List of numeric column names to correlate.

        Returns:
            List of correlation dicts sorted by |r| descending.
        """
        if len(numeric_columns) < 2:
            return []

        # Run correlation computation in thread pool (CPU-bound numpy)
        loop    = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._engine.compute,
            df,
            numeric_columns,
        )

        dicts = []
        for corr in results:
            d = self._to_dict(corr)
            dicts.append(d)

            # Emit per-pair real-time event
            if self._sio and self._dataset_id:
                try:
                    await self._sio.emit(
                        "correlation:pair_complete",
                        {
                            "dataset_id": self._dataset_id,
                            **d,
                        },
                        room=f"dataset:{self._dataset_id}",
                    )
                except Exception:
                    pass

        logger.info(
            "correlation_analysis_complete",
            numeric_columns=len(numeric_columns),
            significant_pairs=len(dicts),
            min_r=self._engine._min_r,
        )
        return dicts

    def analyze_sync(self, df, numeric_columns: list[str]) -> list[dict]:
        """Synchronous version for use inside thread pool callbacks."""
        if len(numeric_columns) < 2:
            return []
        results = self._engine.compute(df, numeric_columns)
        return [self._to_dict(r) for r in results]

    @staticmethod
    def _to_dict(corr: CorrelationCoefficient) -> dict:
        r = corr.value
        return {
            "column_a":  corr.column_a,
            "column_b":  corr.column_b,
            "r":         r,
            "r_squared": round(r ** 2, 6),
            "strength":  (
                "very_strong" if abs(r) >= 0.9
                else "strong"  if abs(r) >= 0.7
                else "moderate"
            ),
            "direction": "positive" if r > 0 else "negative",
            "sample_n":  getattr(corr, "sample_size", 0),
        }
