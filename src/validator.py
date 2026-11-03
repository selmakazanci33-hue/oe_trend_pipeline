"""
Validation layer.

Level 1 — totals:
    * trend final Cumulative_Count vs control total (validation reference)
    * trend final Cumulative_Count vs independent COUNT(DISTINCT) recount
    * sum of Daily_Count vs final Cumulative_Count (internal consistency)
Level 2 — issuer distribution (no issuer controls yet -> VALIDATION PENDING)
Level 3 — status category distribution (no category controls yet -> VALIDATION PENDING)

A mismatch is recorded and surfaced; the observed value is never replaced by the control.
A matched total alone never makes a metric production-ready.
"""

from __future__ import annotations

import logging

import pandas as pd

from config.settings import (
    CONTROL_SOURCES,
    CONTROL_TOTALS,
    EXPLAINED_DIFFERENCE,
    EXPLAINED_DIFFERENCES,
    MATCHED,
    UNEXPLAINED_DIFFERENCE,
    VALIDATION_PENDING,
)
from src.data_processor import final_totals

logger = logging.getLogger(__name__)

RESULT_COLUMNS = ["Metric", "Plan_Year", "Level", "Check", "Expected", "Actual", "Difference", "Status", "Note"]


def _row(metric, py, level, check, expected, actual, status, note="") -> dict:
    diff = None if expected is None or actual is None else int(actual) - int(expected)
    return dict(Metric=metric, Plan_Year=py, Level=level, Check=check, Expected=expected,
                Actual=actual, Difference=diff, Status=status, Note=note)


def _compare(metric: str, py: int, expected: int, actual: int) -> tuple[str, str]:
    if int(expected) == int(actual):
        return MATCHED, ""
    explanation = EXPLAINED_DIFFERENCES.get((metric, py))
    if explanation:
        return EXPLAINED_DIFFERENCE, explanation.get("note", "Business-approved explanation on file")
    return UNEXPLAINED_DIFFERENCE, "Observed value retained; control NOT substituted."


def validate(
    normalized: pd.DataFrame,
    level1_recount: pd.DataFrame | None = None,
    level2_issuer: pd.DataFrame | None = None,
    level3_status: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    totals = final_totals(normalized)

    for t in totals.itertuples(index=False):
        metric, py, final = t.Metric, int(t.Plan_Year), int(t.Final_Cumulative)

        status = MATCHED if int(t.Daily_Sum) == final else UNEXPLAINED_DIFFERENCE
        rows.append(_row(metric, py, 1, "daily_sum_equals_final_cumulative", int(t.Daily_Sum), final, status))

        control = CONTROL_TOTALS.get(metric, {}).get(py)
        if control is None:
            rows.append(_row(metric, py, 1, "control_total", None, final, VALIDATION_PENDING,
                             "No control total on file"))
        else:
            status, note = _compare(metric, py, control, final)
            rows.append(_row(metric, py, 1, "control_total", control, final, status,
                             note or CONTROL_SOURCES.get(metric, "")))

        if level1_recount is not None:
            match = level1_recount[(level1_recount.Metric == metric) & (level1_recount.Plan_Year.astype(int) == py)]
            if match.empty:
                rows.append(_row(metric, py, 1, "independent_distinct_recount", None, final, UNEXPLAINED_DIFFERENCE,
                                 "Recount query returned no row for this metric/year"))
            else:
                recount = int(match.Distinct_Count.iloc[0])
                status = MATCHED if recount == final else UNEXPLAINED_DIFFERENCE
                rows.append(_row(metric, py, 1, "independent_distinct_recount", recount, final, status,
                                 "COUNT(DISTINCT identifier) with identical filters"))

        if level2_issuer is not None:
            sub = level2_issuer[(level2_issuer.Metric == metric) & (level2_issuer.Plan_Year.astype(int) == py)]
            issuer_sum = int(sub.Distinct_Count.sum())
            note = (f"{sub.Issuer.nunique()} issuers; sum of issuer counts = {issuer_sum:,}. "
                    "No issuer-level controls on file.")
            if issuer_sum != final:
                note += " Sum differs from total — an identifier may appear under more than one issuer."
            rows.append(_row(metric, py, 2, "issuer_distribution", None, issuer_sum, VALIDATION_PENDING, note))
        else:
            rows.append(_row(metric, py, 2, "issuer_distribution", None, None, VALIDATION_PENDING,
                             "Not run"))

        if level3_status is not None and metric in ("Cancellation", "Termination"):
            status_name = {"Cancellation": "Cancelled", "Termination": "Terminated"}[metric]
            sub = level3_status[level3_status.Plan_Year.astype(int) == py]
            categories = ", ".join(f"{r.Status_Category}={int(r.Distinct_Policies):,}"
                                   for r in sub.sort_values("Status_Category").itertuples())
            cat_count = sub.loc[sub.Status_Category == status_name, "Distinct_Policies"]
            rows.append(_row(metric, py, 3, "status_category_distribution", None,
                             int(cat_count.iloc[0]) if not cat_count.empty else None, VALIDATION_PENDING,
                             f"DEC31 distinct policies by status: {categories}. No category controls on file."))
        else:
            rows.append(_row(metric, py, 3, "status_category_distribution", None, None, VALIDATION_PENDING,
                             "No business/status category controls on file"))

    results = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    for col in ("Expected", "Actual", "Difference"):
        results[col] = results[col].astype("Int64")
    for r in results.itertuples(index=False):
        log = logger.warning if r.Status == UNEXPLAINED_DIFFERENCE else logger.info
        log("Validation L%s %s PY%s %s — %s expected=%s actual=%s diff=%s",
            r.Level, r.Metric, r.Plan_Year, r.Check, r.Status, r.Expected, r.Actual, r.Difference)
    return results


def level1_status(results: pd.DataFrame) -> dict[tuple[str, int], str]:
    """Roll Level 1 checks up to one status per (Metric, Plan_Year)."""
    out: dict[tuple[str, int], str] = {}
    for (metric, py), grp in results[results.Level == 1].groupby(["Metric", "Plan_Year"]):
        statuses = set(grp.Status)
        if UNEXPLAINED_DIFFERENCE in statuses:
            out[(metric, int(py))] = UNEXPLAINED_DIFFERENCE
        elif EXPLAINED_DIFFERENCE in statuses:
            out[(metric, int(py))] = EXPLAINED_DIFFERENCE
        elif statuses == {MATCHED}:
            out[(metric, int(py))] = MATCHED
        else:
            out[(metric, int(py))] = VALIDATION_PENDING
    return out


def apply_status(normalized: pd.DataFrame, status_map: dict[tuple[str, int], str]) -> pd.DataFrame:
    df = normalized.copy()
    df["Validation_Status"] = [
        status_map.get((m, int(py)), VALIDATION_PENDING) for m, py in zip(df.Metric, df.Plan_Year)
    ]
    return df


def has_unexplained(results: pd.DataFrame) -> bool:
    return bool((results.Status == UNEXPLAINED_DIFFERENCE).any())
