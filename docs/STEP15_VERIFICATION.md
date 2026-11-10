# STEP 15 technical implementation and verification

Implemented STEP 15 only. STEP 16 was not started. No real dataset, pretrained
checkpoint, human participant, consent, ethics approval or scientific result was
created or downloaded. The project remains one student's independent work:
Dương Thị Hồng Vân, EEP002-K49, BIT, UEH, without a supervisor, research team or
confirmed independent annotators.

## 1. Files

Created:

- `src/pfa/research/__init__.py`, `schemas.py`, `protocol.py`, `assignments.py`,
  `statistics.py`, `rq1.py`, `rq2.py`, `rq3.py`, `rq4.py`, `validation.py`,
  `reporting.py`, `smoke.py`, `commands.py`.
- `configs/research_protocol_v1.yaml`.
- `templates/research/README.md`, and nine sets of blank CSV/JSONL/JSON Schema
  files: participants, assignments, manual_observations, assisted_observations,
  dashboard_tasks, questionnaire, gold_references, deviations, consent_events.
- `tests/test_research.py`.
- `docs/RESEARCH_PROTOCOL_RQ1_RQ4.md`, `RQ4_HUMAN_AI_EXPERIMENT.md`,
  `RESEARCH_STATISTICAL_ANALYSIS.md`, `RESEARCH_PARTICIPANT_CONSENT.md`,
  `RESEARCH_DATA_COLLECTION.md`, `RESEARCH_REPORTING_GUIDE.md`,
  `RESEARCH_LIMITATIONS.md`, and this report.

Modified:

- `src/pfa/cli.py`: lazy research CLI integration; previous commands preserved.
- `.gitignore`: allow official blank research CSV/JSONL templates; collected inputs
  and reports remain in ignored private storage.
- `README.md`, `docs/ARCHITECTURE.md`: research integration and boundaries.
- `src/pfa/db/repository.py`, `docs/REVIEW_AUDIT.md`: deterministic logical ordering
  for successful audit events with identical timestamps, exposed during regression.

No dependency, DB entity, migration, public API route or model approval authority was
added. Existing STEP 11 configuration, document, lock and final-test code are unchanged.
Repository files were already untracked; no commit or unrelated deletion was made.

## 2. RQ implementations

**RQ1:** unique case counts, frozen taxonomy order, topic shares with both total and
known-label denominators, coverage/missingness, source/available agency/domain
distributions and actual event-time coverage. Label bases stay separate; duplicate
cases fail. No population CI is invented without a justified sampling design.
The initial real adapter accepts exact authorized adjudicated development records
only; its explicit subset limitation prevents claiming full-corpus/population results.

**RQ2:** consume and revalidate existing STEP 11 final-result, experiment, lock and
model-registry manifests. Preserve validation selection, taxonomy/preprocessing and
per-task eligible support/exclusions. Reuse existing accuracy, F1, precision/recall,
per-class/confusion, high recall, latency and review/coverage metrics. Missing genuine
families remain unavailable. A tiny random Transformer is rejected as pretrained
research evidence. No new model training, threshold tuning or final-test call occurs.

**RQ3:** separate numerical expected/observed checks, reference-event alert quality
and human usability tasks. Alert TP/FP/FN/TN and denominator-based rates exclude
ineligible/unknown-reference windows. Fixed Vietnamese questions test denominator,
missing-date, alert-support and label-basis interpretation. Completion accuracy/time
and optional usefulness/workload remain descriptive with missingness explicit.

**RQ4:** validate measured, assigned human observations and analyze completed-case
time and independent-gold accuracy. Report condition completion, missing/abandoned
tasks, per-task accuracy, high-severity recall/critical misses and suggestion
retention/override. Missing gold or statistical support yields INSUFFICIENT_EVIDENCE.
Mock suggestions never establish real effectiveness.

## 3. Design and randomization

Seeded, deterministic AB/BA crossover, balanced to within one participant. Match
easy/medium/hard counts within participant conditions; allocate different case groups
and avoid all repeated case exposure within a participant. Greedy global exposure
balancing is recorded without claiming exact equality or equal true difficulty.

Immutable previews permit review before a separate allocation approval. Frozen
manifests bind exact participants, case pool, protocol, implementation, source/dataset
and all three assistance model references. Reassignment/overwriting after observation
is rejected. Independent experiment gold must come from disjoint verified STEP 07
pilots. Human review remains necessary for cross-version content/group isolation and
actual-person aliases; different IDs do not prove independence.

## 4. Statistics

Equal-participant paired AI-minus-manual contrasts; crossed participant/case-group
percentile bootstrap, reproducible seed and 1,000 default replicates. Require 20
paired participants, 20 observed independent case groups, five pairs per order and
at least 95% usable replicates before reporting an interval. These are technical
floors, not demonstrated power. Include raw and paired standardized effects,
descriptive AB/BA order contrasts and within-condition time/position learning
diagnostics. Zero SD, zero denominators and unsupported intervals remain null.

The prospective sample-size strategy uses a genuine feasibility pilot, meaningful
effect/precision targets, participant-difference variability, case heterogeneity,
attrition and reviewed design simulation. No true variance, power or recruitment
target is invented. No p-values, significance/equivalence or automatic improvement
claims are generated. Completed-case time and convenience sampling have explicit
selection/generalizability limitations.

## 5. Templates and consent/privacy gates

Nine official blank schemas have zero rows; schema validation grants no rights.
Working copies belong in protected `data/private/research/`, never committed templates.
Pseudonyms use `p_` plus 16 random hex characters; identity/signature maps stay separate.
No citizen text, participant name/contact or free-text comments are accepted by
observation contracts. Reports omit participant/case IDs and text.

Real/human packages require current exact RESEARCH_PACKAGE authorization;
PARTICIPANT_PROTOCOL evidence for actual institutional applicability/ethics review;
separate HUMAN_PARTICIPANT_ACCESS rights (provider/steward for real materials);
VERIFY_CONSENT_EVENT evidence; and a pre-collection RESEARCH_ALLOCATION lock.
Consent must precede observation and remain valid. Withdrawal blocks retained
observations, including automatic restoration through later re-consent. Inputs and
rights are rechecked before atomic report publication. No approval is generated.

Vietnamese information, consent, withdrawal, pseudonymization and retention templates
state all current unknowns and the researcher's actual independent status. Proposed
retention periods await applicable institutional/provider review. OS permissions,
trusted coordinator evidence, encryption/backups and disclosure review remain needed;
checksums are not proof of voluntary consent or protection from privileged operators.

## 6. CLI and synthetic evidence

Commands use `.venv/Scripts/python.exe -m pfa.cli`; RTK prefixes are omitted here.
Exit codes below are captured child-process codes, not wrapper normalization.

| Command | Exit | Result |
|---|---:|---|
| `research status` | 0 | PROTOCOL_PREPARED_NOT_HUMAN_APPROVED; RQ1–RQ4 blocked |
| `research protocol-check` | 0 | PROTOCOL_CHECK_PASS; human approval pending |
| `research templates --output templates/research` | 0 | Nine blank schemas created; zero records |
| `research templates` | 0 | BLANK_TEMPLATES_VERIFIED |
| `research smoke` | 0 | RESEARCH_SMOKE_PASS_SYNTHETIC |
| `research report --rq all --source <temporary control metadata>` | 3 | BLOCKED_ON_RESEARCH_DATA before observation access |
| `research report --rq rq4 --source <temporary control metadata>` | 3 | BLOCKED_ON_EXPERIMENT before observation access |
| Invalid report schema (unit/integration) | 2 | INVALID_RESEARCH_INPUT; submitted values withheld |
| `analytics smoke` | 0 | ANALYTICS_SMOKE_PASS_SYNTHETIC |
| `api smoke` | 0 | API_SMOKE_PASS_SYNTHETIC |
| `db smoke` | 0 | DB_SMOKE_PASS_SYNTHETIC, SQLite |
| `db smoke-postgres` | 4 | TEST_DATABASE_URL required; NOT_VERIFIED in this run |
| `doctor` | 0 | PASS |

Synthetic smoke creates 24 invented participants, 144 assignments (12 AB/12 BA),
143 invented observations (142 completed, one abandoned) and one unobserved assignment.
It verifies case/topic denominators, both conditions, deterministic allocation and
crossed bootstrap, schema/consent/missing-support gates, report repeatability,
aggregate privacy, immutable allocation and cleanup. It reuses STEP 11 metric and
compatibility functions on invented label vectors, **not genuine trained model runs**.
All temporary input, assignment and report artifacts are removed.

## 7. Holdout and reproducibility

Protocol SHA256: `7afd349bc03a75d73785623798a23447b5dcfb1a5bbbbcb8963d6ec1e8af881a`.
STEP 11 config SHA256: `6cd408f1e4b9f01beaa8cfca8c0baa4107eeab649c22c85798a85d42103d897a`.
STEP 11 document SHA256: `cf3d91f615a2493a03c522f7a30292a94fd111398570e85daa314baca7ca1a68`.

Analytics configuration, KPI dictionary, participant-information document and dashboard
task/scoring definitions are also pinned. Allocations bind implementation checksums;
reports record implementation and Python/Pydantic versions. Exact authorized inputs
produce deterministic aggregate bundles and IDs. Changed code/materials cannot
silently analyze an old allocation.

Research functions never call `corpus.evaluation_data`, `final_evaluate`, model
promotion or a test partition reader. Guard tests forbid those paths, reject test
membership before observation/gold reads, and reject synthetic-to-research mode
changes. Existing STEP 11 final-access reservations and audit rules are untouched.

## 8. PostgreSQL and regressions

The user's prior PostgreSQL 18.6/pfa_test verification is historical context. This
process has no TEST_DATABASE_URL or protected PFA_DB_URL available. No credentials
were guessed, no DB was reset, and no PostgreSQL connection was attempted. Current
run PostgreSQL verification is NOT_VERIFIED; SQLite/statistical success does not
replace it. Existing dedicated-schema PostgreSQL tests remain optional and unchanged.

Baseline reproduced here: 736 passed, two PostgreSQL tests skipped, exit 0; Ruff lint
and format passed. This differs from the user-reported 738/zero skips because the
dedicated test credential is unavailable in this process, not because tests were removed.

An initial full run exposed tied-clock audit ordering by random UUID. History now
uses successful review versions to order tied timestamps and puts null-version
conflicts last in that tick, without changing stored timestamps or schema. A
deterministic test forces equal clocks and reverse UUIDs. Tied conflicts still have
stable UUID order, without claiming causality finer than the stored clock.

Targeted research/database verification: 149 passed, exit 0.
Final full suite: **822 passed, 2 skipped, 0 failed** in **145.17 seconds**, exit **0**.
This preserves the 736 reproduced baseline passes and adds 86 research/regression
passes. Both skips are the unchanged optional PostgreSQL tests. All ordinary tests
ran offline. Ruff lint and format check both passed, exit **0**; 188 files already
formatted. No PostgreSQL success is inferred from these skips.

## 9. Remaining blockers and STEP 16 boundary

Actual source/participant-display permission; authorized acquisition/privacy review;
approved taxonomy; real independent pilot/gold and frozen data; genuine evaluated
models including pretrained PhoBERT; institutional applicability/ethics determination;
actual volunteers/consent; justified sample size; blinded participant material and
instrumented collection; real observations; and disclosure/retention review remain
outstanding. No scientific result is available for RQ1–RQ4.

STEP 16 readiness means synthetic end-to-end testing can be planned. It does not
authorize recruitment, real processing, model deployment or scientific claims.

TECHNICAL_IMPLEMENTATION: PASS

RESEARCH_SMOKE: SYNTHETIC_VERIFIED

RQ1_REAL_RESULTS: BLOCKED

RQ2_REAL_RESULTS: BLOCKED

RQ3_REAL_RESULTS: BLOCKED

RQ4_REAL_EXPERIMENT: BLOCKED_ON_EXPERIMENT

CONSENT_AND_PRIVACY_GATES: PASS

POSTGRES_INTEGRATION: NOT_VERIFIED

STEP16_READINESS: READY_FOR_SYNTHETIC_E2E
