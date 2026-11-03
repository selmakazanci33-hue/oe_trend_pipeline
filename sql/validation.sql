-- =============================================================================
-- Validation queries — aggregated counts only. Each section is run separately.
-- Sections are split on "-- name: <section>" markers by query_executor.
--
-- Level 1  : independent COUNT(DISTINCT <identifier>) recount per Plan Year,
--            compared to the trend's final Cumulative_Count and to the control.
-- Level 2  : distinct counts by issuer (hios_issuer_id). No issuer controls exist
--            yet, so Level 2 is reported as VALIDATION PENDING.
-- Level 3  : distinct policies by status category in the DEC31 snapshot.
--            No category controls exist yet, so Level 3 is VALIDATION PENDING.
-- =============================================================================

-- name: enrollment_level1_total
SELECT
    coverage_year AS Plan_Year,
    'Enrollment' AS Metric,
    COUNT(DISTINCT enrollee_id) AS Distinct_Count
FROM dbo.Enrollments_PY2526_NOV30
WHERE coverage_year IN (2025, 2026)
  AND application_type = 'OE'
  AND enrollment_status_description = 'Enrolled'
  AND enrollee_status_description = 'Enrolled'
  AND enrollment_confirmation_date IS NOT NULL
  AND (
        (coverage_year = 2025 AND enrollment_confirmation_date >= '2024-10-01')
     OR (coverage_year = 2026 AND enrollment_confirmation_date >= '2025-10-01')
  )
GROUP BY coverage_year;

-- name: policy_event_level1_total
SELECT
    coverage_year AS Plan_Year,
    CASE enrollment_status_description
        WHEN 'Cancelled' THEN 'Cancellation'
        WHEN 'Terminated' THEN 'Termination'
    END AS Metric,
    COUNT(DISTINCT enrollment_id) AS Distinct_Count
FROM dbo.Enrollments_PY2526_DEC31
WHERE coverage_year IN (2025, 2026)
  AND enrollment_status_description IN ('Cancelled', 'Terminated')
  AND enrollment_id IS NOT NULL
  AND enrollment_last_update_date IS NOT NULL
GROUP BY coverage_year, enrollment_status_description;

-- name: enrollment_level2_issuer
SELECT
    coverage_year AS Plan_Year,
    'Enrollment' AS Metric,
    hios_issuer_id AS Issuer,
    COUNT(DISTINCT enrollee_id) AS Distinct_Count
FROM dbo.Enrollments_PY2526_NOV30
WHERE coverage_year IN (2025, 2026)
  AND application_type = 'OE'
  AND enrollment_status_description = 'Enrolled'
  AND enrollee_status_description = 'Enrolled'
  AND enrollment_confirmation_date IS NOT NULL
  AND (
        (coverage_year = 2025 AND enrollment_confirmation_date >= '2024-10-01')
     OR (coverage_year = 2026 AND enrollment_confirmation_date >= '2025-10-01')
  )
GROUP BY coverage_year, hios_issuer_id;

-- name: policy_event_level2_issuer
SELECT
    coverage_year AS Plan_Year,
    CASE enrollment_status_description
        WHEN 'Cancelled' THEN 'Cancellation'
        WHEN 'Terminated' THEN 'Termination'
    END AS Metric,
    hios_issuer_id AS Issuer,
    COUNT(DISTINCT enrollment_id) AS Distinct_Count
FROM dbo.Enrollments_PY2526_DEC31
WHERE coverage_year IN (2025, 2026)
  AND enrollment_status_description IN ('Cancelled', 'Terminated')
  AND enrollment_id IS NOT NULL
  AND enrollment_last_update_date IS NOT NULL
GROUP BY coverage_year, enrollment_status_description, hios_issuer_id;

-- name: level3_status_category
SELECT
    coverage_year AS Plan_Year,
    enrollment_status_description AS Status_Category,
    COUNT(DISTINCT enrollment_id) AS Distinct_Policies
FROM dbo.Enrollments_PY2526_DEC31
WHERE coverage_year IN (2025, 2026)
  AND enrollment_id IS NOT NULL
GROUP BY coverage_year, enrollment_status_description;
