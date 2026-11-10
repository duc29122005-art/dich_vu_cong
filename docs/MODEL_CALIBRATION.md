# Validation-only confidence calibration

Native LR/SVM decision scores and Transformer logits are not calibrated probabilities.
Softmax normalization alone does not prove calibration. Percentage-based reliability
claims require independent supporting research; this implementation makes none.

`configs/evaluation_v1.yaml` selects OVR sigmoid calibration with fixed regularization
and seed. A separate logistic sigmoid fits each ordered class score against its
one-versus-rest target; outputs are renormalized across classes. This is not a joint
multinomial calibration model. Its assumptions and rare-class behavior require review.
Coefficients/intercepts are finite validated JSON arrays, never executable serialization.

The governed validation partition is grouped by exact duplicates and available
case/thread relationships before deterministic seed-42 role allocation:

| Role | Target | Use |
|---|---:|---|
| calibration | 40% | Fit sigmoid coefficients only |
| threshold | 30% | Select human-review threshold only |
| assessment | 30% | Descriptive calibration/review diagnostics |

The greedy allocation preserves groups and fills size deficits. Actual proportions
can deviate. At least three groups are required. Every row belongs to exactly one
role; task masks apply after allocation. Exported role counts and opaque membership
hashes permit auditing without text. Calibration and threshold APIs reject provenance
that does not explicitly identify the validation split. Production orchestration
supplies these roles from governed data; arbitrary caller-provided score arrays are
not evidence of authorized research.

At least two calibration positives per taxonomy class are required by default.
Missing scores/classes yield UNAVAILABLE. Missing threshold support yields
ALL_REQUIRE_REVIEW. No score, missing label or unknown severity is fabricated.

STEP 09/10 already selected models using the full validation partition. Therefore
STEP 11 assessment is explicitly **descriptive post-selection validation**, not an
unbiased final performance estimate. Separating calibration and threshold roles
prevents reusing their observations for assessment, but does not undo upstream
model-selection optimism. A genuine untouched, separately authorized final test is
required for research performance estimation. No test observations fit calibrators
or select thresholds. Group bootstrap uncertainty remains conditional on fixed models.

Diagnostics include multiclass Brier score (sum of squared class errors; range 0–2)
and ten-bin top-label reliability/ECE. Empty bins have null means/accuracy. Top-label
ECE is not complete multiclass calibration validation; small samples and imbalance
can conceal poor calibration. The smoke's known-score sigmoid self-check is labeled
IN_SAMPLE_METHOD_SELF_CHECK_NOT_PERFORMANCE_ESTIMATE. It verifies arithmetic only.

Calibrators, thresholds, protocol hash, model descriptor hash, split checksums and
role membership hashes are bound in the immutable experiment preview. Final evaluation
revalidates these bindings and never refits them. Change any component before locking
a new protocol; after final exposure a new independent holdout design is required.
