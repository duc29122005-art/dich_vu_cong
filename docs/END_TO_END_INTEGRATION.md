# Synthetic end-to-end integration

STEP 16 validates engineering contracts only. It does not authorize data collection,
establish model accuracy, or implement STEP 17.

Run from the repository root on Windows with Python 3.11:

```powershell
.venv\Scripts\python.exe -m pfa.cli integration smoke
.venv\Scripts\python.exe -m pfa.cli integration security-check
.venv\Scripts\python.exe -m pfa.cli integration performance
```

The smoke uses `pfa.db.smoke.environment`: a new temporary private directory,
random ephemeral role credentials, the existing internal synthetic capability,
Alembic migrations, a disposable SQLite database and FastAPI TestClient. No public
server, Docker, dataset, checkpoint, participant, or model download is involved.
Provider and database connections close before temporary storage is removed,
including when a check raises an exception.

The flow composes existing components:

1. Generate the deterministic STEP 07 corpus fixture (seed 8). Normalize Vietnamese
   using `conservative-1`; validate canonical feedback and screen invented PII.
   Check all eight topics, missing severity, null timestamps, duplicates and invalid inputs.
2. Validate `synthetic_demo` source metadata. Never issue real-source permission evidence.
3. Explicitly select DEMO_ONLY. Call single and batch prediction. Verify null scores,
   uncalibrated outputs, mandatory review and no administrative decisions.
4. Count persisted feedback before/after prediction: prediction is nonpersistent.
5. Explicitly persist eight bundled fixture IDs through the authorized synthetic endpoint.
   This designated adapter accepts no arbitrary citizen text. Its fixed provenance
   reference and source record reference describe the original bundled fixture;
   fixture normalization is checked separately and does not relabel an imported dataset.
6. Claim and correct one record; retain original predictions, append CREATE/CLAIM/
   CORRECT/CONFLICT events; reject stale writes and analyst edits; verify immutable triggers.
7. Call all four authenticated analytics endpoints and use the dashboard's typed API
   client and whitelisted chart transformations. No dashboard database connection exists.
8. Verify research readiness remains blocked and development readers reject protected
   test access before opening any artifact. No final evaluation is invoked.

SQLite smoke first seeds the existing 420-record analytics fixture. After eight
explicit API creations: 428 feedback, negative numerator 250, high-severity numerator
147 and 28 missing event dates. Dated counts remain seven days of 40 followed by 120.
All values are invented engineering assertions, not scientific findings. The simulated
review events never establish independent human validation.

`configs/integration_v1.yaml` pins the execution mode, source and seed and records
reviewed scanner exclusions. API secrets come only from protected environment settings;
smokes generate their own ephemeral credentials and never print them.

## PostgreSQL

```powershell
# Supply TEST_DATABASE_URL through protected local environment configuration.
.venv\Scripts\python.exe -m pfa.cli integration smoke-postgres
```

Reuse STEP 13's checks: local `postgresql+psycopg`, database name ending `_test`,
no connection query overrides. The smoke owns a fresh `pfa_test_<uuidhex>` schema.
Only that schema is removed. It never drops/resets a database or migrates a production
schema. Migration, constraints, concurrent claims (200/409), transaction rollback,
audit persistence and reopened connections are checked before the composed API flow.
The composed PostgreSQL workflow adds eight feedback to the two existing smoke cases,
so its expected analytics total is 10. STEP 14's optional PostgreSQL test separately
checks the large known-count analytics fixture.

Exit codes: 0 verified; 2 failed/unsafe input; 4 missing dependency or dedicated test
configuration. PostgreSQL absence is unavailable test coverage, not an application failure.
Historical PostgreSQL 18.6 verification remains valid even when this run lacks credentials.

`integration dependency-check` is optional and requires `pip-audit` and advisory-service
access. It is not part of offline smoke. See [security testing](SECURITY_TESTING.md).
