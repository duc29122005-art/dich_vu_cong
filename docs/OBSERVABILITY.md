# Privacy-safe observability

Existing `/health/live` confirms process liveness. `/health/ready` reports prediction
readiness for the configured mode; it never implies valid research results. Missing
credentials or eligible approved models fail closed. Persistence health is separate.

Set `PFA_API_OBSERVABILITY_ENABLED=true` to add `GET /api/v1/operations/status`.
It requires an authenticated server-configured ADMIN principal, not the legacy API key
alone. REVIEWER and ANALYST are denied. Default seven API paths remain unchanged.
The endpoint reports mode, model availability, prediction readiness, DB SELECT 1 health,
source-scoped synthetic queue size, request/error/failure counts and mean/max latency.
It exposes no DB URL, actor/record IDs, source documents, keys or input text.

Counters have constant memory, are thread-safe and reset on process restart. They count
HTTP requests, HTTP errors >=400 and server processing failures >=500. Per-item failures
inside successful batch responses are not independent HTTP failures. This is not a durable
event ledger, a full tracing system, or a multi-worker metrics collector. For multiple
workers, add a restricted external collector. Protect operational aggregates even locally.

Existing structured logs retain generated request trace, allowlisted static route,
HTTP status and duration. Dynamic IDs and unknown paths are logged as UNMATCHED. No body,
query string, user request ID, authentication token or exception repr is logged.

`python -m pfa.cli integration performance` measures 20 sequential samples each of
single prediction, eight-item batch prediction, feedback-count query, review queue and
analytics summary. It returns sample count, median, lower empirical p95 and items/second,
Python/OS/architecture/logical CPU count and cleanup status. Database has 420 invented
records. Transport is TestClient, not a network benchmark; no production latency or
throughput guarantee follows. Heavy concurrent load is excluded from normal tests.
