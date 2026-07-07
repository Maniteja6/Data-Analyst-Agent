-- ─────────────────────────────────────────────────────────────────────────────
-- column_statistics.sql
-- DataPilot — per-column descriptive statistics
--
-- Real-time usage:
--   Called by ProfilingAgent for each numeric column in the dataset.
--   Results are emitted as profiling:column_complete Socket.IO events
--   so the browser renders column stat cards one-by-one as they arrive.
--
-- Template variables (replaced by QueryBuilder before execution):
--   {column}     — double-quoted column name:  "revenue"
--   {table}      — always: dataset
--   {percentiles} — DuckDB PERCENTILE_CONT list (auto-generated)
--
-- Performance notes:
--   • Single-pass aggregation — DuckDB computes all stats in one scan.
--   • On a 1M-row Parquet file this runs in < 200ms via DuckDB's vectorised engine.
--   • Cast to DOUBLE before aggregation avoids integer overflow on SUM.
--   • FILTER (WHERE ... IS NOT NULL) skips nulls without a separate subquery.
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    -- ── Identity ───────────────────────────────────────────────────────────
    '{column_raw}'                                          AS column_name,

    -- ── Row counts ─────────────────────────────────────────────────────────
    COUNT(*)                                                AS total_rows,
    COUNT({column})                                         AS non_null_count,
    COUNT(*) - COUNT({column})                              AS null_count,
    ROUND(
        (COUNT(*) - COUNT({column}))::DOUBLE / COUNT(*),
        6
    )                                                       AS null_rate,
    COUNT(DISTINCT {column})                                AS unique_count,
    ROUND(
        COUNT(DISTINCT {column})::DOUBLE / NULLIF(COUNT({column}), 0),
        6
    )                                                       AS cardinality_ratio,

    -- ── Central tendency ───────────────────────────────────────────────────
    AVG({column}::DOUBLE)                                   AS mean,
    MEDIAN({column}::DOUBLE)                                AS median,

    -- ── Spread ─────────────────────────────────────────────────────────────
    STDDEV_POP({column}::DOUBLE)                            AS stddev,
    VAR_POP({column}::DOUBLE)                               AS variance,

    -- ── Range ──────────────────────────────────────────────────────────────
    MIN({column}::DOUBLE)                                   AS min_val,
    MAX({column}::DOUBLE)                                   AS max_val,
    MAX({column}::DOUBLE) - MIN({column}::DOUBLE)           AS range_val,
    SUM({column}::DOUBLE)                                   AS total_sum,

    -- ── Percentiles (single PERCENTILE_CONT call per value for efficiency) ─
    PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY {column}::DOUBLE) AS p5,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {column}::DOUBLE) AS p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {column}::DOUBLE) AS p50,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {column}::DOUBLE) AS p75,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {column}::DOUBLE) AS p95,

    -- ── IQR and Tukey fences (used by AnomalyDetector for outlier bounds) ──
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {column}::DOUBLE)
      - PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {column}::DOUBLE)
                                                            AS iqr,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {column}::DOUBLE)
      - 1.5 * (
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {column}::DOUBLE)
          - PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {column}::DOUBLE)
      )                                                     AS tukey_lower_fence,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {column}::DOUBLE)
      + 1.5 * (
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {column}::DOUBLE)
          - PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {column}::DOUBLE)
      )                                                     AS tukey_upper_fence,

    -- ── Shape ──────────────────────────────────────────────────────────────
    -- Skewness: 0 = symmetric, > 0 = right-skewed, < 0 = left-skewed
    -- Kurtosis: > 3 = heavy tails (leptokurtic), < 3 = light tails (platykurtic)
    SKEWNESS({column}::DOUBLE)                              AS skewness,
    KURTOSIS({column}::DOUBLE)                              AS kurtosis,

    -- ── Coefficient of Variation (relative variability) ────────────────────
    -- CV = stddev / |mean|. High CV (> 1) means data is highly spread.
    -- NULL when mean is zero (undefined).
    ROUND(
        STDDEV_POP({column}::DOUBLE)
        / NULLIF(ABS(AVG({column}::DOUBLE)), 0),
        6
    )                                                       AS coefficient_of_variation,

    -- ── Zero analysis (useful for revenue/count columns) ───────────────────
    COUNT(*) FILTER (WHERE {column}::DOUBLE = 0)            AS zero_count,
    COUNT(*) FILTER (WHERE {column}::DOUBLE < 0)            AS negative_count,

    -- ── Metadata ───────────────────────────────────────────────────────────
    NOW()                                                   AS computed_at

FROM {table}

-- Filter to rows where the column is not null for shape statistics.
-- The counts above already handle nulls correctly via COUNT({column}).
