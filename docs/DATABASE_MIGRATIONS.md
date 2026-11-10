# Explicit migrations and PostgreSQL verification

Install the existing optional API dependencies with Python 3.11:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api]'
.\.venv\Scripts\python.exe -m pfa.cli db status
.\.venv\Scripts\python.exe -m pfa.cli db smoke
```

Default persistence is DISABLED (status exit 3). Smoke runs in a protected temporary
SQLite database, checks real migration upgrade, RBAC, review and history, then cleans
up. It reports `DB_SMOKE_PASS_SYNTHETIC`; it does not verify PostgreSQL.

For a local PostgreSQL installation on Windows, create a dedicated development
database and restricted login using PostgreSQL's administrative tooling. Generate
credentials outside the repository. Inject `PFA_DB_URL` using a protected environment
manager with driver `postgresql+psycopg`. Do not paste passwords into shell history.
Set `PFA_DB_MODE=SYNTHETIC`. This mode still permits only bundled invented fixtures.

Explicitly migrate before starting the service:

```powershell
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pfa.cli db check-migrations
```

`0013_initial` is the initial revision from an empty database. It creates five tables,
named constraints, indexes and backend-specific history/provenance triggers. Upgrade
at head is idempotent. No API startup calls `create_all`, upgrades, resets or drops
tables. Disabled persistence exposes only the original STEP 12 routes. Enabled but
unavailable/incompatible persistence returns 503 on database routes while inference
remains separately available. Health readiness describes model readiness; use `db
status` to check persistence explicitly.

Before any non-disposable migration: review SQL/script and permissions; stop writers;
take a restricted backup; test restore and upgrade on a separate database; verify
head, constraints, triggers and row counts; record the operator/change reference.
Use separate migration-owner and runtime roles. Runtime must not own tables or have
DDL/TRUNCATE/trigger-disable rights. Neither encryption nor administrator-proof
immutability is claimed. Destructive downgrade is deliberately refused; recovery
requires reviewed restore rather than an automatic reset. Future revisions must
preserve this protection. Migration DDL generation in offline mode is disabled.

## Separate PostgreSQL test

Provision a dedicated **local** database whose name ends in `_test`. Supply its
protected URL as `TEST_DATABASE_URL` (not `PFA_DB_URL`). No existing database is dropped
or reset. URLs with remote hosts or driver query options are rejected. The runner
creates a random `pfa_test_<uuid>` schema, upgrades it, exercises persistence/history,
constraints, concurrency, rollback and connection reopening, then removes only that
new schema. The test login needs schema creation permission in this dedicated DB.
Never point it at a user or production database. A forcibly interrupted test can leave
its isolated schema; inspect ownership and remove it manually after review.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli db smoke-postgres
.\.venv\Scripts\python.exe -m pytest tests/test_postgres.py -q
```

Missing TEST_DATABASE_URL: CLI exit 4, pytest explicitly SKIPPED. Configured verification
failure: CLI exit 2 and PostgreSQL NOT_VERIFIED. Successful isolated verification:
exit 0 and PostgreSQL VERIFIED. Never infer PostgreSQL readiness from offline PASS.

Optional `compose.postgres.yaml` starts only a PostgreSQL service when explicitly
invoked. It requires protected `PFA_POSTGRES_USER`, `PFA_POSTGRES_PASSWORD` and
`PFA_POSTGRES_DATABASE` environment values, binds loopback, and persists a volume.
No tool starts Docker or downloads images automatically. Protect the volume and
backups; never use `down -v` against needed data. Local installation is equally valid.
