"""
Builds Plotly traces and the dashboard payload from the validated, normalized dataset.

One trace per (Metric, Plan_Year, Mode). Metrics are never combined on one chart,
so person-grain and policy-grain series are never mixed.
"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from config.settings import (
    DASHBOARD_SUBTITLE,
    DASHBOARD_TITLE,
    METRIC_ORDER,
    METRICS,
    PLAN_YEARS,
    PY_AVAILABLE,
)

PY_COLORS = {2025: "#1F4E79", 2026: "#E07B39", 2027: "#6B8E23"}
MODES = {"daily": "Daily_Count", "cumulative": "Cumulative_Count"}

HOVER = (
    "<b>%{meta.label}</b><br>"
    "Metric: %{meta.metric}<br>"
    "Date: %{x|%b %d, %Y}<br>"
    "Daily Count: %{customdata[0]:,}<br>"
    "Cumulative Count: %{customdata[1]:,}<br>"
    "Grain: %{meta.grain}"
    "<extra></extra>"
)


def build_traces(normalized: pd.DataFrame) -> dict[str, list[dict]]:
    """Return {'<Metric>|<mode>': [trace, ...]} as plain JSON-ready dicts."""
    traces: dict[str, list[dict]] = {}
    for metric in METRIC_ORDER:
        sub_metric = normalized[normalized.Metric == metric]
        if sub_metric.empty:
            continue
        for mode, column in MODES.items():
            fig = go.Figure()
            for py in sorted(sub_metric.Plan_Year.unique()):
                sub = sub_metric[sub_metric.Plan_Year == py].sort_values("Metric_Date")
                fig.add_trace(go.Scatter(
                    x=sub.Metric_Date.dt.strftime("%Y-%m-%d").tolist(),
                    y=sub[column].astype(int).tolist(),
                    customdata=sub[["Daily_Count", "Cumulative_Count"]].astype(int).values.tolist(),
                    mode="lines+markers" if mode == "daily" else "lines",
                    marker={"size": 4},
                    line={"color": PY_COLORS.get(int(py), "#555"), "width": 2.5},
                    name=PLAN_YEARS[int(py)]["label"],
                    meta={"plan_year": int(py), "label": PLAN_YEARS[int(py)]["label"],
                          "metric": metric, "grain": METRICS[metric]["grain"]},
                    hovertemplate=HOVER,
                ))
            traces[f"{metric}|{mode}"] = json.loads(pio.to_json(fig, validate=True))["data"]
    return traces


def build_base_layout() -> dict:
    layout = go.Layout(
        template="plotly_white",
        margin={"l": 70, "r": 30, "t": 50, "b": 60},
        hovermode="closest",
        legend={"orientation": "h", "y": 1.08, "x": 0},
        xaxis={"title": {"text": "Metric_Date"}, "type": "date", "showgrid": True},
        yaxis={"tickformat": ",", "rangemode": "tozero"},
        font={"family": "Segoe UI, Helvetica Neue, Arial, sans-serif", "size": 13},
    )
    return json.loads(pio.to_json(go.Figure(layout=layout)))["layout"]


def build_series(normalized: pd.DataFrame) -> dict:
    """Compact per-(metric, year) rows for the comparison table."""
    out: dict[str, dict[str, list]] = {}
    for (metric, py), sub in normalized.groupby(["Metric", "Plan_Year"]):
        sub = sub.sort_values("Metric_Date")
        out.setdefault(metric, {})[str(int(py))] = {
            "dates": sub.Metric_Date.dt.strftime("%Y-%m-%d").tolist(),
            "daily": sub.Daily_Count.astype(int).tolist(),
            "cumulative": sub.Cumulative_Count.astype(int).tolist(),
            "status": sub.Validation_Status.iloc[-1],
            "grain": sub.Grain.iloc[-1],
            "source": sub.Source_Table.iloc[-1],
            "date_field": sub.Date_Field.iloc[-1],
        }
    return out


def build_payload(normalized: pd.DataFrame, validation: pd.DataFrame, run_meta: dict) -> dict:
    plan_years = [
        {"year": py, "label": cfg["label"], "available": cfg["status"] == PY_AVAILABLE,
         "has_data": bool((normalized.Plan_Year == py).any()),
         "pending_reason": cfg.get("pending_reason", ""),
         "data_owner_question": cfg.get("data_owner_question", "")}
        for py, cfg in sorted(PLAN_YEARS.items())
    ]
    metrics = [
        {"name": m, **{k: METRICS[m][k] for k in (
            "status", "grain", "identifier", "source_table", "date_field", "filters",
            "method", "date_semantics", "validation_note", "limitations")},
         "has_data": bool((normalized.Metric == m).any())}
        for m in METRIC_ORDER
    ]
    val = validation.copy()
    val = val.astype(object).where(val.notna(), None)
    return {
        "title": DASHBOARD_TITLE,
        "subtitle": DASHBOARD_SUBTITLE,
        "run": {**run_meta, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        "plan_years": plan_years,
        "metrics": metrics,
        "traces": build_traces(normalized),
        "layout": build_base_layout(),
        "series": build_series(normalized),
        "validation": val.to_dict(orient="records"),
        "colors": {str(k): v for k, v in PY_COLORS.items()},
    }
