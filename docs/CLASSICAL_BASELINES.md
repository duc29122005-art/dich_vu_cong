# Classical NLP baselines (STEP 09)

These baselines implement three independent classification tasks: eight topic
labels, three sentiment labels and three supervised severity labels. Taxonomy v1.0.0
and its checksum remain unchanged. No model generates annotation gold. Current
research data and permission gates remain incomplete; synthetic scores validate
software only and are not evidence of citizen-feedback performance.

## Installation and commands

Scikit-learn is already declared in the existing `ml` dependency group. Baselines
need only its numerical dependencies and the existing data dependencies; installing
Torch, Transformers or MLflow is unnecessary for this step.

```powershell
.\.venv\Scripts\python.exe -m pip install scikit-learn
.\.venv\Scripts\python.exe -m pfa.cli ml baseline-smoke
# Conditional research examples: require an authorized frozen STEP 08B dataset.
.\.venv\Scripts\python.exe -m pfa.cli ml train-baselines --dataset service_feedback_v1 --task topic --seed 42 --config configs/baseline_v1.yaml
.\.venv\Scripts\python.exe -m pfa.cli ml train-baselines --dataset service_feedback_v1 --task sentiment --seed 42
.\.venv\Scripts\python.exe -m pfa.cli ml train-baselines --dataset service_feedback_v1 --task severity --seed 42
.\.venv\Scripts\python.exe -m pfa.cli ml compare --dataset service_feedback_v1 --task topic
.\.venv\Scripts\python.exe -m pfa.cli ml inspect --run-id ACTUAL_RUN_ID
```

Exit codes follow the existing CLI: 0 success, 2 invalid configuration/artifact,
3 blocked governance, 4 unavailable dataset/run. A missing dataset is NOT_AVAILABLE,
never a successful training run. Non-ML commands do not import scikit-learn.

## Data boundary and eligibility

`corpus.model_selection` supplies only train and validation. Its existing gate
requires the current source training permission, approved taxonomy/handbook,
privacy-reviewed source, completed real pilot, adjudicated gold and approved frozen
dataset. Revocation and changed evidence continue to block access. Synthetic data
require the existing internal temporary session capability; no user flag can
reclassify an arbitrary file as synthetic or promote it into research.

Every task uses the frozen common split assignment and its own eligibility mask.
Unknown severity has no supervised target; excluded counts and reasons are reported
per partition. Invalid labels/masks fail, rather than being repaired. At least two
training classes and one eligible validation example are required. Missing taxonomy
classes and rare classes produce explicit warnings. Class weighting defaults to
`balanced` and uses training class frequencies only.

The ML workflow never deserializes `test.parquet`, obtains test labels or invokes
the final-evaluation reader. Existing dataset integrity checks may hash test bytes;
this is bookkeeping, not model evaluation. Run metadata binds all frozen split
checksums and the test membership checksum for future evaluation. The existing
grouping primitive also checks train/validation duplicate, case/thread and text
overlap. Full holdout leakage certification remains the STEP 08 frozen-build gate.
No operating-system sandbox against a privileged file reader is claimed.

## Vietnamese TF-IDF and configuration

The sklearn Pipeline contains a FeatureUnion of word TF-IDF (1–2 grams) and
character-within-word TF-IDF (`char_wb`, 3–5 grams). Configuration can select
`word`, `char` or `word_char`. Word units use Unicode whitespace/punctuation token
boundaries, not a linguistic Vietnamese word segmenter. Character features capture
subword variants. No stop-word removal, translation or accent stripping occurs;
negations remain. Existing conservative Unicode/whitespace normalization is reused;
feature text is lowercased. Punctuation remains available to character features.

`configs/baseline_v1.yaml` uses the project's JSON-compatible YAML convention.
Both classifiers search C in [0.5, 1.0], `class_weight=balanced`, max_iter=2000,
tol=0.0001 and the supplied seed. Features use sublinear term frequency, default L2
normalization, min_df=1 and at most 20,000 features per branch. These are practical
starting configurations, not scientifically validated hyperparameters. Logistic
Regression uses lbfgs; LinearSVC uses dual=auto. Fitting limits numerical-library
thread pools to one thread for predictable resource use. Nonconvergence fails explicitly.

Each candidate fits its entire TF-IDF/classifier pipeline on training data only.
Validation is transformed using that fitted vocabulary and IDF. Selection maximizes
validation Macro-F1; ties select smaller C, then LR. No refitting on validation,
test tuning, oversampling, cross-validation or automatic threshold calibration is
performed. LinearSVC decision margins are never described as probabilities.

## Metrics and experiment records

Reports include accuracy, macro precision/recall, Macro-F1, Weighted-F1, per-class
precision/recall/F1/support and confusion matrices in stable taxonomy order.
Zero-division values are explicitly 0; all taxonomy classes remain in macro
denominators, including absent classes. Empty evaluation targets fail. Training
time includes vectorizer fitting; inference time includes transformation and batch
prediction, with total and per-record seconds. Wall-clock timing varies by machine.

An immutable UUID run directory under `data/private/ml_runs/` contains `lr.pkl`,
`svm.pkl`, `run.json` and `checksums.json`. Only the best validation candidate for
each family is serialized. Metadata records all candidate metrics/timings, selected
model, seed, config/hash, taxonomy labels/version/hash, manifest/source/build/split
hashes, task exclusions, class counts, warnings, timestamps, implementation checksum,
Python, baseline/preprocessing code hashes, transformation version and exact
numerical dependency versions/hash. This records the runtime;
it is not a complete environment lockfile or a promise of bitwise reproducibility
across numerical library/platform changes. `compare` ranks verified runs using
validation only. No MLflow service is required.

Protected temporary directories, exclusive writer lock and atomic rename prevent
partial publication and silent overwrites. Existing Git rules exclude all runs.
Reports contain aggregates, not source text, record IDs, vocabulary dumps or raw
predictions. Vocabularies in serialized models can reveal source tokens: artifacts
remain private and subject to source retention/publication restrictions.

`inspect` verifies inventory, SHA256, provenance and current dataset authorization
without unpickling. `load_model` accepts only local run IDs created by this trusted
application, verifies first, then requires matching recorded code/dependency/Python
versions. Pickle can execute code: never import third-party or untrusted run bundles.
Checksums are corruption detection, not digital signatures or protection from a
privileged administrator replacing both model and checksum. Deployment account
isolation, encryption, signatures and secure deletion are not implemented here.

## Synthetic checks and research prerequisites

Smoke builds the existing deterministic 120-record invented corpus in temporary
storage. It trains LR and LinearSVC for all three tasks, computes validation
metrics, reloads each artifact, compares predictions/metrics, verifies checksums
and test-access rejection, then removes temporary files. All results identify
SYNTHETIC; no human approvals or gold records are created.

Before research training: obtain authentic source training rights; complete privacy
review and taxonomy/handbook approval; complete real STEP 07B; annotate/adjudicate
the corpus; approve and freeze STEP 08B with leakage checks and a dataset card.
Only then run training commands. Keep the final test closed under its separate
evaluation protocol. STEP 10 models are not implemented by this change.
