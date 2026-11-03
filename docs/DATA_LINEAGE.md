# Data Lineage

```text
Azure SQL (Georgia Access)
  │  src/azure_connection.py — ActiveDirectoryInteractive, SQLAlchemy + pyodbc, SELECT only
  ▼
Source snapshot
  │  Enrollment                → dbo.Enrollments_PY2526_NOV30
  │  Cancellation, Termination → dbo.Enrollments_PY2526_DEC31
  ▼
SQL metric logic  (sql/*.sql, run by src/query_executor.py)
  │  de-duplicate to grain (person / policy) → assign one activity date → daily counts → running total
  │  output: aggregated rows only (Plan_Year, Metric_Date, Metric, Daily_Count, Cumulative_Count)
  │  saved: data/raw/<metric>_trend_<run_id>.csv
  ▼
Pandas  (src/data_processor.py)
  │  required-column / empty / year checks; Metric_Date → calendar date;
  │  same-day timestamp rows summed, cumulative recomputed, total must equal SQL total;
  │  Grain, Source_Table, Date_Field, OE_Day attached
  ▼
Validation  (src/validator.py + sql/validation.sql)
  │  L1 control totals, L1 independent COUNT(DISTINCT) recount, L1 internal consistency,
  │  L2 issuer distribution, L3 status category
  │  saved: data/validation/validation_results_<run_id>.csv, level*_<run_id>.csv, run_manifest_<run_id>.json
  ▼
Normalized dataset
  │  Plan_Year | Metric_Date | Metric | Daily_Count | Cumulative_Count | Grain | Source_Table | Date_Field | Validation_Status | OE_Day
  │  saved: data/processed/oe_trend_normalized_<run_id>.csv
  ▼
Plotly  (src/trend_builder.py)
  │  one trace per (Metric, Plan Year, Daily|Cumulative); metrics never mixed on one chart
  ▼
HTML  (src/dashboard_generator.py)
     output/oe_trend_dashboard.html — self-contained, plotly.js inline, opens offline
```

## PII

No query returns `enrollee_id`, `enrollment_id`, names, or any person-level field — identifiers are only used inside SQL for `GROUP BY` / `COUNT(DISTINCT)`. Raw, processed, validation, log, and HTML outputs contain aggregated counts only. Logs record presence flags for connection settings, never the username value.

## Failure behavior

Any failure in connection, SQL loading, query execution, or processing stops the run with exit code 1 and writes no dashboard. No cached, fabricated, or control values are substituted. A validation mismatch still writes the dashboard (showing the failure) and exits with code 3.

`--from-run <RUN_ID>` rebuilds the HTML from a previous **live** run's processed files. This is explicit, and the dashboard header and banner state the data mode and the original extraction time.
