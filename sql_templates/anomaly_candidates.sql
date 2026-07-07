-- ─────────────────────────────────────────────────────────────────────────────
-- anomaly_candidates.sql
-- DataPilot — multi-method anomaly candidate identification
--
-- Real-time usage:
--   Each qualifying row is emitted as an anomaly:detected Socket.IO event
--   immediately so the frontend renders an anomaly ticker in real-time
--   rather than waiting for the full scan to complete.
--
--   The AnomalyDetector Python class runs this template per numeric column,
--   collects results, deduplicates (same row across multiple columns = one alert),
--   and streams the deduplicated, ranked results.
--
-- Methods implemented (all in a single DuckDB scan for performance):
--   Z-Score:     |z| >= {z_threshold}   (default: 3.0)
--   IQR/Tukey:   value < Q1 - {iqr_multiplier}*IQR  OR
--                value > Q3 + {iqr_multiplier}*IQR  (default multiplier: 1.5)
--
-- Template variables:
--   {column}          — double-quoted numeric column: "revenue"
--   {table}           — always: dataset
--   {z_threshold}     — float, default 3.0
--   {iqr_multiplier}  — float, default 1.5 (use 3.0 for extreme outliers only)
--   {row_id_column}   — column to use as row identifier (rowid or a primary key)
--   {limit}           — maximum anomalies to return (default: 500)
-- ─────────────────────────────────────────────────────────────────────────────

WITH

-- ── Step 1: Compute column-level statistics in one pass ────────────────────
column_stats AS (
    SELECT
        AVG({column}::DOUBLE)                               AS col_mean,
        STDDEV_POP({column}::DOUBLE)                        AS col_stddev,
        PERCENTILE_CONT(0.25) WITHIN GROUP (
            ORDER BY {column}::DOUBLE
        )                                                   AS q1,
        PERCENTILE_CONT(0.75) WITHIN GROUP (
            ORDER BY {column}::DOUBLE
        )                                                   AS q3,
        COUNT({column})                                     AS non_null_count
    FROM {table}
    WHERE {column} IS NOT NULL
),

-- ── Step 2: Derive fences ─────────────────────────────────────────────────
fences AS (
    SELECT
        col_mean,
        col_stddev,
        q1,
        q3,
        q3 - q1                                             AS iqr,
        q1 - {iqr_multiplier} * (q3 - q1)                  AS lower_fence,
        q3 + {iqr_multiplier} * (q3 - q1)                  AS upper_fence,
        non_null_count
    FROM column_stats
),

-- ── Step 3: Score every non-null row ──────────────────────────────────────
scored AS (
    SELECT
        -- Row identity
        {row_id_column}                                     AS row_id,
        {column}::DOUBLE                                    AS value,

        -- Z-Score: signed distance from mean in standard deviations
        ROUND(
            ({column}::DOUBLE - f.col_mean)
            / NULLIF(f.col_stddev, 0),
            4
        )                                                   AS z_score,

        -- Absolute Z-Score for thresholding
        ABS(
            ({column}::DOUBLE - f.col_mean)
            / NULLIF(f.col_stddev, 0)
        )                                                   AS abs_z_score,

        -- IQR method flags
        CASE WHEN {column}::DOUBLE < f.lower_fence THEN TRUE
             WHEN {column}::DOUBLE > f.upper_fence THEN TRUE
             ELSE FALSE
        END                                                 AS is_iqr_outlier,

        CASE WHEN {column}::DOUBLE < f.lower_fence THEN 'low'
             WHEN {column}::DOUBLE > f.upper_fence THEN 'high'
             ELSE 'normal'
        END                                                 AS iqr_direction,

        -- Distance outside the fence (0 when inside)
        GREATEST(
            f.lower_fence - {column}::DOUBLE,
            {column}::DOUBLE - f.upper_fence,
            0
        )                                                   AS fence_distance,

        -- Context values for description generation
        f.col_mean,
        f.col_stddev,
        f.q1,
        f.q3,
        f.iqr,
        f.lower_fence,
        f.upper_fence,
        f.non_null_count

    FROM {table}
    CROSS JOIN fences f
    WHERE {column} IS NOT NULL
),

-- ── Step 4: Filter to anomaly candidates ──────────────────────────────────
candidates AS (
    SELECT
        row_id,
        value,
        z_score,
        abs_z_score,
        is_iqr_outlier,
        iqr_direction,
        fence_distance,
        col_mean,
        col_stddev,
        q1,
        q3,
        iqr,
        lower_fence,
        upper_fence,
        non_null_count,

        -- Detection method flags
        abs_z_score >= {z_threshold}                        AS is_zscore_outlier,

        -- Consensus: detected by BOTH methods = higher severity
        (abs_z_score >= {z_threshold} AND is_iqr_outlier)  AS is_consensus_outlier

    FROM scored
    WHERE abs_z_score >= {z_threshold}
       OR is_iqr_outlier
)

-- ── Final SELECT: annotate with severity and human-readable description ────
SELECT
    row_id,
    '{column_raw}'                                          AS column_name,
    value,

    -- ── Detection metadata ─────────────────────────────────────────────
    is_zscore_outlier,
    is_iqr_outlier,
    is_consensus_outlier,
    ROUND(z_score,       4)                                 AS z_score,
    ROUND(abs_z_score,   4)                                 AS abs_z_score,
    iqr_direction,
    ROUND(fence_distance, 4)                                AS fence_distance,

    -- ── Severity classification ────────────────────────────────────────
    -- critical: consensus outlier (both methods agree) with |z| >= 5
    -- high:     consensus outlier OR |z| >= 4
    -- medium:   single-method outlier with |z| >= 3
    -- low:      IQR outlier just outside the fence
    CASE
        WHEN is_consensus_outlier AND abs_z_score >= 5.0 THEN 'critical'
        WHEN is_consensus_outlier                        THEN 'high'
        WHEN abs_z_score >= 4.0                         THEN 'high'
        WHEN is_zscore_outlier                          THEN 'medium'
        ELSE                                                 'low'
    END                                                     AS severity,

    -- ── Confidence score (0.0–1.0) ────────────────────────────────────
    -- Higher = more confident this is a real anomaly vs natural variance.
    ROUND(
        LEAST(
            1.0,
            (
                0.5 * LEAST(abs_z_score / 6.0, 1.0)       -- z-score component
                + 0.5 * CASE WHEN is_consensus_outlier THEN 1.0
                             WHEN is_iqr_outlier        THEN 0.6
                             ELSE                            0.3
                        END                                 -- consensus component
            )
        ),
        4
    )                                                       AS confidence,

    -- ── Human-readable description (used in anomaly:detected event) ───
    CASE
        WHEN is_consensus_outlier THEN
            'Value ' || ROUND(value, 2)::VARCHAR
            || ' is ' || ROUND(abs_z_score, 1)::VARCHAR
            || ' standard deviations from the mean ('
            || ROUND(col_mean, 2)::VARCHAR
            || ') and outside the IQR fence ['
            || ROUND(lower_fence, 2)::VARCHAR || ', '
            || ROUND(upper_fence, 2)::VARCHAR || ']'
        WHEN is_zscore_outlier THEN
            'Value ' || ROUND(value, 2)::VARCHAR
            || ' is ' || ROUND(abs_z_score, 1)::VARCHAR
            || ' standard deviations from the column mean ('
            || ROUND(col_mean, 2)::VARCHAR || ')'
        ELSE
            'Value ' || ROUND(value, 2)::VARCHAR
            || ' is outside the IQR fence ['
            || ROUND(lower_fence, 2)::VARCHAR || ', '
            || ROUND(upper_fence, 2)::VARCHAR || ']'
    END                                                     AS description,

    -- ── Statistical context ────────────────────────────────────────────
    ROUND(col_mean,     4)                                  AS col_mean,
    ROUND(col_stddev,   4)                                  AS col_stddev,
    ROUND(q1,           4)                                  AS q1,
    ROUND(q3,           4)                                  AS q3,
    ROUND(iqr,          4)                                  AS iqr,
    ROUND(lower_fence,  4)                                  AS lower_fence,
    ROUND(upper_fence,  4)                                  AS upper_fence,
    non_null_count

FROM candidates
ORDER BY
    -- Sort: critical first, then by absolute z-score descending
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'high'     THEN 2
        WHEN 'medium'   THEN 3
        ELSE                 4
    END,
    abs_z_score DESC
LIMIT {limit};
