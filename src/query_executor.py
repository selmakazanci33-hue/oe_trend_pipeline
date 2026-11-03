"""
Loads SQL files and executes them read-only against Azure SQL.

Every query in this project returns aggregated counts only; no person- or
policy-level identifiers leave the database.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from config.settings import SQL_DIR

logger = logging.getLogger(__name__)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|ALTER|DROP|TRUNCATE|CREATE|EXEC|EXECUTE|GRANT|REVOKE|INTO)\b",
    re.IGNORECASE,
)
_SECTION = re.compile(r"^--\s*name:\s*(\w+)\s*$", re.MULTILINE)


class SqlFileError(RuntimeError):
    """Missing, unreadable, or unsafe SQL file."""


class QueryExecutionError(RuntimeError):
    """Query failed in the database."""


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def _assert_read_only(name: str, sql: str) -> None:
    match = _FORBIDDEN.search(_strip_comments(sql))
    if match:
        raise SqlFileError(f"{name}: non-SELECT keyword '{match.group(1)}' is not allowed (read-only pipeline)")


def load_sql(filename: str) -> str:
    path = Path(SQL_DIR) / filename
    if not path.is_file():
        raise SqlFileError(f"SQL file not found: {path}")
    sql = path.read_text(encoding="utf-8").strip()
    if not _strip_comments(sql).strip():
        raise SqlFileError(f"SQL file is empty: {path}")
    _assert_read_only(filename, sql)
    return sql


def load_sql_sections(filename: str) -> dict[str, str]:
    """Split a multi-query file on ``-- name: <section>`` markers."""
    sql = load_sql(filename)
    markers = list(_SECTION.finditer(sql))
    if not markers:
        raise SqlFileError(f"{filename}: no '-- name: <section>' markers found")
    sections: dict[str, str] = {}
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(sql)
        body = sql[m.end():end].strip().rstrip(";")
        if _strip_comments(body).strip():
            sections[m.group(1)] = body
    return sections


def run_query(engine: Engine, name: str, sql: str) -> pd.DataFrame:
    _assert_read_only(name, sql)
    logger.info("Query start — %s", name)
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
    except Exception as exc:
        logger.error("Query failed — %s error_type=%s", name, type(exc).__name__)
        raise QueryExecutionError(f"Query '{name}' failed: {exc}") from exc
    logger.info("Query done — %s rows=%d seconds=%.1f", name, len(df), time.perf_counter() - started)
    return df


def run_sql_file(engine: Engine, filename: str) -> pd.DataFrame:
    return run_query(engine, filename, load_sql(filename))
