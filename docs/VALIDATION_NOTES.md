# Validation Notes

## Control totals are references, not dashboard values

The values below live in `config/settings.py → CONTROL_TOTALS`. They are compared against query output. They are **never** written into the dashboard as metric values, and a mismatch never causes the observed value to be replaced.

| Metric | Grain | Snapshot | PY2025 | PY2026 | Origin |
|---|---|---|---:|---:|---|
| Enrollment | Person | NOV30 | 633,677 | 1,061,718 | POC — distinct OE enrolled people |
| Cancellation | Policy | DEC31 | 536,086 | 370,412 | POC — proxy-date logic |
| Termination | Policy | DEC31 | 548,512 | 18,444 | POC — proxy-date logic |

Cancellation/Termination controls are policy-level cumulative results under proxy logic. They are not business performance comparisons.

## Status vocabulary

| Status | Meaning |
|---|---|
| MATCHED | Observed equals the reference exactly |
| EXPLAINED DIFFERENCE | Differs, and a business-approved explanation exists in `EXPLAINED_DIFFERENCES` |
| UNEXPLAINED DIFFERENCE | Differs with no approved explanation — dashboard shows a red banner; exit code 3 |
| VALIDATION PENDING | No reference exists yet |

## Checks

| Level | Check | Reference |
|---|---|---|
| 1 | `control_total` | `CONTROL_TOTALS` |
| 1 | `independent_distinct_recount` | `COUNT(DISTINCT identifier)` with identical filters (`validation.sql`) |
| 1 | `daily_sum_equals_final_cumulative` | Internal consistency |
| 2 | `issuer_distribution` | Distinct counts by `hios_issuer_id` — no issuer controls yet → PENDING |
| 3 | `status_category_distribution` | DEC31 distinct policies by status — no category controls yet → PENDING |

The metric's `Validation_Status` shown in the dashboard is the Level 1 roll-up. **A Level 1 match does not make a metric production-ready.** Levels 2–3 remain pending, and Cancellation/Termination additionally depend on business confirmation of the event-date definition.

For person grain, the sum of issuer counts can exceed the total when one person appears under more than one issuer; this is reported, not treated as an error.

## Current run status

No live run has completed yet: Azure connection prerequisites are missing on this workstation (see `DISCOVERY_FINDINGS.md §1`). Live validation results will be written to `data/validation/validation_results_<run_id>.csv` on the first successful run.

## Offline verification

`tests/test_offline_pipeline.py` exercises processing, validation (match, mismatch-retains-actual, explained-difference registry, recount mismatch), SQL read-only guards, and dashboard rendering using **synthetic fixtures** written only to `tests/_output/`.
