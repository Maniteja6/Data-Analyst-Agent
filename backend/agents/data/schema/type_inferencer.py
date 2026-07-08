"""Rule-based semantic type inferencer — zero LLM calls, < 1ms per column.

Real-time design:
    TypeInferencer runs synchronously on every column immediately after
    FileReader loads the dataset. Because it uses only polars dtypes and
    column name keyword matching — no network calls — it never adds latency
    to the real-time pipeline.

    Results are emitted as a ``schema:progress`` Socket.IO event after each
    column is classified so the frontend can render a live schema table
    that fills in row by row as inference completes.

Coverage:
    13 semantic types covering all common business data shapes.
    Ambiguous columns (e.g. "code" with mixed content) return UNKNOWN and
    are forwarded to SemanticClassifier for LLM-based disambiguation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame


@dataclass
class TypeInference:
    """Result of a single column type inference."""

    column_name: str
    data_type: str
    semantic_type: str
    confidence: float  # 0.0 = guessed, 1.0 = deterministic
    needs_llm: bool  # True → forward to SemanticClassifier
    sample_values: list[str]
    null_rate: float
    unique_count: int


# ── Keyword sets ───────────────────────────────────────────────────────────

_ID_KEYWORDS = frozenset({"_id", "id", "_key", "uuid", "guid", "pk", "fk", "code", "ref"})
_CURRENCY_KEYWORDS = frozenset(
    {
        "price",
        "revenue",
        "cost",
        "amount",
        "salary",
        "fee",
        "total",
        "subtotal",
        "tax",
        "income",
        "spend",
        "budget",
        "payment",
        "charge",
        "earnings",
        "profit",
        "margin",
        "sales",
        "usd",
        "eur",
        "gbp",
        "jpy",
        "$",
        "£",
        "€",
    }
)
_PCT_KEYWORDS = frozenset(
    {
        "%",
        "pct",
        "percent",
        "rate",
        "ratio",
        "share",
        "fraction",
        "completion",
        "discount",
        "margin",
    }
)
_DATE_KEYWORDS = frozenset(
    {
        "date",
        "day",
        "month",
        "year",
        "dt",
        "timestamp",
        "time",
        "created_at",
        "updated_at",
        "deleted_at",
        "start",
        "end",
        "opened",
        "closed",
        "published",
        "birth",
        "hired",
    }
)
_EMAIL_KEYWORDS = frozenset({"email", "e_mail", "mail", "contact"})
_PHONE_KEYWORDS = frozenset({"phone", "tel", "mobile", "cell", "fax", "contact_no"})
_COUNT_KEYWORDS = frozenset(
    {
        "count",
        "qty",
        "quantity",
        "num_",
        "n_",
        "items",
        "units",
        "orders",
        "transactions",
        "visits",
        "clicks",
        "views",
        "sessions",
        "users",
        "customers",
    }
)

# Maximum cardinality ratio for a text column to be considered categorical
_CATEGORICAL_CARDINALITY_RATIO = 0.05  # < 5% unique → categorical


def infer_all_columns(
    df: DataFrameT, emit_progress: Callable[[str, TypeInference], None] | None = None
) -> list[TypeInference]:
    """Infer semantic types for every column in a DataFrame.

    Args:
        df:             Polars or pandas DataFrame.
        emit_progress:  Optional sync callback ``fn(column_name, inference)``
                        called after each column for real-time UI updates.

    Returns:
        List of TypeInference objects, one per column, in column order.
    """
    results = []
    try:
        import polars as pl

        is_polars = isinstance(df, pl.DataFrame)
    except ImportError:
        is_polars = False

    for col in df.columns:
        inference = infer_column(df, col, is_polars)
        results.append(inference)
        if emit_progress:
            emit_progress(col, inference)

    return results


def infer_column(df: DataFrameT, col: str, is_polars: bool | None = None) -> TypeInference:
    """Infer the semantic type for a single column.

    Args:
        df:        Polars or pandas DataFrame.
        col:       Column name to analyse.
        is_polars: When None, auto-detected.

    Returns:
        TypeInference with semantic_type, confidence, and needs_llm flag.
    """
    if is_polars is None:
        try:
            import polars as pl

            is_polars = isinstance(df, pl.DataFrame)
        except ImportError:
            is_polars = False

    if is_polars:
        return _infer_polars(df, col)
    return _infer_pandas(df, col)


def _infer_polars(df: DataFrameT, col: str) -> TypeInference:
    import polars as pl

    series = df[col]
    dtype = series.dtype
    dtype_str = str(dtype)
    total_rows = df.height
    null_count = series.null_count()
    null_rate = round(null_count / max(total_rows, 1), 4)
    unique_count = series.drop_nulls().n_unique()
    sample_vals = [str(v) for v in series.drop_nulls().head(5).to_list()]

    name = col.lower()

    # ── Deterministic type-based rules ────────────────────────────────────

    if dtype in (pl.Date,):
        return TypeInference(
            col, dtype_str, "date", 1.0, False, sample_vals, null_rate, unique_count
        )

    if dtype in (pl.Datetime, pl.Time, pl.Duration):
        return TypeInference(
            col, dtype_str, "datetime", 1.0, False, sample_vals, null_rate, unique_count
        )

    if dtype == pl.Boolean:
        return TypeInference(
            col, dtype_str, "boolean", 1.0, False, sample_vals, null_rate, unique_count
        )

    # ── Keyword-driven name matching (high confidence) ────────────────────

    if any(kw in name for kw in _EMAIL_KEYWORDS) and "@" in " ".join(sample_vals):
        return TypeInference(
            col, dtype_str, "email", 0.95, False, sample_vals, null_rate, unique_count
        )

    if any(kw in name for kw in _PHONE_KEYWORDS):
        return TypeInference(
            col, dtype_str, "phone", 0.85, False, sample_vals, null_rate, unique_count
        )

    if any(kw in name for kw in _PCT_KEYWORDS):
        return TypeInference(
            col, dtype_str, "percentage", 0.85, False, sample_vals, null_rate, unique_count
        )

    if any(kw in name for kw in _CURRENCY_KEYWORDS):
        return TypeInference(
            col, dtype_str, "currency", 0.90, False, sample_vals, null_rate, unique_count
        )

    # ── Numeric dispatch ──────────────────────────────────────────────────

    int_types = (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64)
    float_types = (pl.Float32, pl.Float64)

    if dtype in int_types:
        if any(kw in name for kw in _COUNT_KEYWORDS):
            return TypeInference(
                col, dtype_str, "numeric_count", 0.85, False, sample_vals, null_rate, unique_count
            )
        if any(kw in name for kw in _ID_KEYWORDS):
            return TypeInference(
                col, dtype_str, "identifier", 0.80, False, sample_vals, null_rate, unique_count
            )
        return TypeInference(
            col, dtype_str, "numeric_count", 0.70, False, sample_vals, null_rate, unique_count
        )

    if dtype in float_types:
        if any(kw in name for kw in _COUNT_KEYWORDS):
            return TypeInference(
                col, dtype_str, "numeric_count", 0.80, False, sample_vals, null_rate, unique_count
            )
        return TypeInference(
            col, dtype_str, "numeric_measure", 0.75, False, sample_vals, null_rate, unique_count
        )

    # ── String dispatch ───────────────────────────────────────────────────

    if dtype == pl.Utf8:
        # Check date-like column names
        if any(kw in name for kw in _DATE_KEYWORDS):
            return TypeInference(
                col, dtype_str, "datetime", 0.70, False, sample_vals, null_rate, unique_count
            )

        # Check identifier patterns
        if any(kw in name for kw in _ID_KEYWORDS):
            return TypeInference(
                col, dtype_str, "identifier", 0.75, False, sample_vals, null_rate, unique_count
            )

        # Cardinality-based categorical detection
        cardinality_ratio = unique_count / max(total_rows - null_count, 1)
        if cardinality_ratio <= _CATEGORICAL_CARDINALITY_RATIO:
            return TypeInference(
                col, dtype_str, "categorical", 0.80, False, sample_vals, null_rate, unique_count
            )

        # Ambiguous — forward to LLM classifier
        return TypeInference(
            col, dtype_str, "free_text", 0.50, True, sample_vals, null_rate, unique_count
        )

    # ── Unknown / struct / list types ─────────────────────────────────────
    return TypeInference(col, dtype_str, "unknown", 0.0, True, sample_vals, null_rate, unique_count)


def _infer_pandas(df: DataFrameT, col: str) -> TypeInference:
    import numpy as np

    series = df[col]
    dtype = series.dtype
    dtype_str = str(dtype)
    total_rows = len(series)
    null_count = int(series.isna().sum())
    null_rate = round(null_count / max(total_rows, 1), 4)
    unique_count = int(series.nunique())
    sample_vals = [str(v) for v in series.dropna().head(5).tolist()]
    name = col.lower()

    if np.issubdtype(dtype, np.datetime64) or "datetime" in str(dtype):
        return TypeInference(
            col, dtype_str, "datetime", 1.0, False, sample_vals, null_rate, unique_count
        )
    if str(dtype) == "bool":
        return TypeInference(
            col, dtype_str, "boolean", 1.0, False, sample_vals, null_rate, unique_count
        )

    if any(kw in name for kw in _CURRENCY_KEYWORDS):
        return TypeInference(
            col, dtype_str, "currency", 0.90, False, sample_vals, null_rate, unique_count
        )
    if any(kw in name for kw in _PCT_KEYWORDS):
        return TypeInference(
            col, dtype_str, "percentage", 0.85, False, sample_vals, null_rate, unique_count
        )

    if np.issubdtype(dtype, np.integer):
        if any(kw in name for kw in _COUNT_KEYWORDS):
            return TypeInference(
                col, dtype_str, "numeric_count", 0.80, False, sample_vals, null_rate, unique_count
            )
        return TypeInference(
            col, dtype_str, "numeric_count", 0.70, False, sample_vals, null_rate, unique_count
        )

    if np.issubdtype(dtype, np.floating):
        return TypeInference(
            col, dtype_str, "numeric_measure", 0.75, False, sample_vals, null_rate, unique_count
        )

    if dtype is object or "str" in str(dtype):
        cardinality_ratio = unique_count / max(total_rows - null_count, 1)
        if any(kw in name for kw in _DATE_KEYWORDS):
            return TypeInference(
                col, dtype_str, "datetime", 0.65, False, sample_vals, null_rate, unique_count
            )
        if cardinality_ratio <= _CATEGORICAL_CARDINALITY_RATIO:
            return TypeInference(
                col, dtype_str, "categorical", 0.80, False, sample_vals, null_rate, unique_count
            )
        return TypeInference(
            col, dtype_str, "free_text", 0.50, True, sample_vals, null_rate, unique_count
        )

    return TypeInference(col, dtype_str, "unknown", 0.0, True, sample_vals, null_rate, unique_count)
