# Georgia Access — OE Historical Trend Pipeline

Retrieves historical Open Enrollment data from Azure SQL, applies metric-specific rules, validates against control totals, and generates an interactive offline HTML dashboard: `output/oe_trend_dashboard.html`.

Metrics: Enrollment (person grain), Cancellation and Termination (policy grain), and EDE (validation pending). Plan Years: PY2025 and PY2026, with PY2027 marked Source Pending.

See `docs/` for discovery findings, metric definitions, lineage, and validation notes.

## 1. Environment setup

Requires Python 3.10+.

```bash
cd ~/Desktop/oe_trend_pipeline
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Dependency installation

```bash
pip install -r requirements.txt
```

## 3. Azure connection prerequisites

The connection follows the reference implementation `834_issuer_etl/azure_reconciliation/azure_client.py`: SQLAlchemy + pyodbc with `Authentication=ActiveDirectoryInteractive` (browser sign-in, no password).

1. **unixODBC and the Microsoft ODBC Driver for SQL Server (macOS):**
   ```bash
   brew install unixodbc
   brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
   HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql17   # or msodbcsql18, then set DRIVER accordingly
   ```
   Confirm: `.venv/bin/python -c "import pyodbc; print(pyodbc.drivers())"`
2. **Connection settings:** `cp .env.example .env` and set `SERVER`, `DATABASE`, `USERNAME` (your Entra ID UPN), and `DRIVER`. Use the same values as the working reference pipeline. `.env` is git-ignored. Process environment variables work too.
3. **Sign-in:** the first query opens a browser for Entra ID sign-in. Complete it within `CONNECTION_TIMEOUT` seconds (default 300).

Test only the connection:

```bash
python run_pipeline.py --check-connection
```

## 4. Running the pipeline

```bash
python run_pipeline.py                            # full run
python run_pipeline.py --skip-extended-validation # skip L1 recount / L2 issuer / L3 status queries
python run_pipeline.py --ede-discovery            # also run EDE discovery diagnostics (not a metric)
```

| Exit code | Meaning |
|---|---|
| 0 | Success, no unexplained differences |
| 1 | Fatal (connection, SQL, query, processing). No dashboard written, no data substituted |
| 3 | Dashboard written, but at least one UNEXPLAINED DIFFERENCE (shown in the dashboard) |

Logs: `logs/oe_trend_pipeline_<run_id>.log`. Outputs: `data/raw/`, `data/processed/`, `data/validation/` — aggregated counts only.

## 5. Generating the dashboard

A full run writes `output/oe_trend_dashboard.html`. To re-render the HTML from a previous live run without querying Azure:

```bash
python run_pipeline.py --from-run 20261103_093000
```

The dashboard header and banner state that the data was rebuilt and show the original extraction time.

## 6. Opening the HTML report

```bash
open output/oe_trend_dashboard.html
```

The file is self-contained (plotly.js is embedded), so it needs no web server or internet connection.

## 7. Adding another Plan Year (e.g. PY2027)

1. Get the validated backend source and its as-of/grain logic from the data owner.
2. Add the year to each metric SQL file (`coverage_year IN (...)` and the confirmation window in `enrollment_trend.sql`), and to `validation.sql`.
3. In `config/settings.py`, set `PLAN_YEARS[2027]["status"] = PY_AVAILABLE` and the label to `"PY2027"`. Add control totals to `CONTROL_TOTALS` once they're validated.
4. Run the pipeline. PY2027 is enabled in the UI automatically when data is returned.

Never fill a Plan Year by copying or extrapolating another year.

## 8. Adding another metric

1. Write `sql/<metric>_trend.sql` returning exactly `Plan_Year, Metric_Date, Metric, Daily_Count, Cumulative_Count`. De-duplicate to the metric grain before counting, return aggregates only, and use SELECT only.
2. Add an entry to `METRICS` in `config/settings.py` (grain, identifier, source, date field, filters, method, limitations, `status="ACTIVE"`), and add it to `METRIC_ORDER`.
3. Add control totals to `CONTROL_TOTALS` if they exist, and recount queries to `validation.sql`. Wire those into `extended_validation()` in `run_pipeline.py`.
4. The dashboard button, chart, definitions, and table are generated from the registry.

To activate EDE: once the `partner_permissions` relationship is validated, write `sql/ede_trend.sql`, set `METRICS["EDE"]` grain/identifier/date/`sql_file`, and change its status to `ACTIVE`.

## Official OE dates / OE_Day

Populate `OFFICIAL_OE_START_DATES` in `config/settings.py` once business confirms the dates. `OE_Day` is then computed for every row, which enables aligned cross-year comparison.

## Tests (offline, synthetic fixtures)

```bash
python -m unittest discover -s tests -v
```
