# STEP 16 engineering verification

Implemented STEP 16 only. STEP 17 was not started. No authorized real feedback,
pretrained weights, participant observations, consent, approvals or research findings
were created or downloaded. The project remains one student's independent research.

## Files

Created:

- `src/pfa/integration/{__init__,commands,contracts,fixtures,observability,performance,security_checks,smoke}.py`.
- `configs/integration_v1.yaml`, `requirements-ci.lock`, `.github/workflows/ci.yml`.
- `tests/test_integration.py`, `tests/test_integration_postgres.py`.
- `docs/END_TO_END_INTEGRATION.md`, `SECURITY_TESTING.md`, `PRIVACY_VERIFICATION.md`,
  `THREAT_MODEL.md`, `CI_GUIDE.md`, `OBSERVABILITY.md`, `BACKUP_RESTORE.md`, this report.

Modified:

- `src/pfa/cli.py`: five integration commands, fixed safe errors and explicit exit codes.
- `src/pfa/api/{app_factory,settings,security}.py`: process-local counters, expanded
  safe static log routes and opt-in ADMIN operational status; default seven paths preserved.
- `src/pfa/db/smoke.py`: optional observability in isolated fixture environment.
- `src/pfa/db/postgres.py`: optional composed workflow callback inside its owned schema.
- `.gitignore`, `.env.example`, `README.md`, `docs/architecture.md`.
- `docs/DATA_REQUEST_TEMPLATE.md`: replace existing personal contact values with protected
  placeholders. Private Word originals are preserved locally and excluded from Git.

No database entity, migration, model approval authority, public intake permission or
locked research protocol was changed. Repository files were already untracked; no commit,
GitHub push, Docker startup or unrelated deletion occurred.

## Integrated evidence

Existing components handle canonical validation, conservative Vietnamese preprocessing,
synthetic source provenance, explicit demo inference, SQLAlchemy persistence, review
compare-and-swap, immutable predictions/audit triggers, analytics, dashboard transforms
and research-readiness status. The synthetic flow rejects four invalid inputs, covers
eight topics, unknown severity, exact/near duplicates, invented privacy identifiers and
missing real event dates. Both prediction endpoints leave database counts unchanged.

Explicit synthetic intake creates eight linked records. One correction preserves all
three original predictions. CREATE/CLAIM/CORRECT/CONFLICT events remain append-only;
stale modification returns 409 and analyst modification returns 403. Known aggregate
counts are 428 total, 250 negative, 147 high-severity and 28 null event dates. Dated trend
remains seven 40-case days followed by 120. Dashboard transformations consume the actual
authenticated analytics responses without raw text/IDs. Research results stay blocked.
Temporary storage, providers and connections are cleaned, including failure paths.

Protected final evaluation is never invoked. A regression replaces the final reader with
a failure sentinel, and another proves the development reader denies `test` before any
manifest read. Locked STEP 11 config/document checksums and STEP 15 bindings are preserved.

## Security and privacy

Tests cover authentication/removal of credentials, ADMIN/REVIEWER/ANALYST, role escalation,
cross-source IDOR, reviewer ownership, injection-shaped strings, malformed JSON/Unicode,
bounded requests, synthetic-only intake, no history mutation, small-cell suppression,
safe logs/errors, unavailable approved models, test-target denial and cleanup.
Operational status reuses server-side roles and source permission checks.

Local scanner checks tracked files plus unignored candidates. At implementation time
there were zero tracked files, so candidate coverage is reported explicitly. Fourteen
exact-line reviewed exclusions cover invented privacy fixtures, nonsecret test sentinels
and public disposable CI credentials. Changed lines fail closed. The permitted synthetic
CSV is checksum-pinned. Secret values are never included in findings.
Heuristic scanning does not prove all PII/secrets absent or inspect ignored private files.
No public model promotion or automated administrative decision is introduced.

## Commands and exits

| Command | Output status | Application exit |
| --- | --- | --- |
| `integration smoke` | `INTEGRATION_SMOKE_PASS_SYNTHETIC` | 0 |
| `integration security-check` | `SECURITY_SCAN_PASS`, no findings | 0 |
| `integration performance` | `PERFORMANCE_SMOKE_PASS_SYNTHETIC` | 0 |
| `integration smoke-postgres` | `POSTGRES_INTEGRATION: NOT_VERIFIED`, `TEST_DATABASE_URL required` | 4 |
| `integration dependency-check` | `DEPENDENCY_AUDIT_NOT_AVAILABLE`, `pip-audit not installed` | 4 |

Shell wrapper normalization was bypassed when recording these application exits by
capturing child process return codes. Missing advisory tooling is not a vulnerability-free
result. No application data was submitted to a third party.

## PostgreSQL and CI

Historical verification remains VERIFIED: PostgreSQL 18.6 at `D:\PostgreSQL\18`, dedicated
`pfa_test`, migration/constraint/audit tests and concurrent review HTTP 200/409.
Current shell has no TEST_DATABASE_URL. Current STEP 16 PostgreSQL execution is therefore
NOT_VERIFIED; this does not invalidate earlier evidence. The optional test path and CI job
reuse owned schemas and never reset a database. No local password was guessed or copied.

CI_WORKFLOW_CREATED. CI_EXECUTED_ON_GITHUB: NO. CI_RESULT: NOT_VERIFIED.
Python 3.11 offline and PostgreSQL service jobs are configured with minimal permissions,
pinned action revisions and exact package versions. Linux dependency resolution and
hosted service execution require the first actual hosted run. No production secrets,
data/model downloads or artifact uploads are required.

## Observability, performance and recovery

Opt-in ADMIN status reports model readiness, separate DB availability, source-scoped
queue size, request/error/failure counters and mean/max elapsed time. Counters are
thread-safe and process-local; logs retain only generated traces, safe routes and timing.
They do not count individual failed batch items as separate HTTP failures.

Recorded local performance: Python 3.11.15, Windows AMD64, 16 logical CPUs, TestClient,
SQLite with 420 invented records, 20 sequential samples per operation. Tests shared the
machine during measurement. No network/production throughput guarantee is inferred.

| Operation | Median ms | Lower empirical p95 ms | Items/second |
| --- | ---: | ---: | ---: |
| Single prediction | 2.784 | 4.856 | 321.45 |
| Eight-item batch | 3.665 | 4.733 | 2150.98 |
| Feedback-count query | 0.146 | 0.238 | 5164.22 |
| Review queue | 20.201 | 22.934 | 47.90 |
| Analytics summary | 30.478 | 77.942 | 28.05 |

Backup/restore documentation covers protected PostgreSQL service credentials, custom
dump inspection, restore into a new target, Alembic head inspection, failure recovery,
registry rollback, source revocation and retention. No backup/restore operation was run;
recoverability is not claimed until a real authorized restore rehearsal occurs.

## Verification results

Baseline before changes: 822 passed, 2 skipped; Ruff lint exit 0; Ruff format exit 0
(188 files formatted). PostgreSQL skips resulted from missing test configuration.
New offline integration tests: 62 passed. Targeted integration/API/DB regression run:
178 passed before six additional integration tests were added.
Full suite: **884 passed, 3 skipped, 0 failed in 177.41 seconds**, exit 0. All 822
previously passing tests remain passing. The three optional PostgreSQL tests were skipped
because TEST_DATABASE_URL is absent; this run adds one optional PostgreSQL E2E test to
the two existing optional checks. Final targeted integration run: **62 passed**, exit 0.
Ruff lint: **PASS**, exit 0. Ruff format check: **206 files already formatted**, exit 0.
`pip check`: **No broken requirements found**, exit 0. Repository security scan:
**269 candidate files, 0 tracked files, 14 reviewed findings, 0 unresolved findings**,
exit 0. Hosted CI has not executed.

## Remaining blockers

No authorized real dataset, frozen approved gold, genuine PhoBERT fine-tuning evaluation,
approved serving model, independent human experiment or real analytics evidence exists.
Public deployment requires managed authentication/TLS/rate limiting, operational access
controls, privacy review and deployment testing. Dependency advisory checking, fresh
PostgreSQL coverage, hosted CI and restore rehearsal remain separately unverified here.
Technical demo release preparation can follow; STEP 17 implementation has not started.

```text
TECHNICAL_IMPLEMENTATION: PASS
E2E_SMOKE: SYNTHETIC_VERIFIED
SECURITY_GATES: PASS
PRIVACY_GATES: PASS
POSTGRES_INTEGRATION: NOT_VERIFIED
CI_WORKFLOW: CONFIGURED
CI_HOSTED_RUN: NOT_VERIFIED
REAL_DATA_PIPELINE: BLOCKED_PERMISSION
STEP17_READINESS: READY_FOR_TECHNICAL_DEMO_RELEASE
```

The PostgreSQL conclusion above describes current-run coverage only. Historical
PostgreSQL integration remains VERIFIED as described above.
