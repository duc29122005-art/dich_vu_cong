# Evaluation protocol version 1

`configs/evaluation_v1.yaml` is a proposed research protocol. Human approval is pending.
Changing settings changes its canonical hash; each locked experiment identifies exact
settings and artifacts. The protocol must lock before any final research test read.

Eligible families: TF-IDF + Logistic Regression, TF-IDF + LinearSVC and genuine
pretrained PhoBERT with independently trained topic/sentiment/severity heads. Synthetic
random Transformers are software fixtures only. Preserve frozen taxonomy v1 label
order; do not infer label order, invent missing runs, or combine synthetic/research ranks.

Selection uses **validation Macro-F1** only. Ties use LR, SVM, PhoBERT then stable
registry ID. Secondary metrics are accuracy, macro/weighted precision/recall/F1,
per-class support, confusion matrices, severity-high recall, batch prediction latency,
throughput and inventory size. They describe tradeoffs without changing the ranking.
Rare/missing classes remain visible in fixed macro denominators; report missing
families and insufficient support explicitly rather than filling values.

Preparation freezes each task's validation-selected winner in the locked experiment.
Final reports preserve that selection. Registry research approval rejects other
runs even if their final-test scores happen to be higher; promotion cannot switch
the selection after test exposure. A new calibration/evaluation requires a new
explicit production authorization bound to the exact approved final report.

Validation group roles, fixed OVR calibration, threshold grid/risk constraints and
optional group bootstrap are specified in MODEL_CALIBRATION.md and MODEL_EVALUATION.md.
Models already selected on full validation have optimistic descriptive role-assessment
scores. Only a separately authorized untouched final holdout estimates final research
performance. High agreement or strong metrics alone cannot establish scientific validity.

## Lock and final evaluation

1. Complete real source permissions, privacy review, taxonomy/handbook approval, real
   pilot/adjudication and frozen STEP 08B dataset approval. Obtain approved training scope.
2. Train actual eligible models using train/validation only. Register verified runs.
   No genuine PhoBERT checkpoint exists yet; report its research family unavailable
   until genuine pretrained integration has been verified.
3. Prepare an experiment preview with exact eligible registry IDs, trust references,
   segmenter configurations, role membership hashes, calibrators and thresholds.
   Review the concrete preview and its returned bundle checksum.
4. Record genuine LOCK_PROTOCOL human evidence bound to that checksum, then run:

   ```powershell
   python -m pfa.cli ml lock-protocol --experiment-id ACTUAL_EXPERIMENT --approval-ref ACTUAL_LOCK_APPROVAL
   ```

5. Obtain separate FINAL_TEST model-layer evidence bound to frozen dataset and
   locked experiment. The existing STEP 08 holdout evidence is additionally required
   in annotation approval request storage: exact `version`, `test_checksum`,
   pseudonymous `reviewer_id`, timezone-aware `reviewed_at`/`expires_at`,
   `purpose=FINAL_EVALUATION`, `human_verified=true`, `evidence_reference`.
6. Explicitly initiate final access; this never happens during smoke, comparison,
   registry browsing, calibration or promotion:

   ```powershell
   python -m pfa.cli ml evaluate --dataset service_feedback_v1 --split test --all --experiment-id ACTUAL_EXPERIMENT --approval-ref ACTUAL_FINAL_APPROVAL --evaluation-ref ACTUAL_HOLDOUT_EVIDENCE --segmenters data/private/segmenters.json
   ```

The evaluator validates current source/data rights, exact artifacts, registered models,
locked protocol, calibration/threshold provenance and both human authorizations. Before
reading test labels it exclusively reserves a holdout identity derived from test content
and membership checksums. A new authorization ref cannot repeat access to that identity.
The existing corpus reader also writes its explicit test-access audit. Missing or corrupt
files never produce PASS. Failed attempts retain the reservation and a failure audit;
there is no silent retry. A coordinator must investigate without reusing exposed labels.

Final results are immutable, aggregate-only bundles containing dataset, experiment,
authorization and model descriptor hashes. They never modify annotations or thresholds.
Do not choose model families or tune any setting from these final results. Protocol
changes after exposure require a new independent holdout design and approval, not a
new reference to the same observations. Different file packaging is not a legitimate
new holdout. The coordinator must enforce scientific independence across corpus versions.

## Current state and next step

Research comparison, promotion and final evaluation remain BLOCKED. No test labels
were made available by the smoke. STEP 12 may develop a mock API against synthetic
adapters with explicit DEMO_ONLY/requires_review behavior after technical checks pass;
this implementation does not start STEP 12 or authorize real deployment.
