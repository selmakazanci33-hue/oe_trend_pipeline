"""
Metric-specific processing of trend query results into the normalized model.

Responsibilities:
- required-column and empty-result checks
- Metric_Date normalized to a calendar date; if the source column carries a time
  component, same-day rows are summed (counts are additive because each
  person/policy is assigned exactly one Metric_Date) and Cumulative_Count is
  recomputed. The recomputed final total must equal the SQL final total.
- Grain / Source_Table / Date_Field lineage attached to every row
- OE_Day added only when official OE start dates are configured
"""

from __future__ import annotations

import logging

import pandas as pd

from config.settings import (
    METRICS,
    NORMALIZED_COLUMNS,
    OFFICIAL_OE_START_DATES,
    TREND_REQUIRED_COLUMNS,
    VALIDATION_PENDING,
)

logger = logging.getLogger(__name__)


class DataProcessingError(RuntimeError):
    """Query result is structurally unusable."""


def check_required_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataProcessingError(f"{name}: missing required column(s) {missing}; got {list(df.columns)}")


def process_trend(raw: pd.DataFrame, metric: str, expected_years: list[int]) -> pd.DataFrame:
    """Turn one metric's raw trend result into normalized rows."""
    cfg = METRICS[metric]
    check_required_columns(raw, TREND_REQUIRED_COLUMNS, metric)
    if raw.empty:
        raise DataProcessingError(f"{metric}: query returned no rows")

    df = raw[TREND_REQUIRED_COLUMNS].copy()
    df["Plan_Year"] = pd.to_numeric(df["Plan_Year"], errors="raise").astype(int)
    df["Metric_Date"] = pd.to_datetime(df["Metric_Date"], errors="raise")
    df["Daily_Count"] = pd.to_numeric(df["Daily_Count"], errors="raise").astype("int64")
    df["Cumulative_Count"] = pd.to_numeric(df["Cumulative_Count"], errors="raise").astype("int64")

    unexpected_metric = set(df["Metric"].unique()) - {metric}
    if unexpected_metric:
        raise DataProcessingError(f"{metric}: unexpected Metric values {sorted(unexpected_metric)}")
    if df[["Plan_Year", "Metric_Date", "Daily_Count", "Cumulative_Count"]].isna().any().any():
        raise DataProcessingError(f"{metric}: null values in trend columns")
    if (df["Daily_Count"] < 0).any():
        raise DataProcessingError(f"{metric}: negative Daily_Count")

    unexpected_years = sorted(set(df["Plan_Year"]) - set(expected_years))
    if unexpected_years:
        raise DataProcessingError(f"{metric}: unexpected Plan_Year values {unexpected_years}")
    missing_years = sorted(set(expected_years) - set(df["Plan_Year"]))
    if missing_years:
        raise DataProcessingError(f"{metric}: no rows for Plan_Year {missing_years}")

    sql_final = df.sort_values("Metric_Date").groupby("Plan_Year")["Cumulative_Count"].last()

    has_time = (df["Metric_Date"] != df["Metric_Date"].dt.normalize()).any()
    df["Metric_Date"] = df["Metric_Date"].dt.normalize()
    daily = (
        df.groupby(["Plan_Year", "Metric_Date", "Metric"], as_index=False)["Daily_Count"].sum()
        .sort_values(["Plan_Year", "Metric_Date"])
        .reset_index(drop=True)
    )
    if has_time:
        logger.info(
            "%s: %s carries a time component — %d timestamp rows rolled up to %d calendar days",
            metric, cfg["date_field"], len(df), len(daily),
        )
    daily["Cumulative_Count"] = daily.groupby("Plan_Year")["Daily_Count"].cumsum()

    recomputed_final = daily.groupby("Plan_Year")["Cumulative_Count"].last()
    for py in expected_years:
        if int(recomputed_final[py]) != int(sql_final[py]):
            raise DataProcessingError(
                f"{metric} PY{py}: day roll-up total {int(recomputed_final[py]):,} "
                f"!= SQL final cumulative {int(sql_final[py]):,}"
            )

    daily["Grain"] = cfg["grain"]
    daily["Source_Table"] = cfg["source_label"]
    daily["Date_Field"] = cfg["date_field"]
    daily["Validation_Status"] = VALIDATION_PENDING
    daily["OE_Day"] = add_oe_day(daily)

    logger.info(
        "Processed %s — %s",
        metric,
        ", ".join(f"PY{py}: {len(daily[daily.Plan_Year == py])} days, total {int(recomputed_final[py]):,}"
                  for py in expected_years),
    )
    return daily[NORMALIZED_COLUMNS]


def add_oe_day(df: pd.DataFrame) -> pd.Series:
    """Day number relative to the official OE start (day 1 = start). Empty until dates are confirmed."""
    if not OFFICIAL_OE_START_DATES:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Int64")
    starts = df["Plan_Year"].map(lambda py: pd.Timestamp(OFFICIAL_OE_START_DATES[py])
                                 if py in OFFICIAL_OE_START_DATES else pd.NaT)
    return ((df["Metric_Date"] - starts).dt.days + 1).astype("Int64")


def final_totals(normalized: pd.DataFrame) -> pd.DataFrame:
    """Final Cumulative_Count per (Metric, Plan_Year)."""
    return (
        normalized.sort_values("Metric_Date")
        .groupby(["Metric", "Plan_Year"], as_index=False)
        .agg(Final_Cumulative=("Cumulative_Count", "last"),
             Daily_Sum=("Daily_Count", "sum"),
             Last_Date=("Metric_Date", "max"),
             Days=("Metric_Date", "nunique"))
    )
