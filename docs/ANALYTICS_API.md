# Authenticated analytics API — analytics-schema-1

The four read-only routes are enabled with STEP 13 persistence:

| GET route | Aggregate output |
|---|---|
| `/api/v1/analytics/summary` | Total, task distributions, coverage/missingness, review/correction KPIs, cross-tab and model references |
| `/api/v1/analytics/topics` | Topic and approved synthetic agency/domain distributions |
| `/api/v1/analytics/trends` | Calendar buckets, event-time counts and within-bucket shares |
| `/api/v1/analytics/alerts` | Three descriptive rule statuses with current/baseline window references |

All require a verified server-configured ADMIN, REVIEWER or ANALYST principal with
source grants. Text permission is not needed because no text is selected or returned.
The legacy STEP 12 API key alone grants no analytics role. Roles are never accepted
from a body/header claim. Every role, including ADMIN, remains subordinate to STEP 02
source authorization. Real analytics is blocked; only the declared synthetic source
and synthetic DB rows are accepted. Source snapshots and taxonomy/model mode are checked.
No endpoint loads model weights, raw citizen data or protected test labels.

## Filters

| Parameter | Meaning |
|---|---|
| `start`, `end` | Paired ISO YYYY-MM-DD inclusive local event dates, ordered, maximum 366 days; supported years 1900–2100 |
| `interval` | day (default), week or month; controls calendar trend buckets |
| `basis` | prediction (default), reviewed or adjudicated; never mixed or silently backfilled |
| `source_id` | Must be in authenticated source grants and current synthetic declaration |
| `agency`, `domain` | Public synthetic codes in analytics_v1.yaml allowlists; unsupported values fail |
| `topic`, `sentiment`, `severity` | Exact taxonomy label IDs; severity also accepts unknown. Filters apply to selected basis |
| `review_status` | One STEP 13 finite-state review status |
| `model_family`, `model_version` | Match the latest prediction of model_task; other task models may differ |
| `model_task` | topic (default), sentiment or severity; makes model-filter interpretation explicit |

Model families are mock/lr/svm/phobert, but a family filter does not create an existing
run. Missing families yield empty cohorts. Version must exist within authorized source
scope; malformed/unsupported versions return 422. Model metadata is not a performance
comparison. Approved research/production models are unavailable. Unknown query fields,
small_group overrides and malformed dates are rejected.

Without explicit dates, summary includes undated records. Trend/alert extent is the
minimum/maximum actual event date; a range exceeding the configured ceiling requires
an explicit bounded window. With explicit dates, undated records are excluded from the
window and counted separately in the pre-date-filter scope. Week starts Monday; month
starts on day 1. Buckets are [start,end_exclusive) in Asia/Ho_Chi_Minh. Storage stays UTC.
Partial boundary buckets are marked; current/future unfinished buckets cannot alert.
Zeros mean no observed rows, not proof of complete source collection.

## Response and limits

Every response contains schema/config versions, config checksum, selected filters,
taxonomy version, timezone, `processing_mode=DEMO_ONLY`, and the exact notice
`SYNTHETIC DATA — DEMO ONLY`. Status is AVAILABLE, EMPTY or SUPPRESSED.
Metrics expose `{numerator, denominator, share, suppressed}`. Zero-denominator share
is null. Suppressed values are null, never zero. No UUIDs, feedback text, audit actors,
private file paths or source-record identifiers are returned.

Default k=5 is server-controlled. Cohorts of 1–4 suppress the entire result. Any
positive small category suppresses its entire distribution/cross-tab/time series,
including complements, so a total cannot reconstruct one hidden cell within that
partition. Binary shares suppress small numerator, complement or denominator;
coverage suppression propagates to conditional rates. This is conservative cell
suppression, not differential privacy or protection against repeated-query inference.

Default capacity is 5,000 authorized metadata rows per request; overflow returns 503
rather than a partial total. At most 366 daily buckets, fixed taxonomy partitions and
three alert rules are returned. No unbounded record list or raw-data export exists.
Queries select metadata only using SQLAlchemy and window ranking. A fresh request
session provides one read snapshot (SQLite explicit transaction; PostgreSQL repeatable
read/read-only, pending actual PostgreSQL verification). Separate endpoint requests
are separate snapshots; the dashboard is not a globally locked multi-request snapshot.

With persistence disabled, analytics routes are absent (404), preserving original
STEP 12 behavior. Enabled but unavailable DB returns 503. Other safe statuses:
401 credential missing/wrong, 403 role/source/mode denial, 422 invalid filters,
503 capacity/configuration/database unavailable. Invalid input and connection details
are never reflected. Logs use existing fixed privacy-safe route/status metadata.

Example invented-data query after explicit demo setup:

```powershell
$headers = @{ 'X-API-Key' = $env:PFA_DASHBOARD_API_KEY }
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/analytics/summary?basis=prediction&start=2025-01-06&end=2025-01-13' -Headers $headers
```

The dated fixture window has 400 records; the missing-event-time metric still reports
20 out of its 420-record pre-date-filter scope. These are invented software fixtures.
