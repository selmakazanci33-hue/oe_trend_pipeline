# Discovery Findings — OE Historical Trend Pipeline

## 1. Reference Azure connection implementation (read-only)

| Item | Reference |
|---|---|
| Project | `~/Downloads/gaaccess-develop16/834_issuer_etl` |
| Connection module | `azure_reconciliation/azure_client.py` |
| Connection test | `test_azure_connection.py` |
| Config / env loading | `config/config.py` (`ENV_FILE = PROJECT_ROOT / ".env"`, `load_dotenv(override=True)`) |
| Env template | `.env.example` (Azure section) |
| Dependencies | `requirements.txt` (`sqlalchemy>=2.0`, `pyodbc>=5.0`, `python-dotenv`) |

Pattern reused in `src/azure_connection.py`:

- **Authentication:** `Authentication=ActiveDirectoryInteractive` — passwordless Entra ID browser sign-in. No `PWD`, no `Trusted_Connection`.
- **Connection string:** `DRIVER={...};SERVER=...;DATABASE=...;UID=...;Authentication=ActiveDirectoryInteractive;Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=<s>;`
- **SQLAlchemy:** `create_engine("mssql+pyodbc:///?odbc_connect=" + quote_plus(odbc_str), future=True)`
- **Env vars:** `SERVER`, `DATABASE`, `USERNAME`, `DRIVER` (default `ODBC Driver 17 for SQL Server`), `CONNECTION_TIMEOUT` (default 300 s, min 30), with `AZURE_SQL_*` aliases.
- **Lifecycle:** engine created per run; login forced with `SELECT 1 AS connection_test`; queries run in `with engine.connect()` blocks via `pd.read_sql(text(sql), conn)`; engine disposed at the end.
- **Read-only:** SELECT only.

Nothing in the reference project was modified, moved, or imported. The new pipeline has its own `.env` at `oe_trend_pipeline/.env`.

### Missing runtime dependencies on this workstation (found 2026-11-03)

The connection *pattern* is fully specified by the reference code. The following *runtime prerequisites* are not present on this machine, so no live query was executed:

1. **No `.env` with connection values.** The reference project has only `.env.example`; `SERVER`/`DATABASE`/`USERNAME` are not set in the environment either. Values must come from the data owner / the machine where the reference pipeline runs.
2. **No Microsoft ODBC Driver for SQL Server** (`msodbcsql17`/`msodbcsql18`) installed.
3. **No unixODBC** (`libodbc.2.dylib`), so `pyodbc` cannot load.
4. **Interactive browser sign-in** is required by `ActiveDirectoryInteractive`; it cannot be completed by an unattended process.

Not invented: no alternate auth mode (SQL auth, service principal, token), no guessed server names.

## 2. Historical snapshot architecture

- Dated historical snapshots exist, e.g. `dbo.Enrollments_PY2526_NOV30`, `dbo.Enrollments_PY2526_DEC31`, plus others referenced in the reference project (`Enrollments_PY2526_01312026`, `_02272026`, `_03312026`, `_04302026`, `_FEB10`, `Enrollments_PY2026`).
- **Do not reconstruct historical populations from the latest snapshot.** Records later cancel, terminate, change lifecycle state, or drop out of later snapshots.
- Use the snapshot that corresponds to the historical reporting period whenever an as-of population is required. Enrollment uses NOV30; Cancellation/Termination use DEC31.

## 3. Plan Year availability

| Plan Year | Status |
|---|---|
| PY2025 | Available in NOV30 / DEC31 snapshots |
| PY2026 | Available in NOV30 / DEC31 snapshots |
| PY2027 | **Source Pending** — backend source of the PY2027 OE Executive Dashboard not identified |

Data-owner question for PY2027:

> For the PY2027 OE Executive Dashboard, what backend table/query is used for the "Currently Enrolled People" metric, and what grain and as-of-date logic is used for that count?

## 4. Grain

- **Enrollment:** person grain (`enrollee_id`).
- **Cancellation / Termination:** policy/enrollment grain (`enrollment_id`).
- People and policies are never summed together or plotted on the same chart.

## 5. Confirmation-date findings

- `Enrolled` during OE does not necessarily mean coverage is effective; future `benefit_effective_date` values were observed for enrolled people.
- Enrollment activity uses `enrollment_confirmation_date`, first confirmation per person. `benefit_effective_date` is not used as the activity date.
- Enrollment trend ≠ active coverage trend.
- The date windows (PY2025 ≥ 2024-10-01, PY2026 ≥ 2025-10-01) are POC discovery windows, not official OE start dates.

## 6. Cancellation / Termination date proxy

- `enrollment_last_update_date` is the current POC activity-date candidate.
- It is a **proxy**, not a confirmed cancellation/termination event timestamp.
- Large PY2025 vs PY2026 differences may reflect lifecycle rules, historical processing, snapshot behavior, metric semantics, or event-date semantics. No causal interpretation is made.

## 7. EDE

- POC discovery with `source = 'EDE'` found substantial populations (e.g. PY2026 OE/Health: 295,242 raw rows, 235,772 distinct enrollments, 168,697 distinct people; OE/Dental: 7,480 / 5,687 / 6,912).
- `source = 'EDE'` is **not** the Executive Dashboard EDE definition. Executive Dashboard documentation indicates EDE is identified via relationships to `partner_permissions`, counted without filtering by status or insurance type.
- The `partner_permissions` join is not present anywhere in the reference project and has not been identified. EDE is **Validation Pending**.
- The snapshot column that splits Dental vs Health was not confirmed for the `Enrollments_PY2526_*` tables (an `insurance_type` column exists only in a different table, `dbo.inbound_automation`), so `ede_discovery.sql` does not assume it.

## 8. Duplicate / raw-row warning

These datasets contain duplicate/repeated rows. `COUNT(*)` over source rows is never a business KPI. Every metric de-duplicates to its grain first (one row per person or per policy), and only then counts.

## 9. Early-OE confirmation volume

Large same-day confirmation volumes at the start of the period can be normal (continuing and new enrollments processed at open). They are not flagged, removed, smoothed, capped, or labeled as new consumers.
