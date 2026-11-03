-- =============================================================================
-- EDE DISCOVERY — diagnostic only. NOT a metric definition.
--
-- source = 'EDE' is a discovery filter. It is NOT the Executive Dashboard EDE
-- definition. The Executive Dashboard documentation indicates EDE enrollments are
-- identified through relationships to partner_permissions, counted without
-- filtering by status or insurance type. That join has not been identified, so
-- this file only locates candidate objects/columns and profiles source = 'EDE'.
--
-- Raw row counts below are diagnostic and must never be used as a business KPI.
-- Run manually or with: python run_pipeline.py --ede-discovery
-- =============================================================================

-- name: partner_permissions_objects
SELECT
    s.name AS Schema_Name,
    o.name AS Object_Name,
    o.type_desc AS Object_Type
FROM sys.objects AS o
INNER JOIN sys.schemas AS s
    ON s.schema_id = o.schema_id
WHERE o.type IN ('U', 'V')
  AND o.name LIKE '%partner%permission%'
ORDER BY s.name, o.name;

-- name: partner_permissions_columns
SELECT
    TABLE_SCHEMA AS Schema_Name,
    TABLE_NAME AS Object_Name,
    COLUMN_NAME AS Column_Name,
    DATA_TYPE AS Data_Type,
    ORDINAL_POSITION AS Ordinal_Position
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME LIKE '%partner%permission%'
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;

-- name: snapshot_candidate_join_columns
SELECT
    TABLE_NAME AS Object_Name,
    COLUMN_NAME AS Column_Name,
    DATA_TYPE AS Data_Type
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME IN ('Enrollments_PY2526_NOV30', 'Enrollments_PY2526_DEC31')
  AND (
        COLUMN_NAME LIKE '%partner%'
     OR COLUMN_NAME LIKE '%source%'
     OR COLUMN_NAME LIKE '%broker%'
     OR COLUMN_NAME LIKE '%agent%'
     OR COLUMN_NAME LIKE '%permission%'
     OR COLUMN_NAME LIKE '%insurance%'
  )
ORDER BY TABLE_NAME, COLUMN_NAME;

-- name: source_ede_profile
SELECT
    coverage_year AS Plan_Year,
    application_type AS Application_Type,
    COUNT(*) AS Raw_Rows_Diagnostic_Only,
    COUNT(DISTINCT enrollment_id) AS Distinct_Enrollments,
    COUNT(DISTINCT enrollee_id) AS Distinct_People
FROM dbo.Enrollments_PY2526_NOV30
WHERE source = 'EDE'
  AND coverage_year IN (2025, 2026)
GROUP BY coverage_year, application_type
ORDER BY coverage_year, application_type;
