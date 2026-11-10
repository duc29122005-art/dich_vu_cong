# Mock model card

Provider: MOCK_FIXTURE; live version: mock-fixture-v1. Classification: DEMO_ONLY.
No trained model artifact, research dataset or model approval is included in this release.
The live provider returns topic=other, sentiment=neutral, severity=medium regardless of
input meaning. This validates contracts, not NLP inference. Seeded analytics labels use
analytics-fixture-v1 predetermined values and are separately marked synthetic.

Scores: null. Calibrated: false. Human review: always required. Administrative decisions:
not allowed. No accuracy, F1, confidence, robustness or fairness estimate is claimed.

Existing Logistic Regression/LinearSVC and PhoBERT infrastructure is retained for future
authorized experiments. LinearSVC margins are not probabilities. The tiny random
Transformer smoke is not pretrained PhoBERT and supplies no genuine research evidence.
APPROVED_MODEL serving remains blocked until registry scope, artifact integrity,
taxonomy/preprocessing, real-data/model evaluation and deployment approval gates pass.

Intended use: local interface/integration demonstration with invented inputs. Do not use
for triage, crisis detection, public-service ranking or citizen administrative decisions.
Real model cards require genuine checkpoint/dataset provenance, comparable evaluation,
calibration, review thresholds, uncertainty and limitations; those sections remain pending.
