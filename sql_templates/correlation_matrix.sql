-- ─────────────────────────────────────────────────────────────────────────────
-- correlation_matrix.sql
-- DataPilot — pairwise Pearson correlation matrix for numeric columns
--
-- Real-time usage:
--   Results are streamed as correlation:pair_complete Socket.IO events —
--   one event per row — so the frontend correlation heatmap fills in
--   cell-by-cell as each pair completes rather than waiting for all pairs.
--
-- Performance notes:
--   • DuckDB's CORR() is a single-pass window aggregate — efficient on wide tables.
--   • For N numeric columns, this query produces N² rows (full matrix including
--     self-correlations and mirror pairs).
--   • Filter |r| >= {min_abs_r} to emit only significant correlations.
--   • On a 500K-row, 20-column dataset: typically < 500ms.
--
-- Template variables:
--   {table}       — always: dataset
--   {col_pairs}   — generated UNION of CORR() pairs by QueryBuilder
--   {min_abs_r}   — float, default 0.3 (filters weak correlations)
--
-- Usage pattern (QueryBuilder generates the UNION for all column pairs):
--   SELECT 'revenue' AS col_a, 'quantity' AS col_b,
--          CORR("revenue"::DOUBLE, "quantity"::DOUBLE) AS r
--   FROM dataset
--   UNION ALL
--   SELECT 'revenue' AS col_a, 'discount' AS col_b,
--          CORR("revenue"::DOUBLE, "discount"::DOUBLE) AS r
--   FROM dataset
--   ...
-- ─────────────────────────────────────────────────────────────────────────────

WITH raw_correlations AS (
    -- QueryBuilder replaces {col_pairs} with the generated UNION ALL block.
    -- Each row: col_a, col_b, r (Pearson correlation coefficient).
    {col_pairs}
),

enriched AS (
    SELECT
        col_a,
        col_b,

        -- ── Correlation value ────────────────────────────────────────────
        ROUND(r, 6)                                         AS r,
        ROUND(POWER(r, 2), 6)                               AS r_squared,

        -- ── Strength classification ──────────────────────────────────────
        -- Used by the frontend to colour heatmap cells.
        CASE
            WHEN ABS(r) >= 0.90 THEN 'very_strong'
            WHEN ABS(r) >= 0.70 THEN 'strong'
            WHEN ABS(r) >= 0.50 THEN 'moderate'
            WHEN ABS(r) >= 0.30 THEN 'weak'
            ELSE 'negligible'
        END                                                 AS strength,

        -- ── Direction ────────────────────────────────────────────────────
        CASE WHEN r > 0 THEN 'positive' ELSE 'negative' END AS direction,

        -- ── Absolute value for filtering / sorting ───────────────────────
        ABS(r)                                              AS abs_r,

        -- ── Self-correlation flag (r = 1.0 always) ───────────────────────
        CASE WHEN col_a = col_b THEN TRUE ELSE FALSE END    AS is_self,

        -- ── Mirror pair flag (col_a > col_b alphabetically) ─────────────
        -- Allows the frontend to show a half-matrix without duplicates.
        CASE WHEN col_a > col_b THEN TRUE ELSE FALSE END    AS is_mirror

    FROM raw_correlations
    WHERE r IS NOT NULL
      AND col_a <> col_b              -- exclude self-correlations
      AND ABS(r) >= {min_abs_r}       -- exclude weak / negligible correlations
)

SELECT
    col_a,
    col_b,
    r,
    r_squared,
    strength,
    direction,
    abs_r,
    is_mirror,

    -- ── Ranking for frontend card ordering ───────────────────────────────
    -- Rank 1 = strongest absolute correlation across the whole dataset.
    RANK() OVER (ORDER BY abs_r DESC)                       AS strength_rank

FROM enriched
WHERE NOT is_mirror         -- return lower triangle only (col_a < col_b alphabetically)

ORDER BY abs_r DESC, col_a, col_b;
