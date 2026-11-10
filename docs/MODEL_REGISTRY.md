# Protected local model registry

Storage is `data/private/model_registry`, excluded from Git. It uses existing
protected-directory and atomic immutable JSON bundle helpers. Registration records
artifact inventory hashes, family/task, labels, taxonomy, frozen preprocessing,
dataset/split provenance, dependency versions and initial calibration status.
Research entries begin CANDIDATE; synthetic entries are DEMO_ONLY in a separate
namespace accessible only inside the internal temporary synthetic capability.

Each lifecycle event is a new numbered immutable bundle linking the preceding bundle
checksum and exact registration-record hash. Registration records are never rewritten.
`registry inspect` presents the immutable record, derived lifecycle status and full
event history, including evaluation and approval references. Calibrator/threshold
provenance lives in the referenced immutable experiment; final reports reference that
experiment. No automatic activation happens during registration, comparison or testing.

```powershell
python -m pfa.cli ml registry list
python -m pfa.cli ml registry inspect --run-id ACTUAL_REGISTRY_ID
python -m pfa.cli ml registry approve --run-id ACTUAL_REGISTRY_ID --evaluation-id ACTUAL_FINAL_REPORT --approval-ref ACTUAL_RESEARCH_APPROVAL
python -m pfa.cli ml registry promote --run-id ACTUAL_REGISTRY_ID --approval-ref ACTUAL_PRODUCTION_APPROVAL
python -m pfa.cli ml registry rollback --task topic --to-run-id PREVIOUSLY_ACTIVE_ID --approval-ref ACTUAL_ROLLBACK_APPROVAL
```

A registry ID is the artifact run ID with `_lr`, `_svm` or `_phobert` appended.
Research approval requires a completed genuine final evaluation with metrics and
matching descriptor, and the model must be the locked validation-selected winner
for its task. Final test metrics cannot select a different winner.
Production promotion requires a separate explicit authorization bound to that evaluation.
Rollback requires a previously active model, a matching task and separate authorization.
Active lookup rechecks artifact integrity, current dataset governance, evidence expiry
and current human decision records. Revocation prevents use; registration is not a
permanent grant of source rights. Demo activation/rollback never touches research.

## Human evidence contract

The trusted coordinator supplies actual existing reviewed decisions at
`data/private/model_registry/requests/REFERENCE.json`. No CLI manufactures approval.
Required fields are `action`, `target_sha256`, pseudonymous `reviewer_id`,
`reviewer_role`, opaque `evidence_reference`, timezone-aware `reviewed_at`,
`expires_at`, `decision`, and strict boolean `human_verified`. Unknown fields fail.
Roles: research_supervisor, data_steward, independent_reviewer, student_researcher.
One independent student may record their legitimate role; this does not substitute
for institutional/source authorization, independent annotation or supervision.

Only an APPROVED, human-verified, current, exactly bound decision passes. REJECTED,
REVOKED, SUPERSEDED, expired or mismatched decisions fail. Keep underlying authentic
evidence separately protected and preserve institutional audit history. This local
metadata store trusts the coordinator's factual attestation; it does not authenticate
human identity or establish legal authority by itself.

Bindings use the existing canonical JSON SHA256 helper `pilot_store.digest`:

| Action | Target |
|---|---|
| TRUST_ARTIFACT | adapter descriptor digest |
| LOCK_PROTOCOL | experiment bundle checksum returned by preparation |
| FINAL_TEST | digest of `{dataset: frozen_binding, experiment_sha256: bundle_checksum}` |
| RESEARCH_APPROVAL | digest of `{record: registration_record_digest, evaluation: final_bundle_checksum}` |
| PRODUCTION_PROMOTION / ROLLBACK | digest of `{record: registration_record_digest, evaluation: approved_final_bundle_checksum}` |

Trust refs are revalidated before executable baseline loading. Model approval never
grants dataset rights. No approval is created during synthetic smoke.

## Limits

Checksums and chained history detect corruption and accidental rewriting. They are
not digital signatures, encryption, a distributed transactional database, or protection
against a privileged coordinator rewriting the entire store. Local exclusive writer
locks and immutable numbered event paths reject concurrent conflicting publication;
retry after inspecting a writer conflict. Keep authenticated backups and enforce OS
account/ACL policy. No network service, Hub publication or remote artifact loading exists.
