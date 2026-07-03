"""AnomalyDetector — orchestrates all four detection methods.

The AnomalyDetector is the single entry point called by the analytics
pipeline. It runs the appropriate detectors for each column based on its
kind and semantic type, then deduplicates overlapping results and returns
a unified, ranked list of anomaly dicts.

Detection strategy per column type
-----------------------------------
Numeric (non-currency, non-count):
    ZScore (threshold=3.0) + IQR (multiplier=1.5) + Rule

Currency / monetary:
    ZScore (threshold=3.5) + IQR (multiplier=2.0) + Rule (negative check)

Count:
    Rule (non-integer, negative) + ZScore

Percentage:
    Rule (range bounds)

Date / Datetime:
    Rule (year range)

Email:
    Rule (format check)

All numeric columns (when ≥ 2 numeric cols exist):
    IsolationForest (multivariate) — runs once across all numeric columns together

Deduplication:
    A row flagged by both Z-score and IQR produces only one anomaly entry;
    the higher-confidence result is kept. Deduplication is keyed on
    (column_name, row_index, anomaly_type).

Usage::

    detector = AnomalyDetector()
    anomalies = await detector.detect(df, profile=data_profile)
    # returns list[dict] suitable for AnomalyAlert entity construction
"""
from __future__ import annotations

from typing import Any

import structlog

from backend.analytics_engine.anomaly_detection.zscore_detector     import ZScoreDetector
from backend.analytics_engine.anomaly_detection.iqr_detector        import IQRDetector
from backend.analytics_engine.anomaly_detection.isolation_forest    import IsolationForestDetector
from backend.analytics_engine.anomaly_detection.rule_detector       import RuleDetector
from backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


class AnomalyDetector:
    """Orchestrates IQR, Z-score, Isolation Forest, and rule-based detection.

    Args:
        zscore_threshold:         Z-score boundary for flagging outliers.
        iqr_multiplier:           Tukey fence multiplier.
        if_contamination:         Expected anomaly fraction for Isolation Forest.
        run_isolation_forest:     Whether to run the multivariate detector.
        max_anomalies_per_column: Cap per-column results to avoid report noise.
    """

    def __init__(
        self,
        zscore_threshold: float | None = None,
        iqr_multiplier: float | None = None,
        if_contamination: float | None = None,
        run_isolation_forest: bool = True,
        max_anomalies_per_column: int = 50,
    ) -> None:
        settings = get_settings()
        self._zscore_threshold   = zscore_threshold  or settings.anomaly_zscore_threshold
        self._iqr_multiplier     = iqr_multiplier    or settings.anomaly_iqr_multiplier
        self._if_contamination   = if_contamination  or settings.anomaly_isolation_forest_contamination
        self._run_if             = run_isolation_forest
        self._max_per_col        = max_anomalies_per_column

    # ── Primary entry point ───────────────────────────────────────────────

    async def detect(self, df, profile=None) -> list[dict]:
        """Run all applicable detectors and return deduplicated anomaly dicts.

        Args:
            df:      Cleaned DataFrame (polars or pandas) after the cleaning stage.
            profile: Optional DataProfile entity; used to read per-column
                     ``semantic_type`` and ``kind`` to route detectors correctly.
                     Falls back to dtype-based inference when None.

        Returns:
            List of anomaly dicts sorted by severity then confidence, descending.
        """
        import asyncio

        column_meta = self._extract_column_meta(df, profile)
        all_results: list[dict] = []

        # ── Per-column detection (Z-score + IQR + Rule) ───────────────────
        for col_name, meta in column_meta.items():
            col_results = self._detect_column(df, col_name, meta)
            all_results.extend(col_results)

        # ── Multivariate detection (Isolation Forest) ─────────────────────
        if self._run_if:
            numeric_cols = [
                c for c, m in column_meta.items()
                if m.get("kind") in ("numeric", "currency", "count")
            ]
            if len(numeric_cols) >= 2:
                try:
                    if_detector = IsolationForestDetector(
                        contamination=self._if_contamination,
                        max_results=self._max_per_col * 2,
                    )
                    if_results  = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: if_detector.to_anomaly_dicts(df, numeric_cols),
                    )
                    all_results.extend(if_results)
                    logger.info(
                        "isolation_forest_run",
                        columns=numeric_cols,
                        found=len(if_results),
                    )
                except Exception as exc:
                    logger.warning("isolation_forest_skipped", error=str(exc))

        # ── Deduplicate and rank ───────────────────────────────────────────
        deduped = self._deduplicate(all_results)
        ranked  = self._rank(deduped)

        logger.info(
            "anomaly_detection_complete",
            total_raw=len(all_results),
            after_dedup=len(ranked),
            column_count=len(column_meta),
        )
        return ranked

    # ── Per-column detection ──────────────────────────────────────────────

    def _detect_column(
        self, df, column: str, meta: dict
    ) -> list[dict]:
        """Run appropriate detectors for one column and return raw results."""
        kind    = meta.get("kind",          "unknown")
        stype   = meta.get("semantic_type", "unknown")
        results: list[dict] = []

        if kind not in ("numeric",) and stype not in (
            "currency", "numeric_measure", "numeric_count", "percentage"
        ):
            # Run rule checks for non-numeric semantic types
            rule_detector = RuleDetector(max_results=self._max_per_col)
            results.extend(rule_detector.detect(df, column, stype))
            return results

        # Numeric column: Z-score
        try:
            threshold = (
                3.5 if stype == "currency"
                else 4.0 if stype == "numeric_count"
                else self._zscore_threshold
            )
            z_detector = ZScoreDetector(threshold=threshold, max_results=self._max_per_col)
            results.extend(z_detector.to_anomaly_dicts(column, df))
        except Exception as exc:
            logger.debug("zscore_failed", column=column, error=str(exc))

        # Numeric column: IQR
        try:
            multiplier = 2.0 if stype == "currency" else self._iqr_multiplier
            iqr_detector = IQRDetector(multiplier=multiplier, max_results=self._max_per_col)
            results.extend(iqr_detector.to_anomaly_dicts(column, df))
        except Exception as exc:
            logger.debug("iqr_failed", column=column, error=str(exc))

        # All numeric types: domain rules
        try:
            rule_detector = RuleDetector(max_results=self._max_per_col)
            results.extend(rule_detector.detect(df, column, stype))
        except Exception as exc:
            logger.debug("rule_check_failed", column=column, error=str(exc))

        return results

    # ── Deduplication ─────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(results: list[dict]) -> list[dict]:
        """Keep the highest-confidence anomaly per (column, row_index, type)."""
        seen: dict[tuple, dict] = {}
        for r in results:
            key = (
                r.get("column", ""),
                r.get("row_index", -1),
                r.get("anomaly_type", ""),
            )
            existing = seen.get(key)
            if existing is None or r.get("confidence", 0) > existing.get("confidence", 0):
                seen[key] = r
        return list(seen.values())

    # ── Ranking ───────────────────────────────────────────────────────────

    @staticmethod
    def _rank(results: list[dict]) -> list[dict]:
        """Sort anomalies by severity → confidence descending."""
        _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def _sort_key(r: dict) -> tuple:
            sev  = _SEVERITY_ORDER.get(r.get("severity", "low"), 3)
            conf = -float(r.get("confidence", 0.5))
            return (sev, conf)

        return sorted(results, key=_sort_key)

    # ── Column metadata extraction ────────────────────────────────────────

    @staticmethod
    def _extract_column_meta(df, profile) -> dict[str, dict]:
        """Build a {column_name: {kind, semantic_type}} lookup.

        Uses the DataProfile entity when available; falls back to dtype
        inspection when profile is None (e.g. in unit tests).
        """
        meta: dict[str, dict] = {}

        if profile is not None:
            for col in getattr(profile, "column_profiles", []):
                kind  = getattr(col, "kind",          None)
                stype = getattr(col, "semantic_type", None)
                if hasattr(kind,  "value"):
                    kind  = kind.value
                if hasattr(stype, "value"):
                    stype = stype.value
                meta[col.column_name] = {
                    "kind":          kind  or "unknown",
                    "semantic_type": stype or "unknown",
                }
            return meta

        # Fallback: infer from dtypes
        try:
            import polars as pl
            if isinstance(df, pl.DataFrame):
                for col in df.columns:
                    dtype = df[col].dtype
                    if dtype in (pl.Float32, pl.Float64, pl.Int32, pl.Int64,
                                 pl.Int8, pl.Int16, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
                        meta[col] = {"kind": "numeric", "semantic_type": "numeric_measure"}
                    elif dtype == pl.Utf8:
                        meta[col] = {"kind": "text", "semantic_type": "unknown"}
                    elif dtype == pl.Boolean:
                        meta[col] = {"kind": "boolean", "semantic_type": "boolean"}
                    elif dtype in (pl.Date, pl.Datetime):
                        meta[col] = {"kind": "datetime", "semantic_type": "datetime"}
                    else:
                        meta[col] = {"kind": "unknown", "semantic_type": "unknown"}
                return meta
        except ImportError:
            pass

        # pandas fallback
        import numpy as np
        for col in df.columns:
            dtype = df[col].dtype
            if np.issubdtype(dtype, np.number):
                meta[col] = {"kind": "numeric", "semantic_type": "numeric_measure"}
            elif np.issubdtype(dtype, np.datetime64):
                meta[col] = {"kind": "datetime", "semantic_type": "datetime"}
            else:
                meta[col] = {"kind": "text", "semantic_type": "unknown"}
        return meta
