"""HypothesisTester — statistical tests for group differences and independence."""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class HypothesisTester:
    """Runs t-tests, ANOVA, and chi-square tests."""

    def t_test(self, df, numeric_col: str, group_col: str) -> dict:
        """Run Welch's t-test between the first two groups in group_col."""
        try:
            from scipy import stats
            groups = df.groupby(group_col)[numeric_col].apply(list)
            if len(groups) < 2:
                return {}
            g1, g2   = list(groups.iloc[0]), list(groups.iloc[1])
            t_stat, p_val = stats.ttest_ind(g1, g2, equal_var=False)
            return {
                "test":        "Welch's t-test",
                "t_statistic": round(float(t_stat), 6),
                "p_value":     round(float(p_val), 6),
                "significant": bool(p_val < 0.05),
                "groups":      [str(groups.index[0]), str(groups.index[1])],
            }
        except Exception as exc:
            logger.debug("t_test_failed", error=str(exc))
            return {}

    def chi_square(self, df, col_a: str, col_b: str) -> dict:
        """Run a chi-square test of independence between two categorical columns."""
        try:
            from scipy import stats
            import pandas as pd
            contingency = pd.crosstab(df[col_a], df[col_b])
            chi2, p_val, dof, _ = stats.chi2_contingency(contingency)
            return {
                "test":        "Chi-square",
                "chi2":        round(float(chi2), 6),
                "p_value":     round(float(p_val), 6),
                "dof":         int(dof),
                "significant": bool(p_val < 0.05),
            }
        except Exception as exc:
            logger.debug("chi_square_failed", error=str(exc))
            return {}
