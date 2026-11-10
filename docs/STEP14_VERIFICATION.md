# STEP 14 implementation and verification

Implemented STEP 14 only. All statistics below describe invented software fixtures.
No authorized citizen dataset, approved research model or scientific result exists.
STEP 15 has not started.

## Files created and modified

Created:

- `src/pfa/analytics/{__init__,schemas,repository,kpis,trends,alerts,service,routes,fixtures,smoke}.py`.
- `dashboard/{__init__,api_client,charts,app}.py` and `.streamlit/config.toml`.
- `tests/test_analytics.py`, `tests/test_dashboard.py`, `tests/test_analytics_postgres.py`.
- `configs/analytics_v1.yaml`.
- `docs/KPI_DICTIONARY.md`, `ANALYTICS_API.md`, `ALERT_ENGINE.md`,
  `DASHBOARD_GUIDE.md`, `ANALYTICS_LIMITATIONS.md`, and this report.

Modified:

- `src/pfa/api/app_factory.py`: persistence-dependent analytics route integration.
- `src/pfa/cli.py`: `analytics smoke` and explicit `analytics seed-demo`.
- `pyproject.toml`: optional Streamlit/Plotly dependencies.
- `.gitignore`, `.env.example`: protected dashboard configuration conventions.
- `README.md`, `docs/ARCHITECTURE.md`, `docs/RBAC_MATRIX.md`, `docs/API_CONTRACT.md`.

## Architecture and endpoints

SQLAlchemy metadata-only queries reuse STEP 13 sessions, source permission checks
and authenticated principals. A bounded request snapshot supplies typed KPI,
trend and alert services. FastAPI returns aggregate Pydantic reports. The separate
Streamlit application accesses authenticated APIs only; it never opens the DB.

Four GET endpoints are implemented:

- `/api/v1/analytics/summary`
- `/api/v1/analytics/topics`
- `/api/v1/analytics/trends`
- `/api/v1/analytics/alerts`

Disabled persistence leaves routes absent, preserving STEP 12 defaults. Enabled but
unavailable persistence returns 503. Requests exceeding 5,000 metadata records return
503 without partial totals. API responses expose no feedback IDs, text, source-record
references, actors, credentials or connection paths.

## KPIs, filters and event time

[KPI_DICTIONARY.md](KPI_DICTIONARY.md) defines numerators, denominators, sources,
missingness, units and limitations for totals; topic/sentiment/severity distributions;
negative/high-severity shares; top complaint topic; review flags, queue and completion;
corrections; label coverage/missingness; and event-time trends.

One feedback is one statistical unit. Latest predictions do not multiply counts.
`prediction`, `reviewed` and `adjudicated` bases are explicit and never backfill each
other. Corrections use predictions available at the successful review event, so later
inference does not rewrite correction history. Unknown severity is separate from
supervised labels. Zero denominators produce null shares.

Filters cover dates, agency/domain, source, topic/sentiment/severity, model family and
version, selected model task and review state. Server-side allowlists and source grants
apply. [ANALYTICS_API.md](ANALYTICS_API.md) specifies each filter and safe error code.

Only actual `received_at` supplies event time. UTC storage is interpreted in
Asia/Ho_Chi_Minh. Daily, Monday-weekly and calendar-month buckets have exclusive end
boundaries. Paired date filters are inclusive local dates, at most 366 days. Missing
dates are counted before date filtering within other filters; ingestion timestamps
are never substituted. Partial/current/future buckets cannot generate alerts.

## Alerts

Three descriptive rules compare a complete daily window against seven preceding
daily windows: volume increase, high-severity share increase and topic concentration.
Minimum baseline/current counts are 10/20, also subject to cell suppression.
Volume requires both a twofold increase and a three-deviation noise guard. Share
increases require configured absolute changes and a sampling-noise guard.

Missing dates above 10%, missing/unknown task labels above 10% in any relevant
window, insufficient support, incomplete windows and small cells suppress unsupported
claims. Status, fixed reason and explicit baseline/current boundaries are returned.
These rules have no validated real false-positive rate, exposure denominator or
seasonal adjustment. They trigger no notification or administrative action.
See [ALERT_ENGINE.md](ALERT_ENGINE.md).

## Dashboard and security

Five Vietnamese pages cover overview, topics, sentiment/severity, trends/alerts and
model/human review. Every page displays `SYNTHETIC DATA — DEMO ONLY`.
Plotly receives whitelisted aggregate labels/counts, without hidden record payloads.
AppTest exercises all pages using authenticated in-process APIs.

ADMIN, REVIEWER and ANALYST use server-configured source grants. Legacy prediction
credentials confer no analytics role. ADMIN cannot override real-source restrictions.
Only synthetic source snapshots and synthetic rows are accepted, in explicit local
DEMO_ONLY mode. Dashboard credentials remain in server environment configuration.
Loopback origins, bounded requests, no redirects/proxy inheritance and safe errors
limit the local client. No public server or permissive CORS was started.

Default k=5 suppresses small cohorts, category partitions, cross-tabs and time series;
binary metrics also protect small complements and propagate denominator suppression.
This is not differential privacy. Repeated-query differencing remains a documented
deployment limitation. Real analytics is blocked, regardless of role.

## Synthetic smoke evidence

`ANALYTICS_SMOKE_PASS_SYNTHETIC` verifies:

- 420 invented feedback, 1,260 mock predictions and 1,050 simulated review events.
- 400 dated feedback and 20 missing event dates.
- Negative count 250/420; high-severity count 147/420.
- Reviewed count 210/420; corrected count 85/210 comparable reviewed records.
- Seven daily counts of 40 followed by 120; all three intended demo rules trigger.
- Filters, weekly grouping, missing dates, demo labeling, authorization and source denial.
- No raw text in aggregate payloads/logs, no real dataset or protected holdout access.
- Disposable migrated SQLite storage removed after completion.

Synthetic reviewers/adjudications establish no independent human validation or gold data.

## Commands and verification

Commands run through the local Python 3.11 virtual environment. RTK prefixes are
omitted below for readability. All listed exit codes are child-process codes.

| Command | Exit | Result |
|---|---:|---|
| `python -m pytest -q` before implementation | 0 | 663 passed, 1 skipped |
| `python -m pytest -q` after implementation | 0 | 736 passed, 2 skipped in 162.99 seconds |
| `python -m ruff check .` before implementation | 0 | PASS |
| `python -m ruff format --check .` before implementation | 0 | PASS |
| `python -m pytest tests/test_analytics.py tests/test_dashboard.py -q` | 0 | 73 passed |
| `python -m pfa.cli analytics smoke` | 0 | ANALYTICS_SMOKE_PASS_SYNTHETIC |
| `python -m pfa.cli api smoke` | 0 | API_SMOKE_PASS_SYNTHETIC |
| `python -m pfa.cli db smoke` | 0 | DB_SMOKE_PASS_SYNTHETIC |
| `python -m pfa.cli doctor` | 0 | PASS |
| `python -m ruff check .` after implementation | 0 | PASS |
| `python -m ruff format --check .` after implementation | 0 | PASS |
| `python -m pytest tests/test_postgres.py tests/test_analytics_postgres.py -q` | 0 | 2 skipped: dedicated TEST_DATABASE_URL unavailable |
| `python -m pfa.cli analytics seed-demo` with APPROVED_MODEL mode | 3 | Explicit local DEMO_ONLY mode required |

The final full suite preserves all 663 previously passing tests and adds 73 passing
analytics/dashboard tests. Both skips require a dedicated PostgreSQL test database.

## PostgreSQL, remaining blockers and next-step boundary

PostgreSQL integration is **NOT_VERIFIED**. Optional tests require a dedicated local
`TEST_DATABASE_URL` ending in `_test`; they create and remove only their unique owned
schema. No existing production database was connected to or reset. SQLite and AppTest
success do not establish PostgreSQL or a live deployment.

Installed dashboard versions verified: Streamlit 1.66.1 and Plotly 6.9.0. Local launch:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Follow [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) for protected credentials, explicit empty
synthetic DB migration/seeding, API launch and filters. Those operator commands were
documented, not executed against a live PostgreSQL database.

Real analytics still requires source permission, authorized acquisition/privacy review,
approved taxonomy, real pilot annotation, frozen gold data and approved model evidence.
Public deployment also needs identity/session isolation, TLS, rate limits,
anti-differencing controls, retention/backup review and human authorization.
STEP 15 may begin protocol preparation only; it has not been implemented here.

TECHNICAL_IMPLEMENTATION: PASS

ANALYTICS_SMOKE: SYNTHETIC_VERIFIED

DASHBOARD: DEMO_READY

POSTGRES_INTEGRATION: NOT_VERIFIED

PRIVACY_RBAC: PASS

REAL_ANALYTICS: BLOCKED

STEP15_READINESS: READY_FOR_PROTOCOL
