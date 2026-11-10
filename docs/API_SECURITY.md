# Local API security boundary

Prediction is fail-closed by default: APPROVED_MODEL mode, no credentials, no active
approved models. DEMO_ONLY must be explicitly configured and is forbidden when
`PFA_ENVIRONMENT=production`. It does not grant dataset access or permit promotion.
Do not submit real citizen feedback to the demo. All examples and smoke inputs are invented.

## Authentication and exposure

All `/api/v1/` routes require `X-API-Key`. The key comes from protected `PFA_API_KEY`
environment configuration, must contain 32–256 printable ASCII characters, and is
compared with constant-time HMAC comparison. Generate high-entropy credentials;
length alone does not establish entropy. There are no embedded secrets, public
promotion routes, authentication-disable switches or arbitrary model paths in requests.
Invalid/missing credentials return 401; absent server credentials return 503.
Rotate the environment credential and restart to revoke it. This is a single local
operator credential. STEP 13 adds separate protected `PFA_API_PRINCIPALS` for
source-scoped RBAC; the legacy key grants no persistence role. See [role matrix](RBAC_MATRIX.md).

CLI binding is limited to loopback and uses one worker. Demo middleware additionally
rejects non-loopback peers and non-local Host headers, and ignores forwarded identity
headers. It reduces accidental exposure and DNS rebinding; a local reverse proxy can
still expose a loopback server if misconfigured. Never publish this demo through a
tunnel, forwarding proxy or public port. Public health endpoints disclose only liveness,
mode and generic readiness blockers. Documentation/OpenAPI are disabled in production.
Development Swagger UI may fetch its browser assets from a CDN; smoke and OpenAPI
schema generation require no network or browser.

CORS defaults to disabled and accepts only configured exact HTTP(S) origins without
wildcards, paths or embedded credentials. Allowed preflight requests need no API key;
actual requests always require one. CORS controls browser access, not authentication.

## Validation, admission and errors

An ASGI boundary authenticates API requests before body reading and bounds declared
and actual streamed bytes. It rejects ambiguous duplicate security headers, conflicting
body framing, compressed input, unsupported content types, invalid UTF-8, duplicate JSON
keys, NaN/Infinity constants and malformed/deep JSON. Body receive time is bounded.
Pydantic rejects unknown fields, whitespace-only content, lone surrogates, replacement
characters, noncharacters, dangerous control/format characters and unsafe request IDs.
Vietnamese accents and combining marks remain valid. Input errors never echo text,
unknown field names, header values or exception messages.

Text/batch limits and a process-local nonblocking prediction semaphore bound resource
use. Busy requests return 503 with Retry-After. There is no global/distributed rate
limiter, user quota or hard inference preemption. Model work runs in FastAPI's worker
thread pool; once started it must finish before its slot releases. Do not implement
an async timeout that releases a slot while a model thread still runs. For public or
multi-user use, first add reviewed reverse-proxy body/header/time limits, TLS, rate
limits, per-user authorization, worker isolation and supervised inference deadlines.
These are production prerequisites, not features claimed by this step.

## Privacy and governance

Structured application logs contain only a generated trace ID, fixed route identifier,
status, duration and event name. Submitted request IDs, raw paths/query strings,
feedback, API keys, model exception text and approval evidence are never logged.
CLI serving disables Uvicorn access logging and forwarded-header trust. Other deployment
entry points, reverse proxies, telemetry agents and HTTP client debug logs must receive
their own privacy review. No body/debug logging middleware should be added.

Existing privacy screening runs transiently before inference. Structured identifier
candidates are redacted; ambiguous free-text personal names/addresses, case identifiers
and sensitive-context candidates stop inference and require review. Screening is
heuristic, not proof of anonymity. Language and service scope are not validated;
responses explicitly require review for that limitation. No input is written to disk,
reports, model artifacts, a database or a queue. Memory/transport handling does not
claim encryption at rest, cryptographic erasure or guaranteed removal from memory dumps.
Disable unnecessary crash dumps and assess retention before real use.

Registry integration reuses current source/approval checks, checksums, trusted artifact
loading and safe paths. It never promotes or downloads models, opens the final holdout,
or falls back to mock after real-model failure. Checksums are integrity controls, not
signatures against a privileged coordinator. API key possession does not grant source
rights or authorize real deployment. Required human dataset/model/privacy and production
approvals remain separate and unavailable today. STEP 13 adds opt-in synthetic
PostgreSQL/review/RBAC infrastructure; real persistence remains blocked. See
[audit boundaries](REVIEW_AUDIT.md) and [retention controls](DATA_RETENTION.md).
