# STEP 13 database contract

The target is PostgreSQL with SQLAlchemy 2.x and psycopg 3. SQLite is restricted to
internal disposable synthetic tests. PostgreSQL integration is not established by
SQLite tests. Credentials come only from protected process environment settings.

The initial schema deliberately permits only synthetic feedback and DEMO_ONLY
predictions. There is no switch that enables real intake. A future reviewed adapter
must validate current STEP 02 scopes, STEP 03B receipts, STEP 04 membership and human
privacy clearance before a separate reviewed migration can permit real persistence.
ADMIN does not override these gates. No database field constitutes research approval.

| Table | Purpose and integrity |
|---|---|
| `source_registry` | Immutable reference and checksum of existing source declaration; no permission authority |
| `model_version` | Immutable task/model reference, taxonomy, preprocessing and descriptor hash; no model approval authority |
| `feedback` | UUID, source, fixture reference, screened text, optional event time/metadata, review state, current human labels, version |
| `prediction` | Immutable original task output, model FK, score semantics, review reasons, mode and provenance |
| `review_event` | Immutable UUID/operation UUID, actor/role, action/reason, labels, version, time and adjudication metadata |

Source-record references are unique per source. Composite foreign keys prevent a
prediction referencing a model of another task/mode or an audit event referencing
another feedback's prediction. Checks constrain labels, states, synthetic flags,
positive versions and null uncalibrated demo scores. Source, state, assignment,
creation time and foreign-key indexes support bounded queue queries. Successful
events have unique `(feedback_id, review_version)`; rejected conflicts have a null
review version and an attempted version. Operation UUIDs are globally unique.

Application timestamps are UTC-aware. Naive writes are rejected by the ORM type.
PostgreSQL uses `timestamp with time zone`; SQLite test results are normalized to UTC.
`received_at` is an actual feedback event timestamp and remains null when unavailable.
Creation time is never substituted for missing event time. Initial fixtures have no
agency/channel/event-time claims.

Feedback provenance/text cannot change after creation. Corrections occupy separate
current-label fields and append events; original model predictions remain unchanged.
Database triggers and ORM guards prevent history UPDATE/DELETE. They do not protect
against a privileged database owner disabling triggers or rewriting backups.

Database startup performs schema/revision/guard checks only. Sessions are injected
per request and closed afterward. Lifespan disposes the engine on shutdown. The
default pool has two connections, zero overflow and a five-second acquisition timeout.
SQL echo is disabled and bound parameters are hidden. Never enable SQL/body debug logs
for sensitive workloads. See [migrations](DATABASE_MIGRATIONS.md),
[review workflow](HUMAN_REVIEW_WORKFLOW.md) and [retention](DATA_RETENTION.md).
