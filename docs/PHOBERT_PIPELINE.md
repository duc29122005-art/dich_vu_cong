# PhoBERT training and inference (STEP 10)

The integration targets `vinai/phobert-base` with three independent sequence
classification heads, in frozen taxonomy order: topic (8), sentiment (3), severity
(3). A real run loads a pretrained RoBERTa-compatible PhoBERT encoder and initializes
the classification head when it is absent. Missing encoder weights fail. Unknown
severity and other task exclusions come from the existing frozen eligibility masks.
No label is inferred during ingestion, and no synthetic prediction becomes gold.

Current research training is blocked. The offline smoke is a randomly initialized
tiny RoBERTa architecture with a synthetic WordLevel tokenizer and a synthetic
phrase fixture. It is **not pretrained PhoBERT**, genuine Vietnamese segmentation,
real-data fine-tuning, calibration or evidence of research performance.

## Optional installation and compatibility

Python 3.11 is retained. Baseline commands do not import Torch or Transformers.
Install the existing data dependencies and the new optional `phobert` group:

```powershell
# CPU-only installation, using the official PyTorch package index:
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e '.[phobert]'
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-smoke
```

Dependencies are Torch >=2.6,<3, Transformers >=4.46,<6, safetensors >=0.4,<1
and the existing scikit-learn metrics dependency. Tokenizers comes from Transformers.
The implementation uses an explicit PyTorch loop; Accelerate/Trainer is unnecessary.
Actual installed versions are probed and saved in every run. Compatibility was
exercised on Windows/Python 3.11 with Torch 2.15.0+cpu, Transformers 5.22.1,
safetensors 0.8.0 and tokenizers 0.23.3. Transformers 5 consumes a state dictionary
passed to save_pretrained; the best-state mapping is copied before each save.

For CUDA, install the official PyTorch wheel matching the available driver/runtime
using PyTorch's platform selector. Do not assume the CPU wheel supports CUDA.
`--device cuda` fails when CUDA is unavailable; `auto` chooses CUDA when available.
Set `CUBLAS_WORKSPACE_CONFIG=:4096:8` before launching a CUDA process. Deterministic
operations are enforced; unsupported deterministic kernels should fail rather than
silently change the reproducibility policy. CUDA has not been verified on this CPU
environment. Numerical results across devices/versions are not promised identical.

## Commands and governance

```powershell
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-smoke
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-readiness --config configs/phobert_v1.yaml
# Conditional research examples, after every data and checkpoint gate is satisfied:
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task topic --seed 42 --device cpu --config configs/phobert_v1.yaml
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task sentiment --seed 42 --config configs/phobert_v1.yaml
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task severity --seed 42 --config configs/phobert_v1.yaml
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-inspect --run-id ACTUAL_RUN_ID
```

Exit codes retain existing conventions: 0 verified operation/synthetic smoke,
2 invalid metadata/artifact, 3 blocked permission/readiness, 4 unavailable dataset/run.
No force, permission bypass, synthetic promotion or automatic hub push is offered.

`baseline.development` reuses the STEP 08 governed train/validation readers and
duplicate/case/thread checks. Real training requires current source training rights,
approved taxonomy/handbook, privacy-reviewed source, real pilot/adjudication, human
gold provenance and the approved frozen dataset. These are gates on authentic
evidence, not actions the software performs on the researcher's behalf. Working as
one student does not waive the existing independent annotation requirements.

The model pipeline never deserializes the test partition or calls the final-test
evaluation reader. Integrity checks may hash the frozen test file; labels are not
made available to training. Dataset, source, construction, split and holdout hashes
are recorded. Current authorization is checked again before checkpoint publication
and on model inspection/loading. Arbitrary privileged filesystem readers are not
sandboxed by this application boundary.

## Manually supplied pretrained checkpoint

No command downloads weights. Before a real readiness probe, an authorized human
must independently review the checkpoint origin/revision and license, then provide
a standalone local snapshot. The v1 adapter supports a single `model.safetensors`
file, `config.json`, `vocab.txt` and `bpe.codes`, plus optional flat tokenizer/license
files. PyTorch pickle `.bin` weights and sharded checkpoints are not supported in
this version. Do not load untrusted weights or convert them by executing an
unreviewed pickle. Symlinks, including typical cache snapshot links, are rejected;
use a controlled standalone copy made under the approved transfer policy.

Create a protected `data/private/phobert_requests/` directory with the existing
`pfa.annotation.pilot_store.private_directory` helper. Only after genuine human
review, record `<reference>.json` using the strict `CheckpointEvidence` contract:

- `checkpoint`: `vinai/phobert-base`; immutable 40-character `revision` commit hash;
- actual `license_name`, `license_evidence_ref`, pseudonymous `reviewer_id`,
  protected `evidence_reference`, nonfuture timezone-aware `reviewed_at`;
- `human_verified: true`, `decision: APPROVED` only after authentic review;
- `files`: the complete flat filename-to-SHA256 inventory of the approved snapshot.

Set `checkpoint_directory` and `checkpoint_evidence_ref` in a local configuration
copy and configure the real segmenter. Do not commit private paths or review
documents. The supplied inventory and commit association require human verification;
checksums are not proof of legal authorization or independent proof of origin.
The exact revision, license reference and evidence checksum are retained in run
metadata. Modified/removed review evidence blocks subsequent real model loading.

The separately invoked readiness command checks that local snapshot, supported
RoBERTa configuration, PhoBERT BPE tokenizer, vocabulary/special-token compatibility,
sequence limit, segmenter and a synthetic CPU forward pass. It reports CPU/CUDA
availability. It does not access research data, approve a license or certify CUDA
training. Without an actual successful probe, report PRETRAINED_CHECKPOINT:
NOT_VERIFIED. Default configuration intentionally has no approved local snapshot.

## Preprocessing and batching

See PHOBERT_WORD_SEGMENTATION.md. The identical segmenter and conservative Unicode
normalization run during training, validation and inference. PhoBERT BPE operates
on segmented text. The tiny fixture instead builds a training-only synthetic
WordLevel vocabulary; this cannot validate pretrained PhoBERT tokenization.

Attention masks and special tokens are preserved. Dynamic padding occurs per batch.
The requested max_length must fit both tokenizer and model; RoBERTa's reserved
position/padding indices are accounted for. Defaults request 256 tokens; smoke uses
32. Exceeding the actual limit fails, rather than silently overriding configuration.
Reports contain truncated-record counts and original token-length aggregates only.
No original text, tokens, feedback IDs or individual examples enter reports.

## Training, evaluation and resume

`configs/phobert_v1.yaml` follows the existing JSON-compatible YAML convention.
Defaults: 3 epochs, learning rate 2e-5, weight decay 0.01, batch size 8, accumulation
1, validation each epoch, patience 2, min_delta 0, seed 42 and one CPU thread.
These are starting parameters, not scientifically validated choices.

AdamW, sample-weighted gradient accumulation (including the final partial group),
finite-loss/gradient checks and clipping at norm 1 are implemented. Each epoch uses
a deterministic shuffle generator. Validation Macro-F1 selects the best checkpoint;
ties retain the earlier epoch. `min_delta` affects patience reset, not selection of
the highest-scoring saved model. Early stopping counts unsuccessful validation
intervals. No test metric participates in selection. The loop sets process RNG,
Torch threading and deterministic-operation settings explicitly.

Metrics reuse STEP 09: accuracy, macro precision/recall, Macro-F1, Weighted-F1,
per-class support/precision/recall/F1 and confusion matrices. Fixed taxonomy classes
remain in macro denominators, with zero-division values 0. Training and validation
inference times are recorded. Missing class coverage is warned; fewer than two
eligible training classes or empty validation fails.

Each evaluation creates a new immutable run/checkpoint version. The best model
and latest resumable model are separate. To continue, use `--resume-run ACTUAL_RUN_ID`
and a configuration with a larger total `epochs`; all other processing settings,
seed, task, source checkpoint, segmentation, dataset, runtime and device must match.
AdamW tensors and groups, CPU/CUDA RNG, completed epochs, optimizer steps, validation
history and patience state are restored. Resume is supported at saved epoch/evaluation
boundaries, not within an interrupted batch. An already early-stopped checkpoint
cannot silently restart selection. Existing checkpoints never change.

## Artifacts and inference

Protected, Git-ignored `data/private/phobert_runs/<run_id>/` contains best/resume
model configurations and safetensors weights, tokenizer files, optimizer safetensors
and JSON, run metadata and SHA256 inventory. Atomic temporary-directory publication
and an exclusive writer lock prevent partial/overwritten runs. Failures clean
temporary files. Retention follows the approved source policy; no encryption,
tamper-proof storage, automatic deletion or secure erasure is claimed.

Inspection verifies current dataset governance, evidence, taxonomy, labels, file
inventory and checksums. Loading also checks code/runtime versions and identical
segmenter hashes. Only known local model/tokenizer classes are loaded with
local_files_only; no remote code or pickle deserialization is used. Safetensors
reduces executable serialization risk; weights/tokenizers can still reveal source
information and must not be published without permission. Hashes are corruption
checks, not signatures against a privileged writer.

The Python batch inference API is `phobert.predict(root, registry, run_id, texts,
segmenter_config, batch_size=8)`. It applies the recorded processing and returns
label IDs/codes plus explicitly uncalibrated softmax scores. These are not calibrated
probabilities, confidence percentages, or validated thresholds. Calibration and
final test evaluation belong to a later protocol, not STEP 10.

## Resources and readiness limits

Smoke runs a 16-hidden-unit, one-layer, two-attention-head random model on CPU,
48 invented records and 32-token sequences. It trains all three heads, checks
backpropagation/inference/reload, resumes a checkpoint, rejects test access and
removes temporary storage. CPU smoke does not establish real-model memory/speed.

Real PhoBERT is substantially larger. FP32 parameters, gradients, AdamW buffers,
best-state CPU copies and activations require several GB before dataset/tokenizer
overhead. Start with a small batch and accumulation; plan approximately 16 GB host
RAM and several GB of free disk per evaluated checkpoint. CUDA VRAM needs depend
on sequence/batch configuration; no measured minimum or GPU compatibility is claimed.
Every evaluated epoch retains best/latest weights and optimizer state, so budget
disk and apply approved retention. V1 uses FP32; mixed precision and distributed
training are deliberately absent.

STEP 11 research evaluation remains blocked until real checkpoint/segmenter
validation, authorized frozen gold data and actual fine-tuning exist. This step
implements no final test evaluation, model promotion or calibration protocol.
