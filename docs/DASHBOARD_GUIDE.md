# Local Vietnamese analytics dashboard

Every page displays **SYNTHETIC DATA — DEMO ONLY**. The dashboard reads only authenticated
aggregate APIs; it never opens a database, feedback file or model checkpoint. Real data
and real model deployment remain blocked. No public server is launched during tests.

## Offline checks

From the repository root on Windows, using Python 3.11:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api,dashboard]'
.\.venv\Scripts\python.exe -m pfa.cli analytics smoke
.\.venv\Scripts\python.exe -m pytest tests/test_analytics.py tests/test_dashboard.py -q
```

Smoke creates a disposable restricted SQLite DB, runs the actual initial migration,
inserts 420 invented feedback, 1,260 mock task predictions and 1,050 simulated review
events, then calls authenticated APIs and cleans up. Of those records, 400 have invented
event dates on 2025-01-06 through 2025-01-13 and 20 have null event dates. Synthetic
actors and decisions do not establish independent human annotation or research gold.
SQLite does not verify PostgreSQL. Streamlit AppTest exercises all five pages through
authenticated in-process TestClient transport without starting a server.

## Explicit local persistent demo

For the STEP 17 temporary demo with no PostgreSQL requirement, use
[DEMO_QUICKSTART.md](DEMO_QUICKSTART.md). It seeds a new isolated store for the API
process lifetime and cleans it after normal shutdown. The optional persistent PostgreSQL
procedure below remains a separate explicit operator workflow; its historical verification
and current-run coverage are distinct.

Provision a separate local PostgreSQL development database under the STEP 13
[migration and backup policy](DATABASE_MIGRATIONS.md). PostgreSQL integration is currently
NOT_VERIFIED. No tool connects to a user DB, migrates, resets or starts Docker automatically.
Provide protected environment settings:

- `PFA_DB_MODE=SYNTHETIC`, `PFA_DB_URL` containing the protected psycopg URL.
- `PFA_API_MODE=DEMO_ONLY`; environment development, never production.
- `PFA_API_PRINCIPALS`: server-side credential JSON with source-scoped pseudonymous
  roles. Use an ANALYST principal for the dashboard, normally can_view_text=false.
- `PFA_DASHBOARD_API_URL=http://127.0.0.1:8000`.
- `PFA_DASHBOARD_API_KEY`: that ANALYST principal's generated secret, injected only on
  the Streamlit server. A legacy inference key alone cannot read analytics.

There are no reusable secret values in this guide. Generate high-entropy credentials
and use protected environment configuration; never paste them into code, charts,
browser widgets or shell history. Follow [RBAC](RBAC_MATRIX.md) for credential shape.
Both API/database and dashboard settings read process environment, not a committed file.

Explicit operator actions, only for the new empty synthetic development DB:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pfa.cli analytics seed-demo
.\.venv\Scripts\python.exe -m pfa.cli api serve --host 127.0.0.1 --port 8000
# In another protected shell with the dashboard ANALYST credential:
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Seeding refuses any nonempty application table, never overwrites data and never changes
source permissions. It accepts no input file or arbitrary text and registers no research
dataset. Fixture dates, model labels and review events are explicitly invented. Normal
API startup never seeds or migrates. Do not point these commands at an existing private
dataset. PostgreSQL setup requires actual local verification; offline AppTest does not
establish a live PostgreSQL deployment.

## Pages and filters

- **Tổng quan**: total, negative/high-severity shares, AI review requirement and top
  complaint topic. Percentages are descriptive aggregate shares, not model reliability.
- **Phân tích chủ đề**: topic and approved synthetic agency/domain counts.
- **Cảm xúc và mức độ**: separate distributions and supported cross-tabulation.
- **Xu hướng và cảnh báo**: local day/week/month buckets, missing-date explanation,
  daily alert status/reason and explicit baseline/current windows.
- **Mô hình và rà soát**: model references/status, queue states, review and correction
  shares. No invented accuracy, calibration or performance comparison is displayed.

Choose AI, reviewed or adjudicated label basis explicitly. Date filters are optional;
for the seeded time series choose 2025-01-06 to 2025-01-13. The initial no-date-filter
view includes undated records and derives trend extent only from actual fixture event
dates. Agency/domain controls expose the public default synthetic codes; a modified
allowlist requires corresponding UI-label configuration/review. Model filters apply to
the selected task. Unknown version/filter choices fail safely. The dashboard does not
silently merge labels. Empty/suppressed results and null percentages are explicit.

## Security

The API enforces auth, RBAC, source scopes and suppression server-side. Streamlit is
not an authorization boundary. Dashboard origin configuration permits only loopback
HTTP(S), rejects userinfo/query/path injection, disables redirects/proxy inheritance and
uses bounded response validation and timeouts. No browser input supplies an API key,
arbitrary model path or upstream URL. There is no shared data cache across users.
The local `.streamlit/config.toml` binds loopback, enables CORS/XSRF protection and
disables usage telemetry; secrets.toml is ignored by Git, but this implementation uses
environment credentials. API wildcard CORS remains disabled.

Plotly data contains whitelisted public category labels, dates and aggregate counts,
with no feedback IDs, raw text or hidden custom-data records. Suppressed cells never
become zeros. Error messages do not echo API bodies, credentials or connection URLs.
Do not expose this dashboard through a tunnel or reverse proxy. Public/multi-user
deployment needs reviewed identity/session isolation, TLS, rate limits, anti-differencing
controls, host/database/backup security and human deployment authorization.
