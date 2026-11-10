# Auditable research readiness matrix

All entries are prospective. Responsible researcher means the one independent student,
Dương Thị Hồng Vân. External parties below are required future evidence sources, not
confirmed collaborators, supervisors, annotators or recruited participants. Record real
evidence references privately; never change a status from absence to PASS by assertion.

| Item | Status | Required evidence | Responsible party | Blocking dependencies | Verification instructions |
| --- | --- | --- | --- | --- | --- |
| Source permission | BLOCKED_PERMISSION | genuine provider decision with scopes/expiry | researcher and actual provider | provider response | data acquisition preflight and audited scope checks |
| Authorized receipt | NOT_AVAILABLE | protected handoff receipt/hash | researcher and actual provider | permission | acquisition verify, then STEP 04 handoff |
| Privacy review | PENDING | reviewed redaction/quarantine/retention | researcher; qualified review if required | authorized receipt | STEP 05 privacy report and explicit review evidence |
| Taxonomy human approval | PENDING | meaning/order/rubric review | researcher and permitted domain reviewer if available | review arrangement | existing taxonomy checkpoint, no invented approver |
| Real pilot labeling | BLOCKED | actual pilot submissions | researcher; future eligible annotators | privacy/taxonomy/rights | STEP 07 pilot verification |
| Independent annotation/agreement | NOT_AVAILABLE | independently produced submissions and agreement | future independent annotators if recruited | actual independence/permission | inspect provenance; one researcher alone is not independent agreement |
| Human adjudication | NOT_AVAILABLE | actual disagreement decisions | explicitly authorized future adjudicator | independent labels | audit decisions, never simulated events |
| Frozen gold dataset | BLOCKED | verified gold, split/group/leakage manifest | researcher | pilot/adjudication/taxonomy | corpus verify; preserve final-test isolation |
| Baseline research training | BLOCKED | governed LR/LinearSVC runs | researcher | approved frozen gold | exact dataset/task/seed and artifact manifests |
| Genuine PhoBERT checkpoint | NOT_VERIFIED | approved origin/revision/hash/tokenizer/segmentation | researcher | authorized checkpoint acquisition | existing readiness checks; tiny model is insufficient |
| PhoBERT fine-tuning | BLOCKED | genuine reproducible run/checkpoints | researcher | gold and genuine checkpoint | resume/reload/provenance checks |
| Calibration | BLOCKED | validation-only fitted calibration/threshold | researcher | genuine runs/isolated validation | STEP 11 calibration evidence, no final-test tuning |
| Locked comparison | BLOCKED | same dataset/taxonomy/task protocol lock | researcher | eligible runs/calibration | unchanged STEP 11 manifest and authorization gates |
| Authorized final test | BLOCKED | explicit final-test scope and audit | researcher and actual rights authority as required | locked comparison | separate final evaluation only; no automatic access |
| Dashboard evaluation | NOT_AVAILABLE | real numerical/reference-event/usability observations | researcher; future volunteers if permitted | authorized data/reference tasks | STEP 15 RQ3 protocol; synthetic alerts are not utility evidence |
| RQ4 recruitment/consent | NOT_AVAILABLE | voluntary recruitment, consent and institutional determination if required | researcher; actual future volunteers | ethics/provider permission and materials | consent-state audit; no UEH approval assumed |
| Human–AI observations | NOT_AVAILABLE | frozen AB/BA allocation and actual sessions | researcher and actual consented volunteers | gold/model/consent | no repeated participant case; no mock-effectiveness claim |
| Statistical analysis | INSUFFICIENT_EVIDENCE | supported participant/case-aware observations | researcher | genuine observations and independent gold | prespecified clustered analysis, missingness and order effects |
| Research report | NOT_AVAILABLE | actual RQ1–RQ4 evidence and limitations | researcher | eligible analyses | research report authorization/provenance checks |
| Retention/deletion | POLICY_PREPARED_EXECUTION_PENDING | provider/consent retention records and verified expiration | researcher and actual custodian if any | authorized storage and retention terms | inspect protected lifecycle/backup evidence; no secure-erasure guarantee |

Technical demo acceptance, advisory PASS or a green CI run cannot satisfy these items.
