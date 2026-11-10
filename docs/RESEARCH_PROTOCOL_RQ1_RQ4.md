# Prospective RQ1–RQ4 research protocol, version 1

Researcher: **Dương Thị Hồng Vân**, class **EEP002-K49**, Faculty **BIT**, **UEH**.
This is one student's independent project. There is no supervisor, research team,
confirmed independent annotator or recruited participant. Affiliation does not imply
official UEH representation, ethics approval or data-provider authorization.

This document prepares methods; it reports no real findings. STEP 15 only is implemented.
STEP 16 has not started. Configuration is `configs/research_protocol_v1.yaml`.

## Separation of modes

| Mode | Permitted purpose | Scientific interpretation |
|---|---|---|
| SYNTHETIC_ENGINEERING_TEST | Internal disposable smoke/tests, invented cases, actors, clocks and mock suggestions | Formula/interface validation only; no scientific result |
| HUMAN_FEASIBILITY_PILOT | Consented real volunteers, invented materials and explicitly disclosed mock assistance | Timing/interface feasibility only; no AI effectiveness or domain accuracy claim |
| AUTHORIZED_RESEARCH | Approved real materials, gold, independently reviewed protocol, consent and documented evaluated models | Limited to the approved sampling frame and estimands |

Modes are explicit at request and observation level; mixed modes fail. The internal
synthetic capability exists only inside a temporary test session. There is no CLI
flag that turns a fixture into research, grants consent or opens the holdout.

## RQ1: which categories occur most often?

Unit: one unique feedback case. Population: the authorized observed corpus, not all
citizens. Report taxonomy-ordered topic counts, count/eligible-case shares, separate
count/known-topic shares, coverage/missingness, source distribution, available
agency/domain metadata and actual event-time coverage. Unknown dates stay unknown.
Do not multiply a case by prediction count or review-event count. Duplicate case IDs
are rejected. Prediction/review/adjudication bases are analyzed separately.

The initial real adapter accepts exact adjudicated train/validation corpus records
only, with metadata matched to the governed reader. This explicit development subset
does not represent the full corpus. Protected test labels remain inaccessible.
Predicted/reviewed bases work in engineering fixtures; a real reader for those bases
requires separately verified provenance before use. Do not relabel gold as predictions.

No probability sampling frame exists. Default uncertainty is NOT_ESTIMATED, with a
reason, rather than an unsupported population CI. A future sampling/group design
requires a prospective amendment before claims. Complaint volume alone cannot rank
agency service quality, citizen satisfaction or population prevalence.

## RQ2: how accurately do the three model families classify three tasks?

Reuse [the unchanged STEP 11 protocol](EXPERIMENT_PROTOCOL.md). Configuration and
document SHA256 hashes are pinned by the research protocol. Analytics configuration,
KPI definitions, participant-information text and dashboard task/scoring definitions
are also pinned. Protocol-check fails on changes; STEP 15 never locks, unlocks or
performs a new final-test evaluation. Allocation also binds implementation checksums;
reports record implementation and Python/Pydantic versions.

Eligible families are TF-IDF + Logistic Regression, TF-IDF + LinearSVC and genuine
pretrained PhoBERT, for topic, sentiment and severity. An untrained tiny Transformer
is not PhoBERT research evidence. Missing genuine runs remain unavailable.

Consume existing immutable STEP 11 final-report/experiment/lock/registry manifests
only after current dataset rights and taxonomy/gold gates pass. Check exact dataset,
task labels, preprocessing, approvals, selected-by-validation models and comparable
per-task support/exclusions. Expose accuracy, macro/weighted F1, macro precision/recall,
per-class metrics, confusion matrices, high-severity recall, batch latency, review
rate and automated coverage from those manifests. No re-ranking or threshold fitting
occurs. Neither scientific comparison nor nine genuine runs are fabricated.

## RQ3: how can analytics support assessment?

Evaluate three separate dimensions, never one invented utility score:

1. **Numerical correctness:** independently specified expected totals, topic counts,
   negative/high shares and daily counts compared with STEP 14 outputs. Register
   reference evidence, denominators, missingness and tolerance before testing.
2. **Alert quality:** freeze eligible windows, rules and independent reference events.
   Report TP/FP/FN/TN, precision, recall and false-positive rate only where eligibility
   and reference truth exist. Unknown/ineligible windows are exclusions, not negatives.
   Reference reviewers must not define events after seeing alerts. Synthetic spikes
   test arithmetic, not real incident detection or administrative usefulness.
3. **Human usability:** standardized denominator, missing-date, insufficient-alert and
   label-basis questions, exact choice scoring, completion time/status, usefulness
   (1–5) and optional single-item workload (0–100). No NASA-TLX or validated construct
   score is implied. Questions/keys live in `pfa.research.rq3.TASKS`; keep answer keys
   in coordinator storage, away from participant screens. Fixed questions are
   interpretation checks, not a validated usability instrument or full dashboard study.

Report participant counts and missing responses. Repeated responses are descriptive,
not independent replications. Numerical correctness does not establish human utility.
See [the KPI dictionary](KPI_DICTIONARY.md) and [alert limitations](ALERT_ENGINE.md).

## RQ4: does documented AI assistance change human performance?

Use the [controlled crossover design](RQ4_HUMAN_AI_EXPERIMENT.md). Primary outcomes:
completed-case time and exact three-task accuracy against independent human gold.
Secondary outcomes: per-task accuracy, high-severity recall/critical misses,
acceptance/override, completion, perceived usefulness/workload. Analyze participants
with equal weights and account for repeated case groups. Predefine missingness,
order and learning diagnostics. See [the statistical plan](RESEARCH_STATISTICAL_ANALYSIS.md).

## Approval and freeze sequence

1. Obtain actual source rights, privacy review, taxonomy/handbook approval, pilot/gold
   validation and a frozen research dataset through existing STEP 02–08 controls.
2. Complete institutional applicability/ethics determination; obtain any required
   review. Separately establish data-provider permission for volunteer access.
3. Complete real model evaluation under STEP 11. Choose assistance models using its
   validation policy, never RQ4 outcomes or new test peeking.
4. Review sampling, independent cases/gold, difficulty strata, group/content isolation,
   exclusions, sample-size justification, timing, material display and all thresholds.
5. Obtain actual consent, pseudonymize and freeze exact allocation, participant registry,
   cases, condition orders, protocol and three-task model references before observation.
6. Collect actual observations; record abandonment, missingness and deviations.
7. Validate current consent, package integrity and all evidence before aggregate reporting.

The software checks IDs and existing gold/registry bindings. Across distinct corpus
versions, near-duplicate/content independence and person-identity aliases require
explicit human evidence; hashes alone do not establish scientific independence.
Evidence is coordinator-controlled and can expire/revoke. No approval is generated
by a passing test. The researcher must not assert independent human verification
until suitable volunteers/reviewers actually exist.
