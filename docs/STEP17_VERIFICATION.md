# STEP 17 technical demo release verification

Release: `pfa-0.1.0-technical-demo-1`. Classification: **TECHNICAL_DEMO_ONLY**.
This record documents local engineering validation, not completed scientific research,
production deployment or independent acceptance. Only STEP 17 is implemented here.
No real citizen data, pretrained weights, participant observations, consents or approvals
were created or downloaded. The project remains one student's independent research.

## Created and modified files

Created source, configuration and checks:

- `src/pfa/release/__init__.py`
- `src/pfa/release/config.py`
- `src/pfa/release/preflight.py`
- `src/pfa/release/demo.py`
- `src/pfa/release/manifest.py`
- `src/pfa/release/audit.py`
- `src/pfa/release/smoke.py`
- `src/pfa/release/commands.py`
- `configs/release_v1.yaml`
- `requirements-audit.lock`
- `scripts/verify_demo.ps1`
- `scripts/start_demo_api.ps1`
- `scripts/start_demo_dashboard.ps1`
- `tests/test_release.py`

Created documentation:

- `docs/DEMO_QUICKSTART.md`
- `docs/DEMO_WALKTHROUGH.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/RELEASE_NOTES.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/TECHNICAL_HANDOVER.md`
- `docs/DATASET_CARD_DEMO.md`
- `docs/MODEL_CARD_DEMO.md`
- `docs/DEPENDENCY_AUDIT.md`
- `docs/BACKUP_RESTORE_REHEARSAL.md`
- `docs/RESEARCH_READINESS_MATRIX.md`
- `docs/STEP17_VERIFICATION.md`
- `docs/research/PAPER_OUTLINE.md`
- `docs/research/METHODOLOGY_SUMMARY.md`
- `docs/research/RQ1_RESULTS_TEMPLATE.md`
- `docs/research/RQ2_RESULTS_TEMPLATE.md`
- `docs/research/RQ3_RESULTS_TEMPLATE.md`
- `docs/research/RQ4_RESULTS_TEMPLATE.md`
- `docs/research/LIMITATIONS_AND_THREATS_TO_VALIDITY.md`
- `docs/research/EXPERIMENT_EXECUTION_CHECKLIST.md`

Modified:

- `src/pfa/cli.py`: release command dispatch and explicit safe exits.
- `src/pfa/analytics/fixtures.py`: optional seed-based opaque identifiers; existing default
  behavior and mathematical fixture counts are preserved.
- `.github/workflows/ci.yml`: offline release preflight and smoke.
- `.env.example`: isolated temporary demo storage guidance.
- `README.md`, `docs/architecture.md`, `docs/DASHBOARD_GUIDE.md`, `docs/CI_GUIDE.md`,
  `docs/API_SERVICE.md`: release integration and handover links.

The 84-pin `requirements-ci.lock`, database migrations, model approval authority and
locked STEP 11 evaluation rules are unchanged. The workspace was already untracked;
no commit, push, repository creation, release publication or archive packaging occurred.
Generated evidence under ignored `reports/releases/` is listed below separately.

## Release architecture and launch

The versioned release configuration binds Python 3.11, project 0.1.0, API 1.0.0,
prediction-schema-1, proposed taxonomy 1.0.0 and the existing research protocol.
Configuration rejects production mode, approved serving, unrestricted bind addresses
and removal of mandatory restrictions. Taxonomy technical compatibility does not imply
human scientific approval.

Preflight checks exact installed dependency versions, imports, protocol/configuration,
blank research templates, synthetic provenance, credential roles, static CI safety and
the repository security scanner. Missing mandatory dependencies block the demo. Optional
research and operational prerequisites remain explicit warnings. Preflight never queries
an advisory service or connects to a database automatically.

`release api` creates, migrates and seeds a NEW owned temporary SQLite store inside the
existing synthetic capability. It never uses `pfa_test`, PFA_DB_URL or a private dataset.
Normal API startup still never migrates a schema. `release dashboard` runs Streamlit
against the authenticated API and strips API administrator/reviewer and DB secrets from
the child environment. Both bind only 127.0.0.1; occupied or invalid ports fail safely.
Role credentials come from process environment and are absent from command arguments.

Follow [DEMO_QUICKSTART.md](DEMO_QUICKSTART.md) to install the existing exact lock,
generate ephemeral keys in a protected parent PowerShell and launch two inherited
foreground terminals. Keep both services running. Stop each with Ctrl+C.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli release smoke
# After setting explicit DEMO_ONLY and role credentials as documented:
.\.venv\Scripts\python.exe -m pfa.cli release preflight
.\.venv\Scripts\python.exe -m pfa.cli release api --port 8000 --seed 17
# In the separately credentialed/inherited dashboard terminal:
.\.venv\Scripts\python.exe -m pfa.cli release dashboard --port 8501
```

The current machine's Restricted execution policy blocked direct `.ps1` execution.
All three scripts parsed with zero syntax errors. No policy was changed or bypassed.
The quickstart provides direct Python invocations that work without executing scripts.
A clean-machine installation and live browser acceptance session were not rehearsed;
API TestClient and Streamlit AppTest exercised the actual composed application instead.

## Synthetic verification

The launch fixture contains 420 invented records, 1,260 mock predictions and 1,050
explicitly simulated review events, covering all eight topics and optional/missing
metadata. Of those records, 400 have fixture event dates and 20 have no event timestamp.
Seed 17 reproduces opaque identifiers; another seed changes identifiers, not the fixed
mathematical scenario. Setup refuses nonempty stores. Each API launch owns a fresh store,
so repeated launch cannot duplicate an existing session's records.

The STEP 16 composed smoke separately exercises 428 synthetic records, validation,
privacy rejection, provenance, explicit demo inference, nonpersistent prediction,
authorized synthetic intake, correction, immutable prediction history, append-only audit,
role denials, conflict handling, known analytics counts and dashboard transformations.
The release smoke reuses it, exercises seeded launch health/model status, publishes and
verifies a temporary source manifest, then verifies cleanup. Scores remain null,
calibrated=false and human review required. Model status reports mock DEMO_ONLY.
No synthetic correction or simulated adjudication constitutes independent human evidence.

Protected final-test access remains blocked; no final evaluation was invoked. Regression
checks retain the existing holdout sentinel, source permission enforcement, privacy-safe
logs, small-cell suppression and research-report blockers. No model or dataset is approved.

## Commands and application exit codes

Captured evidence: `reports/releases/final_checks_v1/commands.json`. The command prefix
below is `.venv\Scripts\python.exe -m pfa.cli`. Child application exits were captured
directly because the RTK shell wrapper normalizes nonzero exits.

| Command | Actual status | Exit |
| --- | --- | ---: |
| `doctor` | `DOCTOR_PASS` | 0 |
| `release preflight --isolated` | `WARNING`; mandatory isolated checks pass | 0 |
| `release preflight` (unconfigured shell) | `BLOCKED`; explicit demo credentials required | 3 |
| `release smoke` | `RELEASE_SMOKE_PASS_TECHNICAL_DEMO` | 0 |
| `integration smoke` | `INTEGRATION_SMOKE_PASS_SYNTHETIC` | 0 |
| `integration security-check` | `SECURITY_SCAN_PASS` | 0 |
| `ml baseline-smoke` | `BASELINE_SMOKE_PASS_SYNTHETIC` | 0 |
| `ml phobert-smoke` | `PHOBERT_SMOKE_PASS_SYNTHETIC_TINY_MODEL` | 0 |
| `ml evaluation-smoke` | `EVALUATION_SMOKE_PASS_SYNTHETIC` | 0 |
| `api smoke` | `API_SMOKE_PASS_SYNTHETIC` | 0 |
| `db smoke` | `DB_SMOKE_PASS_SYNTHETIC` | 0 |
| `analytics smoke` | `ANALYTICS_SMOKE_PASS_SYNTHETIC` | 0 |
| `research smoke` | `RESEARCH_SMOKE_PASS_SYNTHETIC` | 0 |
| `release postgres-check` | `NOT_VERIFIED`; TEST_DATABASE_URL required | 4 |

The tiny PhoBERT smoke is random synthetic infrastructure validation, not genuine
pretrained PhoBERT evidence. Default local-service preflight fails closed without
explicit demo mode and role credentials; isolated preflight does not authorize a live
service. Tests verify configured service preflight and denial of unsafe modes/roles.

## Tests and privacy/security evidence

Baseline before STEP 17 changes: **884 passed, 3 skipped in 179.47 seconds**, exit 0.
Baseline Ruff lint and format passed; 206 files were already formatted.

Final complete suite: **918 passed, 3 skipped, 0 failed in 213.44 seconds**, exit 0.
All 884 previously passing tests remain passing. New release checks: **34 passed in
26.79 seconds**, exit 0. The three skips are optional PostgreSQL tests without
TEST_DATABASE_URL. Final Ruff lint: **PASS**, exit 0. Ruff format: **235 files already
formatted**, exit 0. `pip check`: **No broken requirements found**, exit 0.

Release checks cover configuration, complete dependency pins, credentials/source scopes,
seed stability, nonempty-store denial, failure cleanup, occupied ports, child credential
restriction, authenticated dashboard rendering, blank research templates, immutable
manifest integrity, safe paths, advisory completeness and safe CLI exits.

The scanner checks unignored candidate files as well as tracked files. This workspace
has zero tracked files, so candidate coverage is essential. Fourteen reviewed exact-line
exclusions cover existing synthetic/test/CI placeholders; no new blanket exclusions were
added. Final scan: **303 candidates, 0 tracked, 14 reviewed exclusions, 0 unresolved
findings**, exit 0. Scan findings never print discovered values. This heuristic is not proof that all
secrets or personal data are absent, and ignored private files are outside its scope.

## Dependency audit

Explicit optional installation added pip-audit 2.10.1 and 16 pinned tool dependencies;
the 84 application pins were unchanged and `pip check` passed. No ML upgrade occurred.
The final actual report is `reports/releases/audit_v3/audit.json`: **PASS**, exit 0,
84 application pins queried, no vulnerabilities, skipped packages or missing results.
Direct/transitive classifications, versions, lock hash and execution time are recorded.
Only public package metadata reached the advisory service, not research/application data.

The first report `audit_v1` was incomplete because torch's `+cpu` version was skipped;
it remains preserved as AUDIT_NOT_AVAILABLE, exit 4. The implementation now retains the
original local version and queries the upstream public version. `audit_v2` is retained
as an earlier run; `audit_v3` includes the final completeness guard. Upstream advisory
coverage does not attest binary build provenance, platform exploitability, unlisted
environment packages or complete security. Routine offline smoke never runs this audit.

## PostgreSQL, backup/restore and CI

Historical PostgreSQL verification remains **VERIFIED**: PostgreSQL 18.6 at
`D:\PostgreSQL\18`, dedicated `pfa_test`, isolated schema/migration/constraint/audit checks
and concurrent review HTTP 200/409. This release shell lacks TEST_DATABASE_URL.
**POSTGRES_CURRENT_RUN: NOT_VERIFIED**; no connection was fabricated and no earlier
verification was revoked. The release recheck reuses owned isolated-schema machinery
and rejects unsafe test targets. SQLite success is not PostgreSQL verification.

**BACKUP_RESTORE_REHEARSAL: NOT_VERIFIED**. The prepared procedure requires explicitly
created disposable source and empty target, protected credentials, dump SHA256/list
inspection, named-target confirmation, actual restore/count/constraint checks and separate
cleanup approval. No configured rehearsal target existed; no database was overwritten,
reset or deleted. Documentation alone is not recovery evidence.

**CI_WORKFLOW: CONFIGURED**. Static checks pass for Python 3.11, exact lock installation,
pinned actions, read-only permissions, nonpersistent checkout credentials, offline tests,
release smoke, research gates and the disposable localhost PostgreSQL service job.
CI requires no production secrets, real-data/model downloads or sensitive uploads.
**CI_HOSTED_RUN: NOT_VERIFIED**. No GitHub run, push or external publication occurred.
Cross-platform dependency installation remains subject to the first actual hosted run.
See CI_GUIDE.md for researcher-operated publication and inspection instructions.

## Manifest and integrity

The manifest inventories explicit public source/configuration/documentation inputs and
three known synthetic fixture files. Credentials, private datasets, dumps, approval
evidence, protected model artifacts, participant identities and logs are excluded.
Output is an immutable manifest/integrity bundle, not a distributable archive. No upload
or publication is performed. Actual generation time and optional Git revision are recorded;
a Git revision never attests uncommitted changes. This verification document is an external
attestation excluded from source inventory to avoid circular checksum dependencies.

Actual immutable output: `reports/releases/pfa_0_1_0_demo_v1/manifest.json` and
`integrity.json`. Generation time: **2026-11-05T08:53:32.502776+00:00**.
Git revision is null because no HEAD revision was available. The source inventory has
**280 files**. Both `release manifest` and the separate `release verify` returned
`RELEASE_MANIFEST_VERIFIED`, exit 0. The final release smoke also passed after this
verification document was created; temporary storage cleanup was verified.

```text
content_sha256: 7e2a4e4fb98f7100495f019d0603d11ea73fda1e5733153a5e04761e2a1bf238
manifest_file_sha256: 974511b9067f6f38c37d6d1d15399a86c9749e919edc026c911c5d4321aa31e2
bundle_sha256: c0bb58049df091dbb3a5648ab46af8bce87b701a3e020357a0406f303d822988
taxonomy_checksum: 500a61fd8f8fe49d31f3ec7eca955ebfe1856bb235e04ffc62d6f44f16f5af02
audit_lock_sha256: 6fe0aa14a3a0499ba55ddc574e85e6a51a7c538654bde761389461aa119c2f0d
```

Reproduce the source-integrity check:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli release verify --manifest reports/releases/pfa_0_1_0_demo_v1
```

Generated local evidence also includes `reports/releases/final_checks_v1/commands.json`
and the immutable `audit_v1`, `audit_v2`, `audit_v3` audit bundles. They are ignored local
reports, not packaged public artifacts. Preserve them privately for handover; no dump,
archive or deployable binary was produced. Use a NEW output path for future manifest or
audit runs; existing evidence must not be overwritten.

Application lock SHA256:
`068e90497190ffcf105d896f1ab052eaf2bd862b49109764a02c02512f1e5320`.

## Research handover and remaining blockers

[RESEARCH_READINESS_MATRIX.md](RESEARCH_READINESS_MATRIX.md) gives status, evidence,
responsibility, dependencies and verification for permission, authorized receipt,
privacy review, taxonomy approval, pilot labeling, independent agreement/adjudication,
frozen gold, baseline research runs, genuine checkpoint verification/fine-tuning,
calibration, locked comparison, authorized final evaluation, dashboard evaluation,
consent/recruitment, human observations, clustered analysis, report and retention/deletion.
No pending item is marked PASS. Future volunteers/authorities are conditional, not invented
team members or approvals. All genuine RQ1–RQ4 result templates remain PENDING.

Next actions: follow the local walkthrough, inspect a real hosted CI run when authorized,
configure only the dedicated PostgreSQL test target for fresh verification, and arrange an
explicitly disposable restore rehearsal. Research requires actual permissions, approved
gold, eligible models and genuine consented observations before scientific claims.
Technical acceptance does not satisfy those prerequisites or establish production readiness.

```text
TECHNICAL_IMPLEMENTATION: PASS
TECHNICAL_DEMO_RELEASE: READY
RELEASE_SMOKE: SYNTHETIC_VERIFIED
POSTGRES_CURRENT_RUN: NOT_VERIFIED
DEPENDENCY_AUDIT: PASS
BACKUP_RESTORE_REHEARSAL: NOT_VERIFIED
CI_HOSTED_RUN: NOT_VERIFIED
RESEARCH_DATASET: BLOCKED_PERMISSION
RESEARCH_RESULTS: NOT_AVAILABLE
RELEASE_CLASSIFICATION: TECHNICAL_DEMO_ONLY
```
