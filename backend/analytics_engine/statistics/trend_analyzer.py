"""TrendAnalyzer — linear trend detection and time-series decomposition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)


class TrendAnalyzer:
    """Detects trends in time-series numeric columns."""

    def detect_trend(self, df: DataFrameT, date_col: str, value_col: str) -> dict[str, Any]:
        """Fit a linear trend to a time-series column.

        Returns slope, R², and direction.
        """
        try:
            import numpy as np
            import pandas as pd
            import polars as pl

            # Get pandas Series regardless of input type
            if isinstance(df, pl.DataFrame):
                dates = pd.to_datetime(df[date_col].to_list())
                values = df[value_col].to_list()
            else:
                dates = pd.to_datetime(df[date_col])
                values = df[value_col].values

            df_pd = pd.DataFrame({"date": dates, "value": values}).dropna().sort_values("date")
            if len(df_pd) < 3:
                return {}

            # Convert dates to ordinal numbers for linear regression
            x = df_pd["date"].map(lambda d: d.toordinal()).values
            y = df_pd["value"].values

            slope, intercept = np.polyfit(x, y, 1)
            y_pred = slope * x + intercept
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            pct_change = (y_pred[-1] - y_pred[0]) / abs(y_pred[0]) * 100 if y_pred[0] != 0 else 0
            direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"

            return {
                "slope": round(float(slope), 8),
                "r_squared": round(float(r_squared), 6),
                "direction": direction,
                "pct_change": round(float(pct_change), 2),
                "data_points": len(df_pd),
                "is_significant": bool(r_squared > 0.5),
            }
        except Exception as exc:
            logger.debug("trend_detection_failed", error=str(exc))
            return {}
