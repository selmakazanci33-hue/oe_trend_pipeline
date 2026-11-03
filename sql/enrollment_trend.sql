-- =============================================================================
-- Enrollment trend — PERSON grain (enrollee_id)
-- Source : dbo.Enrollments_PY2526_NOV30 (historical as-of snapshot)
-- Date   : enrollment_confirmation_date, first confirmation per person
-- Output : aggregated daily counts only (no identifiers returned)
--
-- The date windows below are POC / discovery windows, NOT official OE start dates.
-- benefit_effective_date is intentionally NOT used: Enrolled during OE does not
-- mean coverage is currently effective.
-- =============================================================================
WITH Base AS
(
    SELECT
        coverage_year AS Plan_Year,
        enrollee_id,
        enrollment_confirmation_date
    FROM dbo.Enrollments_PY2526_NOV30
    WHERE coverage_year IN (2025, 2026)
      AND application_type = 'OE'
      AND enrollment_status_description = 'Enrolled'
      AND enrollee_status_description = 'Enrolled'
      AND enrollment_confirmation_date IS NOT NULL
),
Person_First_Confirmation AS
(
    SELECT
        Plan_Year,
        enrollee_id,
        MIN(enrollment_confirmation_date) AS Metric_Date
    FROM Base
    WHERE
        (Plan_Year = 2025 AND enrollment_confirmation_date >= '2024-10-01')
        OR
        (Plan_Year = 2026 AND enrollment_confirmation_date >= '2025-10-01')
    GROUP BY
        Plan_Year,
        enrollee_id
),
Daily AS
(
    SELECT
        Plan_Year,
        Metric_Date,
        COUNT(*) AS Daily_Count
    FROM Person_First_Confirmation
    GROUP BY
        Plan_Year,
        Metric_Date
)
SELECT
    Plan_Year,
    Metric_Date,
    'Enrollment' AS Metric,
    Daily_Count,
    SUM(Daily_Count) OVER
    (
        PARTITION BY Plan_Year
        ORDER BY Metric_Date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS Cumulative_Count
FROM Daily
ORDER BY Plan_Year, Metric_Date;
