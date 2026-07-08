"""DistributionFitter — identifies the best-fitting statistical distribution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

    DataFrameT = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)

# Distributions tested in order of complexity
_DISTRIBUTIONS = ["norm", "expon", "lognorm", "gamma", "beta"]


class DistributionFitter:
    """Fits scipy distributions to numeric columns and returns the best fit."""

    def fit(self, df: DataFrameT, column: str) -> dict:
        """Return the best-fitting distribution name and parameters."""
        try:
            from scipy import stats as scipy_stats

            try:
                vals = df[column].drop_nulls().to_numpy()
            except Exception:
                vals = df[column].dropna().to_numpy()

            if len(vals) < 30:
                return {"distribution": "unknown", "params": {}}

            best_name = "unknown"
            best_pval = 0.0
            best_ksstat = float("inf")

            for dist_name in _DISTRIBUTIONS:
                try:
                    dist = getattr(scipy_stats, dist_name)
                    params = dist.fit(vals)
                    ks_stat, p_val = scipy_stats.kstest(vals, dist_name, args=params)
                    if ks_stat < best_ksstat:
                        best_ksstat = ks_stat
                        best_pval = p_val
                        best_name = dist_name
                except Exception as exc:
                    logger.debug(
                        "distribution_fit_attempt_failed", distribution=dist_name, error=str(exc)
                    )
                    continue

            return {
                "distribution": best_name,
                "ks_statistic": round(best_ksstat, 6),
                "p_value": round(best_pval, 6),
                "is_good_fit": best_pval > 0.05,
            }
        except ImportError:
            return {"distribution": "unknown", "params": {}, "reason": "scipy not installed"}
        except Exception as exc:
            logger.debug("distribution_fit_failed", column=column, error=str(exc))
            return {"distribution": "unknown", "params": {}}
