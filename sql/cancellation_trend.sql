-- =============================================================================
-- Cancellation trend — POLICY grain (enrollment_id)
-- Source : dbo.Enrollments_PY2526_DEC31 (historical as-of snapshot)
-- Date   : MAX(enrollment_last_update_date) per policy
--          PROXY activity date — not a confirmed cancellation event timestamp.
-- Output : aggregated daily counts only (no identifiers returned)
--
-- COUNT(*) in Daily counts rows of Policy_Event, which is already one row per
-- (Plan_Year, enrollment_id, status) — i.e. distinct policies, not raw rows.
-- =============================================================================
WITH Policy_Event AS
(
    SELECT
        coverage_year AS Plan_Year,
        enrollment_id,
        enrollment_status_description AS Metric_Status,
        MAX(enrollment_last_update_date) AS Metric_Date
    FROM dbo.Enrollments_PY2526_DEC31
    WHERE coverage_year IN (2025, 2026)
      AND enrollment_status_description = 'Cancelled'
      AND enrollment_id IS NOT NULL
      AND enrollment_last_update_date IS NOT NULL
    GROUP BY
        coverage_year,
        enrollment_id,
        enrollment_status_description
),
Daily AS
(
    SELECT
        Plan_Year,
        Metric_Date,
        COUNT(*) AS Daily_Count
    FROM Policy_Event
    GROUP BY
        Plan_Year,
        Metric_Date
)
SELECT
    Plan_Year,
    Metric_Date,
    'Cancellation' AS Metric,
    Daily_Count,
    SUM(Daily_Count) OVER
    (
        PARTITION BY Plan_Year
        ORDER BY Metric_Date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS Cumulative_Count
FROM Daily
ORDER BY Plan_Year, Metric_Date;
