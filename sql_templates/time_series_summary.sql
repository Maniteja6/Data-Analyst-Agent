-- ─────────────────────────────────────────────────────────────────────────────
-- time_series_summary.sql
-- DataPilot — temporal aggregation for time series analysis and forecast charts
--
-- Real-time usage:
--   Called by SQLAgent when intent = trend_analysis or forecasting_request.
--   Results feed directly into:
--     1. Vega-Lite line chart (rendered via VisualizationAgent → VegaEmbed)
--     2. ForecastAgent as the historical training series
--     3. Insight narrative ("revenue grew 23% from Q1 to Q3 2024")
--
-- The query auto-selects the appropriate granularity via the {granularity}
-- parameter so the result always has 20-60 data points — enough for a
-- meaningful trend line without overloading the frontend chart.
--
-- Template variables:
--   {date_column}    — double-quoted datetime column: "order_date"
--   {value_column}   — double-quoted numeric column:  "revenue"
--   {table}          — always: dataset
--   {granularity}    — day | week | month | quarter | year
--                      QueryBuilder selects based on date range span:
--                        < 60 days  → day
--                        < 26 weeks → week
--                        < 36 months→ month
--                        < 20 quarters→ quarter
--                        else       → year
--   {agg_func}       — SUM | AVG | COUNT | MAX | MIN (default: SUM)
-- ─────────────────────────────────────────────────────────────────────────────

WITH
-- ── Step 1: Truncate timestamps to the chosen granularity ─────────────────
bucketed AS (
    SELECT
        date_trunc('{granularity}', {date_column}::TIMESTAMP) AS period,
        {value_column}::DOUBLE                                 AS value
    FROM {table}
    WHERE {date_column} IS NOT NULL
      AND {value_column} IS NOT NULL
),

-- ── Step 2: Aggregate per period ──────────────────────────────────────────
aggregated AS (
    SELECT
        period,
        {agg_func}(value)                                      AS period_value,
        COUNT(*)                                                AS row_count,
        AVG(value)                                             AS period_avg,
        MIN(value)                                             AS period_min,
        MAX(value)                                             AS period_max,
        STDDEV_POP(value)                                      AS period_stddev
    FROM bucketed
    GROUP BY period
),

-- ── Step 3: Compute period-over-period change ─────────────────────────────
with_changes AS (
    SELECT
        period,
        period_value,
        row_count,
        period_avg,
        period_min,
        period_max,
        period_stddev,

        -- Previous period value for change calculation
        LAG(period_value) OVER (ORDER BY period)               AS prev_period_value,

        -- Absolute change vs previous period
        period_value
            - LAG(period_value) OVER (ORDER BY period)         AS abs_change,

        -- Percentage change vs previous period (null for first row)
        ROUND(
            100.0 * (
                period_value
                - LAG(period_value) OVER (ORDER BY period)
            ) / NULLIF(
                LAG(period_value) OVER (ORDER BY period),
                0
            ),
            2
        )                                                      AS pct_change,

        -- Running total (for cumulative trend charts)
        SUM(period_value) OVER (ORDER BY period
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)  AS running_total,

        -- Rolling 3-period average (smoothing for noisy series)
        AVG(period_value) OVER (ORDER BY period
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)          AS rolling_3_avg,

        -- Period rank for ordering
        RANK() OVER (ORDER BY period)                          AS period_rank,

        -- Total periods (used by frontend to size chart width)
        COUNT(*) OVER ()                                       AS total_periods
    FROM aggregated
),

-- ── Step 4: Overall dataset statistics ───────────────────────────────────
overall AS (
    SELECT
        MIN(period)                                            AS series_start,
        MAX(period)                                            AS series_end,
        SUM(period_value)                                      AS grand_total,
        AVG(period_value)                                      AS overall_avg,
        MAX(period_value)                                      AS overall_max,
        MIN(period_value)                                      AS overall_min,

        -- Overall trend direction via linear regression slope
        -- Positive slope = upward trend, negative = downward
        REGR_SLOPE(
            period_value,
            EPOCH(period)
        )                                                      AS trend_slope,
        REGR_R2(
            period_value,
            EPOCH(period)
        )                                                      AS trend_r2

    FROM aggregated
)

-- ── Final SELECT: join per-period stats with overall metadata ─────────────
SELECT
    -- Period (ISO 8601 string for Vega-Lite temporal encoding)
    STRFTIME(period, '%Y-%m-%dT%H:%M:%S')                     AS period_iso,
    period,
    period_rank,
    total_periods,

    -- Aggregated value
    ROUND(period_value, 4)                                     AS value,
    row_count,

    -- Per-period descriptive stats
    ROUND(period_avg,    4)                                    AS avg_value,
    ROUND(period_min,    4)                                    AS min_value,
    ROUND(period_max,    4)                                    AS max_value,
    ROUND(period_stddev, 4)                                    AS stddev_value,

    -- Period-over-period metrics
    ROUND(prev_period_value, 4)                                AS prev_value,
    ROUND(abs_change,        4)                                AS abs_change,
    pct_change,

    -- Smoothed and cumulative series
    ROUND(rolling_3_avg, 4)                                    AS rolling_3_avg,
    ROUND(running_total, 4)                                    AS running_total,

    -- Overall series context (same value on every row — used by frontend for axis scaling)
    o.series_start,
    o.series_end,
    ROUND(o.grand_total,    4)                                 AS series_total,
    ROUND(o.overall_avg,    4)                                 AS series_avg,
    ROUND(o.overall_max,    4)                                 AS series_max,
    ROUND(o.overall_min,    4)                                 AS series_min,

    -- Trend metadata (same on every row)
    ROUND(o.trend_slope, 8)                                    AS trend_slope,
    ROUND(o.trend_r2,    4)                                    AS trend_r2,
    CASE
        WHEN o.trend_slope > 0  THEN 'up'
        WHEN o.trend_slope < 0  THEN 'down'
        ELSE                         'flat'
    END                                                        AS trend_direction

FROM with_changes
CROSS JOIN overall o
ORDER BY period ASC;
