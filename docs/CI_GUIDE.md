# Continuous integration

`.github/workflows/ci.yml` is configured; creating it is not evidence of a hosted run.
It uses Python 3.11, pinned checkout/setup actions, exact local package versions in
`requirements-ci.lock`, Ruff, offline pytest, E2E smoke, repository scanning and research
governance tests. The lock captures the verified local Windows environment; Linux wheel
availability/resolution must be checked by the first hosted run. It is version-pinned,
not a cryptographically hashed supply-chain lock. CPU torch packages use the official
PyTorch CPU index. No model weights or public-service datasets are downloaded.

The offline job excludes three explicit PostgreSQL test files. The separate required
PostgreSQL job creates a disposable local PostgreSQL 18.6 service and CI-only test
credentials. A required CLI preflight must pass before its explicit PostgreSQL test files
run. A missing database cannot silently pass by skipping tests. Unique owned schemas are
cleaned; no database reset is performed. No researcher's local password or production
secret is required. Workflow permissions are `contents: read`. No privileged pull-request
trigger or artifact upload exists. Package installation needs network; test/model/data
execution is offline. Docker is used by hosted services only and remains optional locally.

For a repository not connected to GitHub: first review public files with the security
scanner, keep private data ignored, then connect/push through the user's normal repository
workflow. Configure branch protection to require both jobs after the first successful run.
No push, repository creation or hosted run is performed by STEP 16.

Local equivalents:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m pfa.cli integration security-check
python -m pfa.cli integration smoke
# Separate protected local TEST_DATABASE_URL is required:
python -m pfa.cli integration smoke-postgres
```

Run dependency advisories separately as documented in SECURITY_TESTING.md. Record
unavailability separately from vulnerabilities. Review and regenerate the version lock
when dependencies change; never include editable local paths or credentials in it.

Current evidence: CI_WORKFLOW_CREATED; CI_EXECUTED_ON_GITHUB: NO; CI_RESULT: NOT_VERIFIED.

STEP 17 adds mandatory isolated release preflight and release smoke to the offline job.
`pfa.release.preflight.workflow_check` checks pinned actions, read-only permissions,
nonpersistent checkout credentials, required Python/test/offline/SQL steps and absence
of privileged triggers, production secrets or artifact uploads. This is static review,
not proof of hosted execution. To obtain hosted evidence after an explicitly authorized
repository push, open GitHub Actions, inspect both jobs' actual logs and record the real
run URL/commit/conclusion privately or in a safe technical verification record. No such
push/run is performed here. Optional advisories use DEPENDENCY_AUDIT.md.
