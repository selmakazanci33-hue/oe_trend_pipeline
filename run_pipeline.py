#!/usr/bin/env python3
"""
Georgia Access — OE Historical Trend Pipeline.

    python run_pipeline.py                        # live: Azure -> SQL -> validate -> dashboard
    python run_pipeline.py --check-connection     # connection test only
    python run_pipeline.py --ede-discovery        # also run EDE discovery diagnostics
    python run_pipeline.py --skip-extended-validation
    python run_pipeline.py --from-run <RUN_ID>    # rebuild dashboard from a prior run's processed files

Exit codes: 0 success · 1 fatal error (no dashboard written) · 3 dashboard written with
UNEXPLAINED DIFFERENCE validation results.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.azure_connection import AzureConnectionError, connect_azure  # noqa: E402
from src.dashboard_generator import generate_dashboard  # noqa: E402
from src.data_processor import DataProcessingError, process_trend  # noqa: E402
from src.query_executor import (  # noqa: E402
    QueryExecutionError,
    SqlFileError,
    load_sql,
    load_sql_sections,
    run_query,
    run_sql_file,
)
from src.trend_builder import build_payload  # noqa: E402
from src.validator import apply_status, has_unexplained, level1_status, validate  # noqa: E402

logger = logging.getLogger("oe_trend_pipeline")

EXIT_OK, EXIT_FATAL, EXIT_VALIDATION = 0, 1, 3


def setup_logging(run_id: str) -> Path:
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = settings.LOGS_DIR / f"oe_trend_pipeline_{run_id}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    return log_file


def preflight_sql() -> None:
    """Fail before connecting if any required SQL file is missing or unsafe."""
    for metric in settings.active_metrics():
        load_sql(settings.METRICS[metric]["sql_file"])
    load_sql_sections("validation.sql")
    load_sql_sections(settings.METRICS["EDE"]["discovery_sql_file"])
    logger.info("SQL preflight passed")


def log_pending_items() -> None:
    for py, cfg in settings.PLAN_YEARS.items():
        if cfg["status"] == settings.PY_SOURCE_PENDING:
            logger.warning("PY%s — Source Pending: %s Not queried; no values produced.", py, cfg["pending_reason"])
    logger.warning("EDE — Validation Pending: authoritative partner_permissions relationship not identified. "
                   "No EDE values produced.")


def extract(engine, run_id: str, years: list[int]) -> pd.DataFrame:
    frames = []
    for metric in settings.active_metrics():
        cfg = settings.METRICS[metric]
        logger.info("Step — execute %s query (%s)", metric, cfg["sql_file"])
        raw = run_sql_file(engine, cfg["sql_file"])
        raw.to_csv(settings.RAW_DIR / f"{metric.lower()}_trend_{run_id}.csv", index=False)
        logger.info("Step — process %s", metric)
        norm = process_trend(raw, metric, years)
        logger.info("Step — validate %s control totals", metric)
        validate(norm)
        frames.append(norm)
    return pd.concat(frames, ignore_index=True)


def extended_validation(engine) -> dict[str, pd.DataFrame]:
    sections = load_sql_sections("validation.sql")
    results = {name: run_query(engine, f"validation.sql:{name}", sql) for name, sql in sections.items()}
    return {
        "level1_recount": pd.concat([results["enrollment_level1_total"], results["policy_event_level1_total"]],
                                    ignore_index=True),
        "level2_issuer": pd.concat([results["enrollment_level2_issuer"], results["policy_event_level2_issuer"]],
                                   ignore_index=True),
        "level3_status": results["level3_status_category"],
    }


def ede_discovery(engine, run_id: str) -> None:
    sections = load_sql_sections(settings.METRICS["EDE"]["discovery_sql_file"])
    for name, sql in sections.items():
        try:
            df = run_query(engine, f"ede_discovery.sql:{name}", sql)
        except QueryExecutionError as exc:
            logger.warning("EDE discovery section %s failed (diagnostic only): %s", name, exc)
            continue
        df.to_csv(settings.VALIDATION_DIR / f"ede_discovery_{name}_{run_id}.csv", index=False)
    logger.warning("EDE discovery is diagnostic only — EDE remains VALIDATION PENDING.")


def run_live(args, run_id: str) -> int:
    years = settings.available_plan_years()
    engine = connect_azure()
    if args.check_connection:
        return EXIT_OK

    normalized = extract(engine, run_id, years)

    extended = {}
    if args.skip_extended_validation:
        logger.warning("Extended validation skipped (--skip-extended-validation)")
    else:
        logger.info("Step — extended validation (Level 1 recount, Level 2 issuer, Level 3 status category)")
        extended = extended_validation(engine)
        for name, df in extended.items():
            df.to_csv(settings.VALIDATION_DIR / f"{name}_{run_id}.csv", index=False)

    if args.ede_discovery:
        ede_discovery(engine, run_id)

    engine.dispose()
    return finish(normalized, validate(normalized, **extended), run_id, data_mode="live",
                  extracted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def run_from_processed(run_id_source: str, run_id: str) -> int:
    norm_file = settings.PROCESSED_DIR / f"oe_trend_normalized_{run_id_source}.csv"
    val_file = settings.VALIDATION_DIR / f"validation_results_{run_id_source}.csv"
    manifest_file = settings.VALIDATION_DIR / f"run_manifest_{run_id_source}.json"
    for f in (norm_file, val_file, manifest_file):
        if not f.is_file():
            raise FileNotFoundError(f"--from-run {run_id_source}: missing {f}")
    manifest = json.loads(manifest_file.read_text())
    if manifest.get("data_mode") != "live":
        raise ValueError(f"--from-run {run_id_source}: source run was not a live extraction")
    normalized = pd.read_csv(norm_file, parse_dates=["Metric_Date"])
    normalized["OE_Day"] = normalized["OE_Day"].astype("Int64")
    validation = pd.read_csv(val_file)
    logger.warning("Rebuilding dashboard from processed files of run %s (not a live query)", run_id_source)
    return finish(normalized, validation, run_id, data_mode=f"rebuilt from run {run_id_source}",
                  extracted_at=manifest.get("extracted_at"))


def finish(normalized: pd.DataFrame, validation: pd.DataFrame, run_id: str, *, data_mode: str,
           extracted_at: str | None) -> int:
    logger.info("Step — normalize and apply validation status")
    normalized = apply_status(normalized, level1_status(validation))

    if data_mode == "live":
        normalized.to_csv(settings.PROCESSED_DIR / f"oe_trend_normalized_{run_id}.csv", index=False)
        validation.to_csv(settings.VALIDATION_DIR / f"validation_results_{run_id}.csv", index=False)

    log_pending_items()
    logger.info("Step — build Plotly traces and dashboard")
    payload = build_payload(normalized, validation, {"run_id": run_id, "data_mode": data_mode,
                                                     "extracted_at": extracted_at})
    out = generate_dashboard(payload, settings.DASHBOARD_FILE)

    failed = has_unexplained(validation)
    manifest = {
        "run_id": run_id,
        "data_mode": data_mode,
        "extracted_at": extracted_at,
        "dashboard": str(out),
        "metrics": sorted(normalized.Metric.unique().tolist()),
        "plan_years": sorted(int(p) for p in normalized.Plan_Year.unique()),
        "level1_status": {f"{m}|PY{py}": s for (m, py), s in level1_status(validation).items()},
        "unexplained_differences": failed,
        "pending": ["PY2027 — Source Pending", "EDE — Validation Pending"],
    }
    (settings.VALIDATION_DIR / f"run_manifest_{run_id}.json").write_text(json.dumps(manifest, indent=2))

    for key, status in manifest["level1_status"].items():
        logger.info("Level 1 result — %s: %s", key, status)
    logger.info("Dashboard output — %s", out)
    if failed:
        logger.error("Validation mismatch — UNEXPLAINED DIFFERENCE present; dashboard shows the failure")
        return EXIT_VALIDATION
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-connection", action="store_true", help="Only test the Azure connection")
    parser.add_argument("--skip-extended-validation", action="store_true",
                        help="Skip Level 1 recount / Level 2 issuer / Level 3 status queries")
    parser.add_argument("--ede-discovery", action="store_true", help="Run EDE discovery diagnostics")
    parser.add_argument("--from-run", metavar="RUN_ID", help="Rebuild dashboard from a prior live run's files")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    for d in (settings.RAW_DIR, settings.PROCESSED_DIR, settings.VALIDATION_DIR, settings.OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    log_file = setup_logging(run_id)
    logger.info("Pipeline start — run_id=%s log=%s", run_id, log_file)

    try:
        preflight_sql()
        code = run_from_processed(args.from_run, run_id) if args.from_run else run_live(args, run_id)
    except AzureConnectionError as exc:
        logger.error("FATAL — Azure connection: %s", exc)
        code = EXIT_FATAL
    except SqlFileError as exc:
        logger.error("FATAL — SQL file: %s", exc)
        code = EXIT_FATAL
    except QueryExecutionError as exc:
        logger.error("FATAL — query: %s", exc)
        code = EXIT_FATAL
    except DataProcessingError as exc:
        logger.error("FATAL — data processing: %s", exc)
        code = EXIT_FATAL
    except (FileNotFoundError, ValueError) as exc:
        logger.error("FATAL — %s", exc)
        code = EXIT_FATAL

    if code == EXIT_FATAL:
        logger.error("No dashboard written for this run. No cached or substituted data was used.")
        if settings.DASHBOARD_FILE.is_file():
            logger.warning("Existing %s is from an earlier run and was NOT updated", settings.DASHBOARD_FILE)
    logger.info("Pipeline end — run_id=%s exit_code=%s", run_id, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
