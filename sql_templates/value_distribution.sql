-- ─────────────────────────────────────────────────────────────────────────────
-- value_distribution.sql
-- DataPilot — value distribution for categorical and numeric columns
--
-- Real-time usage:
--   Results are emitted as profiling:column_complete Socket.IO events.
--   The frontend passes them directly to VegaEmbed as histogram data —
--   no client-side binning needed.
--
-- Two modes controlled by template variable {mode}:
--
--   MODE: categorical
--     Returns top-N value counts sorted descending.
--     Used when semantic_type IN (categorical, boolean).
--     Frontend renders as horizontal bar chart.
--
--   MODE: numeric
--     Returns pre-computed histogram bins using DuckDB's HISTOGRAM().
--     Used when semantic_type IN (currency, numeric_measure, numeric_count).
--     Frontend renders as bar chart with pre-binned data (no client-side binning).
--
-- Template variables:
--   {column}      — double-quoted column name
--   {table}       — always: dataset
--   {mode}        — categorical | numeric
--   {top_n}       — integer, default 20 (categorical mode)
--   {bin_count}   — integer, default 20 (numeric mode)
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Categorical mode: top-N value counts ─────────────────────────────────────
-- Replace entire block with the numeric mode block below when {mode} = numeric.
SELECT
    {column}::VARCHAR                                       AS value,
    COUNT(*)                                                AS frequency,
    ROUND(COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER (), 6)      AS relative_frequency,
    ROUND(
        100.0 * COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER (),
        2
    )                                                       AS percentage,

    -- Cumulative frequency for Pareto / 80-20 analysis
    SUM(COUNT(*)) OVER (
        ORDER BY COUNT(*) DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                       AS cumulative_count,
    ROUND(
        100.0 * SUM(COUNT(*)) OVER (
            ORDER BY COUNT(*) DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::DOUBLE / SUM(COUNT(*)) OVER (),
        2
    )                                                       AS cumulative_pct,

    -- Rank for ordering on frontend (1 = most frequent)
    RANK() OVER (ORDER BY COUNT(*) DESC)                    AS frequency_rank

FROM {table}
WHERE {column} IS NOT NULL
GROUP BY {column}
ORDER BY frequency DESC
LIMIT {top_n};

-- ─────────────────────────────────────────────────────────────────────────────
-- ── Numeric mode: pre-computed histogram bins ─────────────────────────────────
-- Uncomment and use this block when {mode} = numeric.
-- DuckDB's histogram() function returns a STRUCT with keys[] and values[].
-- The unnesting produces one row per bin — ready for Vega-Lite bar chart.
-- ─────────────────────────────────────────────────────────────────────────────
/*
WITH bounds AS (
    SELECT
        MIN({column}::DOUBLE) AS min_val,
        MAX({column}::DOUBLE) AS max_val,
        (MAX({column}::DOUBLE) - MIN({column}::DOUBLE))
            / {bin_count}     AS bin_width,
        COUNT({column})       AS non_null_count
    FROM {table}
),
binned AS (
    SELECT
        FLOOR(
            ({column}::DOUBLE - b.min_val)
            / NULLIF(b.bin_width, 0)
        )                                                   AS bin_index,
        COUNT(*)                                            AS bin_count,
        b.min_val,
        b.bin_width,
        b.non_null_count
    FROM {table}
    CROSS JOIN bounds b
    WHERE {column} IS NOT NULL
    GROUP BY bin_index, b.min_val, b.bin_width, b.non_null_count
)
SELECT
    LEAST(bin_index, {bin_count} - 1)                      AS bin_index,
    b.min_val + LEAST(bin_index, {bin_count} - 1) * b.bin_width
                                                            AS bin_start,
    b.min_val + (LEAST(bin_index, {bin_count} - 1) + 1) * b.bin_width
                                                            AS bin_end,
    SUM(bin_count)                                          AS frequency,
    ROUND(SUM(bin_count)::DOUBLE / MAX(non_null_count), 6)  AS relative_frequency,
    ROUND(100.0 * SUM(bin_count)::DOUBLE / MAX(non_null_count), 2)
                                                            AS percentage
FROM binned b
GROUP BY LEAST(bin_index, {bin_count} - 1), b.min_val, b.bin_width
ORDER BY bin_index;
*/
