"""
Read-only Azure SQL connection for the OE Historical Trend Pipeline.

Follows the proven pattern of the reference implementation
gaaccess-develop16/834_issuer_etl/azure_reconciliation/azure_client.py:

- SQLAlchemy + pyodbc (``mssql+pyodbc:///?odbc_connect=...``)
- Authentication=ActiveDirectoryInteractive (passwordless; no PWD, no Trusted_Connection)
- Settings from this project's ``.env`` (load_dotenv override=True) or process environment
- Same variable names: SERVER / DATABASE / USERNAME / DRIVER / CONNECTION_TIMEOUT,
  with AZURE_SQL_* aliases
- Login is forced with ``SELECT 1 AS connection_test``

SELECT only. Never INSERT/UPDATE/DELETE/ALTER.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import ENV_FILE

logger = logging.getLogger(__name__)

AUTH_MODE = "ActiveDirectoryInteractive"
DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
# Interactive AAD login needs time for browser sign-in (default 5 minutes)
DEFAULT_CONNECTION_TIMEOUT = 300


class AzureConnectionError(RuntimeError):
    """Raised when the Azure SQL connection cannot be configured or established."""


def _env(key: str, alias: str = "") -> str:
    load_dotenv(ENV_FILE, override=True)
    val = os.getenv(key) or os.getenv(alias) or ""
    return str(val).strip().strip('"').strip("'")


def _connection_timeout() -> int:
    raw = _env("CONNECTION_TIMEOUT", "AZURE_CONNECTION_TIMEOUT")
    if raw:
        try:
            return max(30, int(raw))
        except ValueError:
            logger.warning("Invalid CONNECTION_TIMEOUT=%r — using default %s", raw, DEFAULT_CONNECTION_TIMEOUT)
    return DEFAULT_CONNECTION_TIMEOUT


def _azure_settings() -> dict[str, str]:
    return {
        "server": _env("SERVER", "AZURE_SQL_SERVER"),
        "database": _env("DATABASE", "AZURE_SQL_DATABASE"),
        "username": _env("USERNAME", "AZURE_SQL_USERNAME"),
        "driver": _env("DRIVER", "AZURE_SQL_DRIVER") or DEFAULT_DRIVER,
    }


def azure_configured() -> bool:
    """True when SERVER, DATABASE, and USERNAME are set. PASSWORD is not used."""
    cfg = _azure_settings()
    return bool(cfg["server"] and cfg["database"] and cfg["username"])


def connection_diagnostics() -> dict[str, Any]:
    """Connection diagnostics with no secrets and no username value."""
    cfg = _azure_settings()
    return {
        "env_file": str(ENV_FILE),
        "env_file_exists": ENV_FILE.is_file(),
        "server_present": bool(cfg["server"]),
        "database_present": bool(cfg["database"]),
        "username_present": bool(cfg["username"]),
        "driver": cfg["driver"],
        "authentication_mode": AUTH_MODE,
        "connection_timeout": _connection_timeout(),
    }


def build_odbc_connect_string() -> str:
    """
    DRIVER={DRIVER};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};
    Authentication=ActiveDirectoryInteractive;Encrypt=yes;
    TrustServerCertificate=yes;Connection Timeout=<seconds>;
    """
    if not azure_configured():
        raise AzureConnectionError(
            f"Azure SQL settings missing. Set SERVER, DATABASE, and USERNAME in {ENV_FILE} "
            "or the process environment."
        )
    cfg = _azure_settings()
    return (
        f"DRIVER={{{cfg['driver']}}};"
        f"SERVER={cfg['server']};"
        f"DATABASE={cfg['database']};"
        f"UID={cfg['username']};"
        f"Authentication={AUTH_MODE};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        f"Connection Timeout={_connection_timeout()};"
    )


def get_engine() -> Engine:
    url = "mssql+pyodbc:///?odbc_connect=" + quote_plus(build_odbc_connect_string())
    return create_engine(url, future=True)


def connect_azure() -> Engine:
    """
    Create the engine and force interactive login with SELECT 1.

    Raises AzureConnectionError on any failure. Never returns a partial engine.
    """
    diag = connection_diagnostics()
    for key, value in diag.items():
        logger.info("Azure connection diagnostic — %s: %s", key, value)

    if not azure_configured():
        raise AzureConnectionError(
            "SERVER, DATABASE, and USERNAME are required "
            f"(env_file_exists={diag['env_file_exists']}). See README — Azure connection prerequisites."
        )

    try:
        import pyodbc
    except ImportError as exc:
        raise AzureConnectionError(
            "pyodbc could not be loaded. On macOS this usually means unixODBC is not installed "
            f"(brew install unixodbc). Underlying error: {exc}"
        ) from exc

    installed = pyodbc.drivers()
    if diag["driver"] not in installed:
        raise AzureConnectionError(
            f"ODBC driver '{diag['driver']}' is not installed. Installed drivers: {installed or 'none'}. "
            "Install the Microsoft ODBC Driver for SQL Server (see README)."
        )

    logger.info("CONNECTING TO AZURE — complete browser sign-in within %s seconds", diag["connection_timeout"])
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 AS connection_test"))
    except Exception as exc:
        logger.error("Azure connection failed — driver=%s error_type=%s", diag["driver"], type(exc).__name__)
        raise AzureConnectionError(f"Azure connection failed: {exc}") from exc

    logger.info("Azure connection successful")
    return engine
