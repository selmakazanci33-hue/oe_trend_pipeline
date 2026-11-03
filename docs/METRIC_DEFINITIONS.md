# Metric Definitions

The single source of truth in code is `config/settings.py → METRICS`. This document mirrors it.

## Enrollment

| Attribute | Value |
|---|---|
| Grain | Person |
| Identifier | `enrollee_id` |
| Source | `dbo.Enrollments_PY2526_NOV30` (NOV30 historical snapshot) |
| Filters | `coverage_year IN (2025, 2026)`, `application_type = 'OE'`, `enrollment_status_description = 'Enrolled'`, `enrollee_status_description = 'Enrolled'`, `enrollment_confirmation_date IS NOT NULL` |
| POC window | PY2025: confirmation ≥ 2024-10-01; PY2026: confirmation ≥ 2025-10-01 (discovery windows, **not** official OE dates) |
| Activity date | `enrollment_confirmation_date` — `MIN` per (Plan Year, person) |
| Daily Count | Distinct people whose first confirmation falls on that calendar date |
| Cumulative Count | Running total of Daily Count within the Plan Year |
| SQL | `sql/enrollment_trend.sql` |
| Known limitations | Not an active-coverage trend. `Enrolled` ≠ effective coverage. Windows are POC. |
| Validation status | Level 1 control: PY2025 633,677 / PY2026 1,061,718. Levels 2–3: VALIDATION PENDING. |

## Cancellation

| Attribute | Value |
|---|---|
| Grain | Policy |
| Identifier | `enrollment_id` |
| Source | `dbo.Enrollments_PY2526_DEC31` (DEC31 historical snapshot) |
| Filters | `coverage_year IN (2025, 2026)`, `enrollment_status_description = 'Cancelled'`, `enrollment_id` and `enrollment_last_update_date` not null |
| Activity date | `MAX(enrollment_last_update_date)` per (Plan Year, policy, status) — **proxy** |
| SQL | `sql/cancellation_trend.sql` |
| Known limitations | Proxy date, not a confirmed cancellation event timestamp. Year-to-year differences are not interpreted. |
| Validation status | Level 1 control: PY2025 536,086 / PY2026 370,412. Proxy date — business validation required. |

## Termination

| Attribute | Value |
|---|---|
| Grain | Policy |
| Identifier | `enrollment_id` |
| Source | `dbo.Enrollments_PY2526_DEC31` |
| Filters | `coverage_year IN (2025, 2026)`, `enrollment_status_description = 'Terminated'`, `enrollment_id` and `enrollment_last_update_date` not null |
| Activity date | `MAX(enrollment_last_update_date)` per (Plan Year, policy, status) — **proxy** |
| SQL | `sql/termination_trend.sql` |
| Known limitations | Proxy date, not a confirmed termination event timestamp. Year-to-year differences are not interpreted. |
| Validation status | Level 1 control: PY2025 548,512 / PY2026 18,444. Proxy date — business validation required. |

Cancellation and Termination split the combined POC query by status. Because the POC query grouped by `(coverage_year, enrollment_id, enrollment_status_description)`, the per-status results are identical to the combined query's.

## EDE

| Attribute | Value |
|---|---|
| Grain | Pending |
| Identifier | Pending |
| Source | Pending — authoritative `partner_permissions` relationship |
| Filters | Not defined. `source = 'EDE'` is a discovery filter only. |
| Activity date | Pending |
| SQL | `sql/ede_discovery.sql` — diagnostic only (run with `--ede-discovery`) |
| Known limitations | No EDE values are produced. |
| Validation status | **VALIDATION PENDING** |

## Plan Year PY2027

Source Pending. Never queried, never filled, never extrapolated. Shown as `PY2027 — Source Pending` and disabled in the UI.

## OE_Day

Column exists in the normalized model but stays empty until `OFFICIAL_OE_START_DATES` in `config/settings.py` is populated with business-confirmed dates.
