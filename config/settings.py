"""
Central configuration for the OE Historical Trend Pipeline.

Holds paths, the Plan Year registry, the metric registry, and validation
control totals. Control totals are validation references only — they are
never written into the dashboard as metric values.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

SQL_DIR = PROJECT_ROOT / "sql"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
VALIDATION_DIR = DATA_DIR / "validation"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"
DASHBOARD_FILE = OUTPUT_DIR / "oe_trend_dashboard.html"

DASHBOARD_TITLE = "Georgia Access — Open Enrollment Historical Trend Report"
DASHBOARD_SUBTITLE = "Historical Plan Year comparison of key Open Enrollment metrics"

# ---------------------------------------------------------------------------
# Validation statuses (the only values allowed anywhere in the pipeline)
# ---------------------------------------------------------------------------
MATCHED = "MATCHED"
EXPLAINED_DIFFERENCE = "EXPLAINED DIFFERENCE"
UNEXPLAINED_DIFFERENCE = "UNEXPLAINED DIFFERENCE"
VALIDATION_PENDING = "VALIDATION PENDING"
VALIDATION_STATUSES = (MATCHED, EXPLAINED_DIFFERENCE, UNEXPLAINED_DIFFERENCE, VALIDATION_PENDING)

# ---------------------------------------------------------------------------
# Plan Year registry
#   AVAILABLE      -> queried, validated, charted
#   SOURCE_PENDING -> shown in the UI as unavailable; never queried, never filled
# ---------------------------------------------------------------------------
PY_AVAILABLE = "AVAILABLE"
PY_SOURCE_PENDING = "SOURCE_PENDING"

PLAN_YEARS: dict[int, dict] = {
    2025: {"label": "PY2025", "status": PY_AVAILABLE},
    2026: {"label": "PY2026", "status": PY_AVAILABLE},
    2027: {
        "label": "PY2027 — Source Pending",
        "status": PY_SOURCE_PENDING,
        "pending_reason": (
            "The backend enrollment source used by the PY2027 OE Executive Dashboard "
            "has not been identified."
        ),
        "data_owner_question": (
            "For the PY2027 OE Executive Dashboard, what backend table/query is used for "
            "the 'Currently Enrolled People' metric, and what grain and as-of-date logic "
            "is used for that count?"
        ),
    },
}


def available_plan_years() -> list[int]:
    return sorted(py for py, cfg in PLAN_YEARS.items() if cfg["status"] == PY_AVAILABLE)


# POC / discovery windows used inside enrollment_trend.sql.
# These are NOT official OE start dates.
POC_DISCOVERY_WINDOW_START = {2025: "2024-10-01", 2026: "2025-10-01"}

# Official OE start dates — intentionally empty until business confirms them.
# When populated (e.g. {2026: "2025-11-01"}), data_processor adds OE_Day.
OFFICIAL_OE_START_DATES: dict[int, str] = {}

# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------
METRIC_STATUS_ACTIVE = "ACTIVE"
METRIC_STATUS_PENDING = "DEFINITION_PENDING"

METRICS: dict[str, dict] = {
    "Enrollment": {
        "status": METRIC_STATUS_ACTIVE,
        "sql_file": "enrollment_trend.sql",
        "grain": "Person",
        "identifier": "enrollee_id",
        "source_table": "dbo.Enrollments_PY2526_NOV30",
        "source_label": "NOV30 Snapshot",
        "date_field": "enrollment_confirmation_date",
        "filters": (
            "application_type = 'OE'; enrollment_status_description = 'Enrolled'; "
            "enrollee_status_description = 'Enrolled'; enrollment_confirmation_date IS NOT NULL; "
            "POC discovery window: PY2025 >= 2024-10-01, PY2026 >= 2025-10-01"
        ),
        "method": "First confirmation per person (MIN enrollment_confirmation_date) under current POC filters.",
        "date_semantics": "Confirmation activity date. Not a coverage-effective date; Enrolled does not imply active coverage.",
        "validation_note": "POC validated against NOV30 snapshot control.",
        "limitations": [
            "Enrollment trend is not an active-coverage trend.",
            "Date windows are POC discovery windows, not official OE dates.",
        ],
    },
    "Cancellation": {
        "status": METRIC_STATUS_ACTIVE,
        "sql_file": "cancellation_trend.sql",
        "grain": "Policy",
        "identifier": "enrollment_id",
        "source_table": "dbo.Enrollments_PY2526_DEC31",
        "source_label": "DEC31 Snapshot",
        "date_field": "enrollment_last_update_date",
        "filters": "enrollment_status_description = 'Cancelled'; enrollment_id and enrollment_last_update_date NOT NULL",
        "method": "One row per policy: MAX(enrollment_last_update_date) per (coverage_year, enrollment_id, status).",
        "date_semantics": "PROXY activity date — not a confirmed cancellation event timestamp.",
        "validation_note": "Proxy date — business validation required.",
        "limitations": [
            "enrollment_last_update_date is a proxy, not an authoritative cancellation event date.",
            "PY2025 vs PY2026 differences may reflect lifecycle rules, historical processing, or snapshot behavior.",
        ],
    },
    "Termination": {
        "status": METRIC_STATUS_ACTIVE,
        "sql_file": "termination_trend.sql",
        "grain": "Policy",
        "identifier": "enrollment_id",
        "source_table": "dbo.Enrollments_PY2526_DEC31",
        "source_label": "DEC31 Snapshot",
        "date_field": "enrollment_last_update_date",
        "filters": "enrollment_status_description = 'Terminated'; enrollment_id and enrollment_last_update_date NOT NULL",
        "method": "One row per policy: MAX(enrollment_last_update_date) per (coverage_year, enrollment_id, status).",
        "date_semantics": "PROXY activity date — not a confirmed termination event timestamp.",
        "validation_note": "Proxy date — business validation required.",
        "limitations": [
            "enrollment_last_update_date is a proxy, not an authoritative termination event date.",
            "PY2025 vs PY2026 differences may reflect lifecycle rules, historical processing, or snapshot behavior.",
        ],
    },
    "EDE": {
        "status": METRIC_STATUS_PENDING,
        "sql_file": None,
        "discovery_sql_file": "ede_discovery.sql",
        "grain": "Pending",
        "identifier": "Pending",
        "source_table": "Pending — partner_permissions relationship",
        "source_label": "Pending",
        "date_field": "Pending",
        "filters": "Not defined. source = 'EDE' is a discovery filter only, not the Executive Dashboard definition.",
        "method": (
            "Executive Dashboard documentation indicates EDE enrollments are identified via relationships "
            "to partner_permissions and counted without filtering by status or insurance type. "
            "The authoritative join has not been identified."
        ),
        "date_semantics": "Pending",
        "validation_note": "Validation Pending — authoritative partner_permissions relationship required.",
        "limitations": ["No production EDE values are produced until the partner_permissions join is validated."],
    },
}

METRIC_ORDER = ["Enrollment", "Cancellation", "Termination", "EDE"]


def active_metrics() -> list[str]:
    return [m for m in METRIC_ORDER if METRICS[m]["status"] == METRIC_STATUS_ACTIVE]


# ---------------------------------------------------------------------------
# Validation controls (Level 1 — totals). Validation references only.
# ---------------------------------------------------------------------------
CONTROL_TOTALS: dict[str, dict[int, int]] = {
    "Enrollment": {2025: 633_677, 2026: 1_061_718},
    "Cancellation": {2025: 536_086, 2026: 370_412},
    "Termination": {2025: 548_512, 2026: 18_444},
}

CONTROL_SOURCES: dict[str, str] = {
    "Enrollment": "POC discovery — distinct OE enrolled people, NOV30 snapshot",
    "Cancellation": "POC discovery — distinct cancelled policies, DEC31 snapshot (proxy date logic)",
    "Termination": "POC discovery — distinct terminated policies, DEC31 snapshot (proxy date logic)",
}

# Business-approved explanations for known differences, keyed by (metric, plan_year).
# Only an entry here can turn a mismatch into EXPLAINED DIFFERENCE.
EXPLAINED_DIFFERENCES: dict[tuple[str, int], dict] = {}

# Required columns returned by every trend query.
TREND_REQUIRED_COLUMNS = ["Plan_Year", "Metric_Date", "Metric", "Daily_Count", "Cumulative_Count"]

NORMALIZED_COLUMNS = [
    "Plan_Year",
    "Metric_Date",
    "Metric",
    "Daily_Count",
    "Cumulative_Count",
    "Grain",
    "Source_Table",
    "Date_Field",
    "Validation_Status",
    "OE_Day",
]
