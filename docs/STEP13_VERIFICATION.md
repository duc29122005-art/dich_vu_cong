# STEP 13 implementation and verification

Verified locally on 2026-11-05 with Python 3.11. Only STEP 13 was implemented. No real
data, pretrained checkpoint, public server or Docker service was accessed or started.

## 1. Files

Created:

- `src/pfa/db/{__init__,models,session,contracts,repository,routes,smoke,commands,postgres}.py`
- `src/pfa/api/identity.py`
- `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`,
  `migrations/versions/0013_initial.py`
- `compose.postgres.yaml`
- `tests/test_db.py`, `tests/test_postgres.py`
- `docs/DATABASE_SCHEMA.md`, `docs/DATABASE_MIGRATIONS.md`,
  `docs/HUMAN_REVIEW_WORKFLOW.md`, `docs/RBAC_MATRIX.md`, `docs/REVIEW_AUDIT.md`,
  `docs/DATA_RETENTION.md`, this report

Modified:

- `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`, `src/pfa/cli.py`
- `src/pfa/api/{app_factory,settings,security,service}.py`
- `docs/architecture.md`, `docs/API_SERVICE.md`, `docs/API_SECURITY.md`,
  `docs/API_CONTRACT.md`

The repository was already untracked at inspection. No commit was created and no
existing project files were removed. Git-ignore verification covers private data,
SQLite databases, backups and local credential files.

## 2. Database schema and lifecycle

SQLAlchemy 2.x models provide `feedback`, `prediction`, `review_event`, `model_version`
and `source_registry`. Named checks, indexes, unique keys and composite foreign keys
protect task/model and prediction/feedback membership. Event time is nullable and is
never replaced by ingestion time. ORM timestamps normalize to UTC and reject naive
writes. Current human labels remain separate from historical predictions.

One lifespan engine uses bounded pooling; FastAPI dependencies own per-request
sessions. Startup validates schema and history guards but performs no DDL. Default
persistence is DISABLED. The initial schema intentionally permits synthetic/demo
records only. Source/model snapshots reference existing governance and cannot grant
permissions or research approval. See [schema](DATABASE_SCHEMA.md).

Tested dependencies: SQLAlchemy 2.1.8, Alembic 1.20.1, psycopg 3.3.8, FastAPI
0.162.0 and Pydantic 2.14.2. Dependency constraints stay in the optional API extra.

## 3. Migrations

Explicit revision `0013_initial` upgrades an empty database. SQLite migration upgrade,
repeat upgrade at head and revision/schema verification passed. Alembic metadata
comparison reported `SCHEMA_DIFFS: []`. History reports one head. Downgrade refuses
destructive operations. The migration installs backend-specific immutable-history
and feedback-provenance guards. PostgreSQL execution remains NOT_VERIFIED.
See [migration/backup operations](DATABASE_MIGRATIONS.md).

## 4. Roles

Protected environment credentials bind pseudonymous actors to server-defined roles
and source/text grants. ADMIN creates fixtures, assigns authorized reviewers and reads
audit history. REVIEWER claims and reviews assigned items; adjudication requires a
separate explicit capability. ANALYST reads permitted metadata and cannot write.
Text access always needs an explicit grant. The legacy inference key grants no DB
role. Headers and bodies cannot elevate roles. No role bypasses source governance.
See [complete matrix](RBAC_MATRIX.md).

## 5. Review workflow

PENDING_REVIEW becomes IN_REVIEW through claim or assignment. An assigned reviewer
confirms/corrects to REVIEWED or escalates to NEEDS_ADJUDICATION. Only a designated
reviewer may adjudicate to ADJUDICATED. Invalid transitions, stale versions and
duplicate operation IDs are rejected. Unknown severity remains an explicit workflow
outcome with an insufficient-evidence reason. Synthetic adjudication explicitly
records that no independent human validation occurred.

## 6. API endpoints and responses

Opt-in endpoints are POST/GET `/api/v1/feedback`, GET `/api/v1/feedback/{id}`,
GET `/api/v1/reviews/queue`, PATCH `/api/v1/reviews/{id}` and
GET `/api/v1/reviews/{id}/history`. Pagination/filtering, role/source checks and
strict schemas are implemented. Enabled but unavailable persistence returns 503;
disabled persistence preserves the seven STEP 12 endpoint paths.

Creation accepts a server-owned synthetic fixture ID and operation UUID, not arbitrary
feedback text. The response preserves three mock predictions, null scores, review
reasons, DEMO_ONLY mode and provenance. Its stored provenance marks input_persisted
true; standalone prediction calls remain nonpersistent. A correction returns separate
current_labels, REVIEWED and the incremented version while original predictions stay
unchanged. Request/response examples appear in [workflow contract](HUMAN_REVIEW_WORKFLOW.md).

## 7. Audit protection

Creation, assignment/review/adjudication and relevant rejected conflicts append
transactional events with opaque references, closed reason codes and no input text.
ORM and database UPDATE/DELETE guards preserve history. There is no history mutation
endpoint. ADMIN-only history reads are source-scoped and paginated. External role
configuration changes need a separate operator change log. Privileged database owners
can bypass application/trigger protections; no administrator-proof immutability,
encryption or cryptographic tamper evidence is claimed. See [limits](REVIEW_AUDIT.md).

## 8. Concurrency and atomicity

Review writes use `UPDATE WHERE feedback_id AND version AND previous_state`, increment
the version and append audit in the same transaction. A forced simultaneous claim test
produced one HTTP 200 and one HTTP 409. A failed audit insert rolled back review state.
Stale operation tests verify conflict events and unchanged predictions. Connection
failures return safe 503; lock conflicts return 409 without SQL/credential disclosure.

## 9. Offline synthetic smoke

`DB_SMOKE_PASS_SYNTHETIC`: one feedback, three immutable demo predictions and four
events (CREATE, CLAIM, CORRECT, CONFLICT). Unauthorized request: 401; analyst write:
403; stale write: 409. Temporary protected storage was removed. Smoke checked history
deletion rejection and unchanged model predictions. Dedicated regression guards reject
any attempt by database smoke to open governed train/validation or final test data.
This verifies SQLite/application behavior only.

## 10. PostgreSQL result

POSTGRES_INTEGRATION: NOT_VERIFIED. No PostgreSQL server/tools or dedicated
TEST_DATABASE_URL are configured. The opt-in runner requires a local dedicated database
ending `_test`, creates a fresh random schema, and tests upgrade, constraints, foreign
keys, UTC column type, concurrent claims, rollback, pagination and connection reopening.
It removes only its newly created schema and never resets an existing database. The
separate PostgreSQL pytest was explicitly skipped. SQLite results do not establish
PostgreSQL behavior.

## 11. Pytest

Before implementation: **600 passed**. Final complete command: **663 passed, 1 skipped
in 154.97 seconds**, exit 0. The skipped test is the opt-in PostgreSQL integration test.
Existing STEP 01–12 tests remain passing. New tests cover schema/history, roles/auth,
source/fixture/privacy gates, transitions, concurrency/rollback, metadata/text access,
safe logging/errors, startup without DDL, holdout isolation and CLI status codes.

## 12. Ruff and executed commands

All commands ran through the required local `rtk` wrapper and the virtual environment.
Exit codes below are the Python CLI exit codes; nonzero child codes were separately
captured because the wrapper normalizes failures.

| Python command | Exit | Observed result |
|---|---:|---|
| `-m pytest -q` | 0 | 663 passed, 1 skipped |
| `-m ruff check .` | 0 | All checks passed |
| `-m ruff format --check .` | 0 | 143 files already formatted |
| `-m pfa.cli db smoke` | 0 | DB_SMOKE_PASS_SYNTHETIC |
| `-m pfa.cli db status` | 3 | PERSISTENCE_DISABLED; real persistence BLOCKED |
| `-m pfa.cli db check-migrations` | 3 | PERSISTENCE_DISABLED |
| `-m pfa.cli db smoke-postgres` | 4 | NOT_VERIFIED; TEST_DATABASE_URL required |
| `-m pytest tests/test_postgres.py -q` | 0 | 1 skipped, no PostgreSQL verification |
| `-m alembic history` | 0 | empty base to 0013_initial head |
| `-m pfa.cli api smoke` | 0 | API_SMOKE_PASS_SYNTHETIC |
| `-m pfa.cli doctor` | 0 | Configuration/package/directory checks passed |

The isolated smoke invokes actual Alembic upgrade on its disposable database.
No Alembic upgrade/current command was run against an unconfigured user database.

## 13. Privacy, provenance and remaining human actions

Real intake is blocked even for ADMIN. Existing permission checks cannot substitute for
STEP 03B receipt, STEP 04 privacy/membership review or future reviewed real persistence
adapter. Input text is never accepted by the synthetic creation schema. Candidate PII
screening rejects suspect fixture content before writes. Logs and audit omit inputs,
credentials and connection URLs. Model registry and permission declarations remain
unchanged. Predictions do not authorize administrative decisions or generate gold.

Remaining actions: provision a dedicated PostgreSQL test DB and run opt-in verification;
review real user/source/text assignments; approve retention, deletion, privilege and
backup/restore procedures; obtain genuine source/privacy permissions and human research
approvals before any real-data workflow. No academic supervisor, independent pilot,
approved research dataset/model or approved real-world deployment is invented.

## 14. STEP 14 boundary

Ready for synthetic analytics development only. No analytics endpoint/dashboard or
other STEP 14 implementation was added. Research and production remain blocked.

```text
TECHNICAL_IMPLEMENTATION: PASS
DB_SMOKE: SYNTHETIC_VERIFIED
POSTGRES_INTEGRATION: NOT_VERIFIED
RBAC: PASS
AUDIT_TRAIL: PASS
REAL_DATA_PERSISTENCE: BLOCKED
STEP14_READINESS: READY_FOR_SYNTHETIC_ANALYTICS
```
