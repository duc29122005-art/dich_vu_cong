# STEP 11: evaluation infrastructure

This implementation supports offline engineering validation now. Research comparison
is BLOCKED: authorized data, a completed real pilot, approved gold splits and genuine
pretrained PhoBERT experiments are unavailable. Synthetic scores are not scientific results.

## Adapters and compatibility

`model_adapters.describe` inspects existing STEP 09/10 manifests without executing
pickle. `Adapter` validates the descriptor again before loading. Baseline loading
requires an internal temporary synthetic capability or an explicit human
`TRUST_ARTIFACT` decision bound to the exact descriptor hash. Checksums establish
integrity, not the trustworthiness of executable pickle. Never import third-party
pickle into the application run directories.

LR and LinearSVC expose native decision scores, ordered explicitly from sklearn
classes into the frozen taxonomy order. Missing trained classes make scores unavailable.
SVM margins are never probabilities. The Transformer adapter loads existing safe
weights and the exact supplied segmentation configuration; logits are uncalibrated.
Tiny random Transformer descriptors say `SYNTHETIC_TINY_MODEL`. They cannot replace
a genuine pretrained PhoBERT run in research comparison. No model download occurs.

Comparison requires the same frozen dataset binding, taxonomy, task labels and
validation split. Conservative normalization must match. Frozen preprocessing may
differ across TF-IDF and PhoBERT, but must match within a family/task comparison.
Unknown severity and workflow exclusions retain their STEP 08 masks.

## Metrics

Metrics include accuracy, macro and weighted precision/recall/F1, per-class support,
ordered raw and row-normalized confusion matrices, and severity-high recall.
Absent classes remain in macro denominators with zero scores; absent high-severity
support yields null high recall. Empty task partitions return insufficient support
at orchestration level. The low-level metrics function rejects empty/mismatched input.

Batch latency measures prediction after model loading, including preprocessing and
tokenization. Throughput is records/seconds; zero elapsed time yields null throughput.
Model size is the validated artifact inventory size, including metadata/tokenizer and
resume files where present; it is not peak RAM or an optimized deployment size.

Optional reproducible percentile bootstrap resamples whole case/duplicate groups.
Default support requirements are 20 independent groups and five records per taxonomy
class. At least 100 and 80% of requested resamples must retain all classes. Otherwise
intervals are null with an explicit insufficient-support status. Conditional intervals
cannot establish population representativeness or generalization to unseen rare classes.

## Commands

```powershell
python -m pfa.cli ml evaluation-smoke
python -m pfa.cli ml registry list
# Research examples; require actual authorized frozen data and existing runs:
python -m pfa.cli ml registry register --run-id ACTUAL_BASELINE_RUN --family lr
python -m pfa.cli ml registry register --run-id ACTUAL_BASELINE_RUN --family svm
python -m pfa.cli ml registry register --run-id ACTUAL_PHOBERT_RUN --family phobert
python -m pfa.cli ml compare --dataset service_feedback_v1
python -m pfa.cli ml prepare-evaluation --dataset service_feedback_v1 --run-id ACTUAL_REGISTRY_ID --trust-refs data/private/trust_refs.json --segmenters data/private/segmenters.json --config configs/evaluation_v1.yaml
```

Trust references and segmenter configurations are JSON dictionaries keyed by registry
entry ID. Segmenter values use the existing `SegmentationConfig` contract and actual
local model location. No synthetic bypass switch exists. `compare --task TASK` retains
the STEP 09 baseline-only compatibility behavior; omit `--task` for unified comparison.

Comparison JSON is published immutably under `data/private/model_registry/comparisons`.
Aggregate Markdown is exclusively created under `reports/models`. Neither includes
feedback text. Preparation publishes a separate immutable experiment preview; it does
not lock a protocol, promote a model or read test labels. Errors: invalid input 2,
permission/authorization denial 3, missing artifact/dataset 4, success 0.

Smoke uses 240 invented records, six baseline entries across three tasks and one
tiny sentiment Transformer entry. It verifies adapters, checksums, comparison,
calibration, review, demo activation/rollback and denied test access. It removes its
temporary directory and creates no human approvals or research registry entries.
