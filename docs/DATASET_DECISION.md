# Dataset selection decision — STEP 02

## Evidence boundary

The master plan was not present. This registry transcribes the STEP 02 project
brief, received on 2026-11-03. No source website, dataset card, license, gated
terms, record, or owner identity was independently inspected. URLs are supplied
locators, not evidence of permission. `last_verified`, ownership, coverage,
licenses, actual schemas, and unknown task labels remain `UNKNOWN`.
This document supports declared roles only; it is **not approval evidence**.

## Comparison and initial assessment

All seven sources have PENDING permission and UNKNOWN license status. No source
currently permits software tests, training, internal analysis, or publication.

| Source | Intended role and suitability | Score / 100 | Recommendation |
|---|---|---:|---|
| uit_vsfc | Vietnamese student-feedback benchmark; domain transfer must be evaluated; not primary public-service evidence | 14 | PENDING_REVIEW |
| public_service_official | Direct-domain primary candidate; obtain explicit terms before any collection | 32 | PENDING_REVIEW |
| authorized_agency_export | Preferred controlled primary acquisition route; agency and actual schema not identified | 30 | PENDING_REVIEW |
| neu_esc | Auxiliary Vietnamese NLP benchmark; reported gated access and conditions need verification | 14 | PENDING_REVIEW |
| vn_mps_qa | Terminology/QA reference only; not labeled citizen feedback | 8 | NOT_SUITABLE |
| sipas | Aggregate satisfaction context only; cannot supply individual feedback labels | 14 | NOT_SUITABLE |
| synthetic_demo | Future invented demonstration dataset, always marked SYNTHETIC; no research-valid citizen evidence | 0 | PENDING_REVIEW |

`NOT_SUITABLE` refers to individual citizen-feedback classification labels,
not every possible reference use. Legal eligibility is reported separately as
`permitted_scope`. Even an approved reference-use scope would not make QA or
aggregate indicators valid feedback labels.

## Scoring rubric

Each dimension is 0–5, multiplied by its weight and divided by 5. Total is 0–100.
Scores are conservative triage indicators, not legal decisions or measured model
utility. The CLI prints every component's rationale.

- Domain relevance (30%): DIRECT=5, ADJACENT=2, INDIRECT=1,
  SYNTHETIC/UNKNOWN=0, based only on the brief's declared context.
- Permission and privacy (30%): 5 only for an effective audited human approval
  with license, privacy, retention, and scope verification; otherwise 0.
- Label suitability (20%): 0 for every source in STEP 02. No label schema or
  quality has been inspected. Add evidence-based label scoring in a later step
  after authorized inspection; never infer labels from a dataset name.
- Coverage and metadata (10%): 0 for every source. Counts, sampling,
  representativeness, and documented collection metadata are unverified.
- Reproducibility (10%): 1 for a supplied HTTPS locator, 0 without a locator.
  No credit for immutable versions, checksums, or splits: none verified.

Decision priority: explicit denial/revocation is BLOCKED; QA/aggregate roles are
NOT_SUITABLE for classification labels; otherwise an effective approved scope
is APPROVED_FOR_SCOPE; remaining sources are PENDING_REVIEW. A high domain score
never changes permission eligibility. `assess` exit 0 means assessment completed,
not that access was granted. Future access code must call `require_access`.

## Next decision

Request 2,000–5,000 de-identified agency records using DATA_REQUEST_TEMPLATE.md.
Confirm authority, collection basis, schema, privacy, permitted scopes, retention,
labeling rights, model training, derived artifacts, and publication separately.
Verify UIT-VSFC licensing before benchmark use and NEU-ESC gated terms before
access. Do not treat public accessibility as a data-use license.

If no real dataset is approved, proceed only with isolated invented test fixtures.
These are software test metadata, not a materialized `synthetic_demo` dataset.
Mark fixtures SYNTHETIC. Do not claim real-data accuracy, domain validation, or
research conclusions. Materializing any registered dataset, including synthetic
examples for distribution, requires its own reviewed scope. STEP 03 real-data
acquisition remains blocked until authorized.
