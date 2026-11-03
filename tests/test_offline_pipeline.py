"""
Offline tests for processing, validation, SQL guards, and dashboard rendering.

All data here is SYNTHETIC test fixture data. It is never written to data/ or
output/; the rendered test dashboard goes to tests/_output/ only.

    .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from src import validator  # noqa: E402
from src.dashboard_generator import generate_dashboard  # noqa: E402
from src.data_processor import DataProcessingError, process_trend  # noqa: E402
from src.query_executor import SqlFileError, _assert_read_only, load_sql, load_sql_sections  # noqa: E402
from src.trend_builder import build_payload  # noqa: E402

TEST_OUTPUT = ROOT / "tests" / "_output"


def synthetic_trend(metric: str, with_time: bool = False) -> pd.DataFrame:
    """SYNTHETIC fixture: shaped like a trend query result, values are arbitrary."""
    rows = []
    for py, start, counts in ((2025, "2024-11-01", [50, 20, 10, 5]), (2026, "2025-11-01", [80, 30, 15, 7])):
        cum = 0
        for i, n in enumerate(counts):
            day = pd.Timestamp(start) + pd.Timedelta(days=i)
            parts = [(day + pd.Timedelta(hours=9), n - 2), (day + pd.Timedelta(hours=15), 2)] if with_time else [(day, n)]
            for ts, c in parts:
                cum += c
                rows.append({"Plan_Year": py, "Metric_Date": ts, "Metric": metric,
                             "Daily_Count": c, "Cumulative_Count": cum})
    return pd.DataFrame(rows)


SYNTHETIC_CONTROLS = {m: {2025: 85, 2026: 132} for m in ("Enrollment", "Cancellation", "Termination")}


class ProcessorTests(unittest.TestCase):
    def test_rolls_up_timestamps_to_days(self):
        out = process_trend(synthetic_trend("Enrollment", with_time=True), "Enrollment", [2025, 2026])
        self.assertEqual(len(out), 8)
        self.assertEqual(out[out.Plan_Year == 2026].Cumulative_Count.iloc[-1], 132)
        self.assertEqual(out[out.Plan_Year == 2025].Daily_Count.tolist(), [50, 20, 10, 5])
        self.assertEqual(set(out.Grain), {"Person"})
        self.assertEqual(list(out.columns), settings.NORMALIZED_COLUMNS)
        self.assertTrue(out.OE_Day.isna().all(), "OE_Day must stay empty until official OE dates are confirmed")

    def test_policy_grain_lineage(self):
        out = process_trend(synthetic_trend("Termination"), "Termination", [2025, 2026])
        self.assertEqual(set(out.Grain), {"Policy"})
        self.assertEqual(set(out.Date_Field), {"enrollment_last_update_date"})
        self.assertEqual(set(out.Source_Table), {"DEC31 Snapshot"})

    def test_missing_column_fails(self):
        with self.assertRaises(DataProcessingError):
            process_trend(synthetic_trend("Enrollment").drop(columns=["Cumulative_Count"]), "Enrollment", [2025, 2026])

    def test_empty_result_fails(self):
        with self.assertRaises(DataProcessingError):
            process_trend(synthetic_trend("Enrollment").iloc[0:0], "Enrollment", [2025, 2026])

    def test_missing_plan_year_fails(self):
        raw = synthetic_trend("Enrollment")
        with self.assertRaises(DataProcessingError):
            process_trend(raw[raw.Plan_Year == 2025], "Enrollment", [2025, 2026])

    def test_inconsistent_cumulative_fails(self):
        raw = synthetic_trend("Enrollment")
        raw.loc[raw.index[-1], "Cumulative_Count"] += 1
        with self.assertRaises(DataProcessingError):
            process_trend(raw, "Enrollment", [2025, 2026])


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.norm = pd.concat([process_trend(synthetic_trend(m), m, [2025, 2026])
                               for m in ("Enrollment", "Cancellation", "Termination")], ignore_index=True)

    def test_matched(self):
        with mock.patch.object(validator, "CONTROL_TOTALS", SYNTHETIC_CONTROLS):
            res = validator.validate(self.norm)
        self.assertEqual(set(validator.level1_status(res).values()), {settings.MATCHED})
        self.assertEqual(set(res[res.Level > 1].Status), {settings.VALIDATION_PENDING})

    def test_mismatch_keeps_actual_value(self):
        controls = {**SYNTHETIC_CONTROLS, "Enrollment": {2025: 85, 2026: 999}}
        with mock.patch.object(validator, "CONTROL_TOTALS", controls):
            res = validator.validate(self.norm)
        row = res[(res.Metric == "Enrollment") & (res.Plan_Year == 2026) & (res.Check == "control_total")].iloc[0]
        self.assertEqual(row.Status, settings.UNEXPLAINED_DIFFERENCE)
        self.assertEqual(row.Actual, 132)
        self.assertEqual(row.Difference, 132 - 999)
        self.assertTrue(validator.has_unexplained(res))
        status = validator.apply_status(self.norm, validator.level1_status(res))
        self.assertEqual(status[(status.Metric == "Enrollment") & (status.Plan_Year == 2026)].Cumulative_Count.max(), 132)

    def test_explained_difference_requires_registry_entry(self):
        controls = {**SYNTHETIC_CONTROLS, "Cancellation": {2025: 80, 2026: 132}}
        with mock.patch.object(validator, "CONTROL_TOTALS", controls), \
             mock.patch.object(validator, "EXPLAINED_DIFFERENCES", {("Cancellation", 2025): {"note": "test"}}):
            res = validator.validate(self.norm)
        self.assertEqual(validator.level1_status(res)[("Cancellation", 2025)], settings.EXPLAINED_DIFFERENCE)

    def test_recount_mismatch_flagged(self):
        recount = pd.DataFrame([{"Plan_Year": 2025, "Metric": "Enrollment", "Distinct_Count": 84}])
        with mock.patch.object(validator, "CONTROL_TOTALS", SYNTHETIC_CONTROLS):
            res = validator.validate(self.norm, level1_recount=recount)
        self.assertEqual(validator.level1_status(res)[("Enrollment", 2025)], settings.UNEXPLAINED_DIFFERENCE)


class SqlTests(unittest.TestCase):
    def test_project_sql_files_are_read_only_and_load(self):
        for metric in settings.active_metrics():
            self.assertIn("SELECT", load_sql(settings.METRICS[metric]["sql_file"]))
        self.assertEqual(set(load_sql_sections("validation.sql")), {
            "enrollment_level1_total", "policy_event_level1_total", "enrollment_level2_issuer",
            "policy_event_level2_issuer", "level3_status_category"})
        self.assertIn("source_ede_profile", load_sql_sections("ede_discovery.sql"))

    def test_trend_queries_never_return_identifiers(self):
        for metric in settings.active_metrics():
            sql = load_sql(settings.METRICS[metric]["sql_file"])
            final_select = sql[sql.rindex("SELECT"):]
            self.assertNotRegex(final_select, r"\benrollee_id\b|\benrollment_id\b")

    def test_write_statements_rejected(self):
        for bad in ("DELETE FROM dbo.x", "SELECT * INTO #t FROM dbo.x", "UPDATE dbo.x SET a=1", "EXEC sp_who"):
            with self.assertRaises(SqlFileError):
                _assert_read_only("t", bad)
        _assert_read_only("t", "SELECT enrollment_last_update_date FROM dbo.x -- DELETE in comment")

    def test_missing_sql_file(self):
        with self.assertRaises(SqlFileError):
            load_sql("does_not_exist.sql")


class DashboardTests(unittest.TestCase):
    def test_render(self):
        norm = pd.concat([process_trend(synthetic_trend(m), m, [2025, 2026])
                          for m in ("Enrollment", "Cancellation", "Termination")], ignore_index=True)
        with mock.patch.object(validator, "CONTROL_TOTALS", SYNTHETIC_CONTROLS):
            res = validator.validate(norm)
        norm = validator.apply_status(norm, validator.level1_status(res))
        payload = build_payload(norm, res, {"run_id": "test", "data_mode": "SYNTHETIC TEST FIXTURE",
                                            "extracted_at": "n/a"})
        out = generate_dashboard(payload, TEST_OUTPUT / "test_dashboard.html")
        html = out.read_text()

        self.assertIn("Georgia Access — Open Enrollment Historical Trend Report", html)
        embedded = json.loads(re.search(r'<script type="application/json" id="payload">(.*?)</script>',
                                        html, re.DOTALL).group(1))
        py27 = next(p for p in embedded["plan_years"] if p["year"] == 2027)
        self.assertFalse(py27["available"])
        self.assertFalse(py27["has_data"])
        self.assertNotIn("2027", embedded["series"].get("Enrollment", {}))
        ede = next(m for m in embedded["metrics"] if m["name"] == "EDE")
        self.assertFalse(ede["has_data"])
        self.assertEqual(set(embedded["traces"]), {f"{m}|{mode}" for m in ("Enrollment", "Cancellation", "Termination")
                                                   for mode in ("daily", "cumulative")})
        self.assertNotRegex(html.split('id="payload">')[1], r"enrollee_id\"\s*:|enrollment_id\"\s*:")


if __name__ == "__main__":
    unittest.main()
