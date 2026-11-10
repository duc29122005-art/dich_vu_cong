# Architecture

STEP 06 adds `pfa.annotation.taxonomy` (frozen proposed instrument, strict schema
and canonical checksum), `schema` (independent annotation records/workflow states),
and `io` (empty templates and read-only CSV/JSONL validation). No dependencies were
added. The CLI reuses argparse, Settings and existing safe exception conventions.

Submission metadata binds dataset type/source/version and taxonomy version/hash.
Real validation calls existing STEP 02 permission checks and STEP 04 review-bound
manifest verification before reading annotation rows, then checks membership and
rechecks provenance before returning. Synthetic membership derives only from the
trusted bundled fixture with distinct software-only IDs. Generated templates have
no dataset identity and no records. Labels, review states and human approval are
separate; no validation result becomes gold data or overrides publication gates.

Taxonomy approval remains pending. STEP 07A technical annotation/adjudication and
agreement infrastructure is described below; real human work has not started. See
ANNOTATION_GUIDELINES.md, ANNOTATION_SCHEMA.md and ANNOTATION_WORKFLOW.md.

STEP 05 adds `quality` (strict policy/report models, timezone handling and quality
gates) and `profiling` (streaming statistics, keyed duplicate groups, transformation
audits and immutable aggregate report bundles). It extends shared preprocessing
with change counts and privacy screening with audit-only contextual patterns.
Existing STEP 04 defaults and publication contracts remain intact. All processing
uses existing Pydantic and standard-library dependencies.

The data flow is authorization, STEP 04 manifest/review verification, bounded
canonical rows, validation/normalization/privacy/duplicate diagnostics, quality
gates, then protected JSON/Markdown audit outputs. Real inputs resolve only from
verified STEP 04 storage. Synthetic CLI inputs resolve only from the checksum-bound
bundled fixture, remain SYNTHETIC and never gain research publication eligibility.
STEP 05 emits no transformed record dataset and cannot publish data. STEP 04
remains the only publication path. Reports contain keyed references and aggregate
statistics, with opaque agency/domain/status buckets instead of raw labels.
Permission and integrity checks repeat before a real report is committed.

Reports bind source manifest version/checksum, algorithm versions and policy hash.
Connected duplicate group references are available for future group-aware splitting;
STEP 07A/08A consume this lineage through the gated workflows below. See DATA_QUALITY.md,
PREPROCESSING_POLICY.md, PRIVACY_AUDIT.md and DUPLICATE_POLICY.md.

STEP 04 adds `official_schema` (canonical feedback/options), `preprocessing`
(conservative Unicode cleanup), `privacy` (candidate pattern screening),
`official_io` (bounded readers and protected storage), and `official` (permission-first
orchestration, keyed deduplication, review-bound publication and verification).
It uses existing dependencies only. Source provenance stays outside feedback
records; original IDs and raw-text fingerprints are never exported. Shared
permission decisions gain optional expiry; official imports require it explicitly.
Manifest directories serve as commit markers for immutable processed versions.
See DATA_INGESTION.md for storage, trust boundaries and recovery limitations.

STEP 03 adds `pfa.data.adapters.uit_vsfc` for bounded-batch Parquet validation,
`benchmark_http` for bounded HTTPS transfer, and `benchmark` for authorized
metadata discovery, atomic installation, manifests, and integrity verification.
PyArrow is optional in the data extra. Existing permission mechanisms are reused;
no permission records are changed. Synthetic fixture verification is explicitly
distinguished from real external data. See BENCHMARK_DATASET.md.

STEP 02 adds `pfa.data.registry` (strict source metadata), `assessment` (weighted
decision support), and `permissions` (reviewed evidence, append-only local audit,
and fail-closed scope gate). The CLI uses the existing argparse framework. These
modules use Pydantic and the standard library; no dependency was added. Registry
and decision files live under `configs`; protected evidence stays outside Git.
See PERMISSION_REGISTER.md for the trust boundary and recovery workflow. STEP 02
introduced governance only; subsequent ingestion components are described above.

STEP 01 establishes an installable research workspace, not a running ML service.
The src-layout keeps imports tied to the installed `pfa` distribution. Setuptools
supports editable development. The CLI uses argparse and needs no service runtime.

## Shared core

`pfa.core.config.Settings` validates environment values and centralizes workspace
paths. Configuration is loaded explicitly, avoiding import-time side effects.
The working directory is the default workspace; `PFA_PROJECT_ROOT` supports an
explicit workspace when running elsewhere. `.env` is loaded from the working
directory. Optional API/database components read credentials only from protected
process environment settings; other commands require no database configuration.

`pfa.core.logging.configure_logging` owns a single application stream handler and
does not modify root handlers. Callers pass the configured level and log only
operational metadata, never feedback text, identifiers, or secrets.

## Component boundaries

- Dataset (`pfa.data`): acquisition, schema validation, anonymization, annotation,
  and dataset versioning. `raw` retains restricted source inputs; `interim` holds
  intermediate data; `processed` holds validated model inputs; `benchmarks` holds
  evaluation datasets; `annotations` holds controlled labeling outputs.
- ML (`pfa.ml`): Vietnamese preprocessing, training, evaluation, and inference
  for topic, sentiment, and severity. Start with TF-IDF baselines, then PhoBERT.
  Track dataset version, split, parameters, seeds, metrics, and environment.
- API (`pfa.api`): FastAPI request validation and inference orchestration.
  Training must remain outside request handlers.
- Database (`pfa.db`): STEP 13 SQLAlchemy/Alembic persistence and synthetic review
  workflow. Credentials remain environment-only; real intake stays blocked.
- Analytics (`pfa.analytics`): STEP 14 metadata-only aggregates and descriptive alerts.
  `dashboard/` consumes authenticated aggregate APIs using Streamlit/Plotly.

ML should consume validated datasets; API should consume versioned model
artifacts; dashboard should consume authorized aggregate results. Shared core
must not import these higher-level components. Docker and MLflow integration
belong to later steps. No future component is implemented by empty packages.

## Verification

STEP 03B adds `pfa.data.acquisition` and strict `acquisition.models`. A separate
`acquisition.events` module records hash-linked human contact milestones; these
cannot grant usage permission. Immutable verification bundles bind receipt hashes,
current permission hashes and verification timestamps. Metadata-only status reports
the last recorded state; payload integrity is checked again by verify/STEP 04.
A separate
candidate shortlist records discovery uncertainty without changing effective
source permissions. Request packages reuse the Vietnamese request template and
remain unsigned/unsent. Local reception reuses STEP 02 current permission/audit
and STEP 04 source/expiry checks before input reads, then validates an existing
human handoff with authenticated SHA256/size and supplier/source references.

Data flow: metadata discovery, human source/rights review, manually sent request,
authenticated transfer evidence, protected bounded CSV/JSONL copy, immutable
quarantine receipt, integrity verification, then existing STEP 04 preview/review.
Raw reception stays under ignored `data/private/acquisition/receipts/`; protected
temporary bundles and a local writer lock provide atomic non-overwriting publication.
Optional `official import --receipt-id` checks exact receipt/source/path binding.
Transport verification grants no privacy clearance, publication or research labels.
The synthetic smoke reuses the pinned invented fixture and existing STEP 04
synthetic preview inside an isolated temporary session. No downloader, sender,
scraper, encryption or secure deletion was added. See REAL_DATA_ACQUISITION.md.

STEP 08A adds `pfa.data.splitting` for strict split/row contracts, union-find group
isolation, deterministic allocation and leakage diagnostics; `corpus` for governed
builds, protected atomic Parquet publication, dataset cards, verification and separate
development/evaluation readers; `corpus_smoke` for temporary invented fixtures.
PyArrow comes from the existing data extra; no dependency was added.

The real path requires current taxonomy and handbook approval, source authorization
including training, verified STEP 04 privacy-reviewed source storage, a completed
STEP 07B pilot, explicit human-adjudicated batches and reviewed grouping/holdout
policy. A preview computes construction/card checksums; an existing genuine human
approval binds both before publication. Immutable versions under `data/processed/`
bind source, gold revisions, taxonomy, permission/retention and split membership.
Known duplicate/case/thread relationships and exact text are unioned across batches.
Unknown severity has an explicit task mask; unresolved reviews block freezing.

All tasks share assignments. Default group-random allocation balances one primary
task; temporal splitting is opt-in and uses only verified event time. Integrity
verification never repairs a frozen version. Development readers reject test access;
a separate evidence-bound evaluation reader audits final test access. This API
boundary does not sandbox administrators or arbitrary file readers. Synthetic
capability remains temporary and cannot authorize a real build. STEP 08A creates
no trained models or official research corpus.

STEP 09 adds `pfa.ml.baseline` and `baseline_smoke`. Governed STEP 08 development
readers supply train/validation and preserve independent task eligibility. Existing
grouping detects development overlap. sklearn pipelines combine word/character
TF-IDF with LR or LinearSVC; only training fits vocabulary, IDF and classifiers.
Validation Macro-F1 selects candidates without test-label access. Protected atomic
run directories bind pipeline pickles, validation metrics, config/runtime hashes,
taxonomy and frozen dataset/split hashes. Inspection validates current governance
and checksums without unpickling. Loading is restricted to trusted local application
artifacts with matching runtime versions; checksum verification is not authenticity
against a privileged writer. A temporary synthetic capability exercises all three
tasks and cleans up. STEP 09 does not perform real research training.

STEP 10 adds `pfa.ml.phobert`, `segmentation` and `phobert_smoke`. It reuses the
baseline development readers, task masks and metrics without changing STEP 09.
An explicit local VnCoreNLP Java adapter precedes PhoBERT BPE; the isolated synthetic
path uses a labeled phrase fixture and training-only WordLevel tokenizer with a
random tiny RoBERTa model. No network downloader or remote code is used.

Three independent heads follow frozen taxonomy order. Dynamic padding, bounded
truncation, deterministic shuffling, AdamW accumulation and validation-only early
stopping/model selection operate without test-label access. Each evaluation saves
an immutable protected bundle containing best/resume safe weights, tokenizer,
optimizer/RNG safe tensors, metadata and checksums. Resume validates exact dataset,
task, code/runtime, seed, segmentation and configuration; only total epochs can
increase. Inspection/loading revalidate current data governance and provenance.
Real checkpoints require human-reviewed local inventories, immutable origin revision
and license evidence. No real PhoBERT checkpoint or segmenter has been verified;
research training remains blocked. See PHOBERT_PIPELINE.md.

STEP 11 adds `model_adapters`, `evaluation_policy`, `evaluation`, `model_registry`
and `evaluation_smoke` without rewriting STEP 09/10. Descriptors validate the existing
run inventory and governance before prediction. Baseline pickle loading additionally
requires explicit artifact trust evidence for research. Native decision scores/logits
remain distinct from JSON sigmoid-calibrated outputs; frozen taxonomy order is shared.

Governed validation groups are partitioned into calibration, threshold and descriptive
assessment roles. Preparation creates an immutable experiment preview; human evidence
locks exact protocol, models and calibration provenance before any final test access.
Final evaluation reserves a content/membership-bound one-shot audit, then invokes the
existing separately authorized corpus holdout reader. Failures retain the reservation.
Comparison, calibration, promotion and smoke do not deserialize protected test labels.

Protected registry storage uses atomic immutable JSON bundles and numbered hash-linked
events in separate research/demo namespaces. Registration does not unpickle or activate
models. Research approval requires genuine final evaluation and human evidence;
production activation and rollback require separate authorization. Current permissions,
artifact integrity and approvals are rechecked. Checksums are not signatures against a
privileged writer. Synthetic capability remains temporary and cannot grant real rights.
See MODEL_EVALUATION.md, MODEL_CALIBRATION.md, HUMAN_REVIEW_POLICY.md,
MODEL_REGISTRY.md and EXPERIMENT_PROTOCOL.md.

STEP 12 adds optional `pfa.api`: strict public schemas, environment-only settings,
an ASGI authentication/body boundary, a lifespan-owned prediction service and two
providers. FastAPI dependencies retrieve the service; no endpoint exposes model IDs,
filesystem paths or registry writes. Default APPROVED_MODEL readiness is unavailable.
Explicit local DEMO_ONLY returns constant labeled fixtures with null confidence and
mandatory review, and cannot be enabled in production.

The registry provider reuses STEP 11 active-model authorization, safe adapter loading,
frozen taxonomy/preprocessing, locked experiment and calibration provenance. Model
objects load once and release on shutdown; current control evidence/checksums are
revalidated before prediction requests. Changes require restart. No protected test
labels are accessed. Mock and authorized providers share STEP 11 review logic.

Transient privacy screening precedes inference. Ambiguous sensitive candidates bypass
models and require review; structured identifiers are redacted. Language and scope
remain unvalidated and also require review. Request bodies, response errors and logs
never persist input text. Prediction concurrency and body/text/batch bounds limit local
resource use. Authentication, CORS allowlists, demo loopback restrictions and safe
errors are tested entirely offline with TestClient. No public server starts in tests.
See API_SERVICE.md, API_SECURITY.md and API_CONTRACT.md.

STEP 13 adds `pfa.db`: frozen SQLAlchemy models, explicit Alembic migration,
per-request session injection, source-scoped repository, strict workflow schemas,
opt-in API routes and isolated SQLite/PostgreSQL verification runners. API lifespan
opens a bounded engine and validates revision/columns/history guards, without DDL.
Persistence defaults to disabled, preserving the seven original STEP 12 endpoints.
Enabled but unavailable database routes fail closed with 503. `/predict` never saves.

Protected environment principals bind unique pseudonymous actors to ADMIN, REVIEWER
or ANALYST, source grants, text access and explicit adjudication capability. Existing
inference credentials confer no persistence role. No request header/body can assign
itself a role. All roles remain subordinate to existing permission governance.

Synthetic feedback resolves from server-owned fixture IDs, passes privacy screening,
then stores original DEMO_ONLY outputs and a CREATE event transactionally. Immutable
source/model reference snapshots do not approve data or models. No real intake adapter
exists: even future source permission alone cannot bypass STEP 04 privacy/membership
review. Schema checks also disallow real flags and approved-model substitution.

Finite-state review uses a SQL version/state compare-and-swap. Current labels and
assignment change in the same transaction as append-only history; stale operations
return 409. ORM guards and backend triggers preserve predictions, events and feedback
provenance. They do not resist privileged owners or replace retention/deletion policy.
SQLite exercises portable behavior only. PostgreSQL migration, constraint/concurrency
and lifecycle verification requires a separate dedicated local TEST_DATABASE_URL;
the runner creates and removes only its new random schema. No PostgreSQL integration
is claimed when this test is skipped. See DATABASE_SCHEMA.md, DATABASE_MIGRATIONS.md,
HUMAN_REVIEW_WORKFLOW.md, RBAC_MATRIX.md, REVIEW_AUDIT.md and DATA_RETENTION.md.

STEP 14 adds strict analytics configuration/filter/response schemas, a bounded
SQLAlchemy metadata repository, pure KPI/calendar/alert functions, a service and four
FastAPI aggregate routes. Existing STEP 13 session/principal dependencies enforce
server-side role and source access. Synthetic source snapshots and model/taxonomy
references are checked before aggregation; real rows/sources remain blocked.

The repository never selects feedback text, source-record references or audit actors.
Window ranking chooses one latest prediction per task and separately the last
prediction available at final review time. One feedback remains one statistical unit
despite prediction/review history. Each request uses a read snapshot; PostgreSQL's
repeatable-read/read-only path requires optional actual PostgreSQL verification.

Label bases never backfill one another. Received event times convert from UTC to
Asia/Ho_Chi_Minh calendar days, Monday weeks or calendar months; missing dates stay
explicit. Pure aggregation applies null denominators and conservative cell/partition
suppression before response serialization. Daily moving-baseline rules validate count,
known-label, missing-time and complete-window support. They return retrospective
DEMO_ONLY indicators, not verified incidents or inferential research findings.

The separate `dashboard/` package uses a local authenticated HTTP client and whitelisted
Plotly chart transformations. It reads no database or citizen records and has no
browser-supplied API credentials. Five Vietnamese pages share a mandatory synthetic
watermark. Streamlit AppTest exercises the actual APIs via TestClient without a public
listener. Configuration defaults to loopback and disables telemetry.

An explicit empty-database fixture seeder creates only invented feedback, labels and
simulated review events. It changes no permission or research registry. Smoke uses an
isolated migrated SQLite database and cleans it up. Optional PostgreSQL analytics tests
use only a dedicated local TEST_DATABASE_URL and a new owned random schema; skipping
them never verifies PostgreSQL. See KPI_DICTIONARY.md, ANALYTICS_API.md, ALERT_ENGINE.md,
DASHBOARD_GUIDE.md and ANALYTICS_LIMITATIONS.md. STEP 15 adds the prospective
research package described below.

## STEP 15 research protocols and controlled observations

`pfa.research` adds strict mode/collection schemas, a versioned protocol bound to the
unchanged STEP 11 config/document hashes, seeded difficulty-matched AB/BA assignments,
immutable allocation previews/locks, protected observations and aggregate reporting.
It reuses existing taxonomy labels, corpus permission/gold gates, model-registry
authorization/history, STEP 11 metrics/manifests and atomic checksum bundles. No new
dependency, database table, migration, model approval authority or public endpoint
is introduced. Existing API/RBAC/review behavior remains intact; researcher filesystem
commands require trusted coordinator OS access rather than granting a new ADMIN role.

Modes are SYNTHETIC_ENGINEERING_TEST, HUMAN_FEASIBILITY_PILOT and AUTHORIZED_RESEARCH.
Source/taxonomy/protocol/evidence checks precede protected observation reads. Human
activity additionally requires institutional applicability/ethics evidence, separate
provider participant-access rights, verified consent-event evidence and a pre-collection
allocation lock. Package rights and inputs are rechecked before report publication.
Assignment manifests contain no gold answers; reports contain no participant/case IDs
or citizen text. No input text is collected by these schemas.

RQ1 counts unique descriptive cases and explicit label bases. The initial real reader
uses exact approved development gold, never protected test labels. RQ2 revalidates and
reads existing STEP 11 reports; it does not run final evaluation or change its rules.
RQ3 separates numerical checks, reference-event alert quality and human interpretation
tasks. RQ4 measures participant-paired contrasts using crossed participant/case-group
bootstrap, reports missing/abandoned tasks and descriptive order/learning diagnostics,
and returns insufficient evidence when support/gold is absent.

Protected roots under `data/private/research` hold inputs, previews, allocations and
reports. Genuine approvals reuse the coordinator-controlled existing authorization
store. Independent experiment gold must be in disjoint verified STEP 07 pilots;
group/content independence across corpus versions still requires human review.
The internal synthetic capability is temporary only and cannot grant research access.
Blank official templates contain no observations; smoke examples live separately in
code/tests. No live participant UI, recruitment or scientific finding is supplied.
See RESEARCH_PROTOCOL_RQ1_RQ4.md and RESEARCH_REPORTING_GUIDE.md.

## STEP 16: integrated engineering validation

`pfa.integration` composes existing preprocessing, source registry, demo provider,
FastAPI/SQLAlchemy repositories, review state machine, immutable history, analytics,
dashboard transformations and research-readiness contracts. Temporary synthetic
storage and ephemeral credentials isolate every smoke. Prediction remains nonpersistent;
explicit synthetic intake is a separate API call. No data permission gate is weakened.

The PostgreSQL path reuses STEP 13's dedicated-target validation, migration, unique
schema, constraints, rollback/restart checks and concurrent claims. An optional workflow
callback runs the composed analytics/dashboard flow within that same owned test schema.
SQLite and PostgreSQL evidence are reported separately; historical verification is
not revoked when a new shell lacks TEST_DATABASE_URL.

API middleware collects bounded process-local request/error/failure counts and latency,
retaining existing privacy-safe structured logs. Opt-in ADMIN operational status includes
model readiness, DB health and source-scoped queue size. Default API contracts are preserved.
The repository scanner reports locations/rules without discovered values, checks tracked
and unignored candidates, and binds reviewed false positives to exact line hashes.

GitHub Actions defines offline and disposable PostgreSQL jobs with minimal permissions,
pinned action revisions and exact package versions. No production secrets, sensitive
uploads, pretrained weights or datasets are required. Hosted execution is unverified.
See END_TO_END_INTEGRATION.md, THREAT_MODEL.md and BACKUP_RESTORE.md.

## STEP 17: local release and technical handover

`pfa.release` adds a strict TECHNICAL_DEMO_ONLY configuration, lock/version/import checks,
server-side credential preflight, static CI review, explicit advisory/SQL checks and an
offline release smoke. It reuses STEP 16 integration and the existing synthetic store,
analytics fixture, API factory, human review and dashboard. Live local demonstration is
an internal synthetic test application: a new owned temporary root holds its private
SQLite database, migrations and fixed fixture. No on-disk capability marker, real-data
gate override or existing-database reset is introduced. The process-lifetime internal
synthetic capability ends before cleanup. Actual production injection remains forbidden.

The analytics seeder optionally accepts a validated identifier seed for deterministic
opaque model/feedback/prediction/event UUIDs. Default behavior and mathematical fixtures
remain unchanged; nonempty targets still fail. Separate foreground launch commands bind
127.0.0.1, check occupied ports and keep credentials in process environment. The Streamlit
child receives only its restricted ANALYST credential; API and database secrets are removed.

Release manifests inventory explicit public source/configuration/templates and hashes,
with actual build time, optional Git revision, fixture/model provenance and restrictions.
Version/content hashes are reproducible; timestamp/Python/revision are generation metadata.
Generation attestations and private data/models/dumps/secrets are excluded. Immutable
bundle verification detects changes. No archive or external publication is performed.
Research deliverables are prospective templates and a blocked readiness matrix; no
scientific result, human acceptance or independent validation is manufactured.

STEP 07A adds `pfa.annotation.approval` for exact taxonomy/handbook human
checkpoints, `pilot` for sampling/assignment/import/adjudication, `agreement` for
stdlib nominal Cohen's Kappa, `pilot_store` for protected immutable bundles, and
`pilot_smoke` for temporary SYNTHETIC demonstrations. No dependency was added.

Real data flow is: current taxonomy checkpoint and permission, verified STEP 04
publication and STEP 05 privacy/quality, approved plan, deterministic unique pilot,
isolated blank A/B assignments, evidence-bound independent submissions, agreement,
explicit human review of every record, immutable final decisions and verification.
The existing STEP 06 schema validates records throughout. Dataset manifests,
taxonomy checksum, plan, submission revisions and final decisions remain linked.
Unknown severity and unresolved workflow states cannot become gold labels.

Control storage is protected `data/private/annotation_pilots/`; separate actor
deliveries are under `data/private/annotation_deliveries/`. Real operations require
the designated Windows coordinator; ordinary actor accounts receive isolated ACLs.
Coordinator/admin access is trusted. Checksums are corruption checks, not signatures.
Human evidence authenticity and deployed account isolation require human verification.
Retention follows existing source policy; no encryption/secure deletion is claimed.
Synthetic workflow capability exists only inside an isolated temporary session and
cannot create real approvals or research gold. STEP 07B and STEP 08B remain blocked.
See PILOT_ANNOTATION.md and PILOT_RESEARCH_PROTOCOL.md for operational prerequisites.

Tests use temporary directories and subprocesses to exercise configuration,
CLI exit codes, missing directories, permissions, and privacy-safe failures.
No network, GPU, Docker, or database is required. Doctor performs real temporary
write probes; tests also simulate denied writes for consistent Windows coverage.
