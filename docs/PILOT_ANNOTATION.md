# Pilot annotation workflow

STEP 07A validates software offline. STEP 07B has not started. Real sampling
requires approved taxonomy/handbook, current STEP 02 source authorization,
STEP 04 published manifest and human privacy review, and STEP 05 quality gates.
Expired/revoked permission, inconsistent evidence or unresolved privacy risk block
access. Arbitrary external paths and benchmarks cannot become research inputs.

## Human plan and accounts

After genuine protocol approval, the coordinator stores an existing protected
request at `data/private/annotation_pilots/requests/<plan_ref>.json`. The strict
`pfa.annotation.pilot.PilotPlan` contract requires:

- `plan_ref`, `dataset_type: RESEARCH`, `source_id`, verified `dataset_version`;
- `target_count: 200`, `seed: 42`, `coordinator_sid`;
- `annotators` with exactly A and B, each containing `annotator_id` (`ann_` plus
  16 hex characters) and `windows_sid`;
- `adjudicator` with the same actor fields;
- timezone-aware `submission_deadline`, actual nonfuture `reviewed_at`,
  `reviewer_id`, protected `evidence_reference`, and verified `human_verified: true`.

All four Windows accounts and all three annotation pseudonyms must differ.
Aliases A/B are assignment slots, not authentication. Run real commands as the
designated coordinator. Other platforms fail closed for real workflows. Keep the
existing protected `PFA_FINGERPRINT_KEY` available without committing it.

## Sampling and assignment

Run these commands only after genuine authorization:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation sample-pilot --source authorized_agency_export --n 200 --seed 42 --pilot pilot_v1 --plan-ref pilot_v1
.\.venv\Scripts\python.exe -m pfa.cli annotation export --annotator A --pilot pilot_v1
.\.venv\Scripts\python.exe -m pfa.cli annotation export --annotator B --pilot pilot_v1
```

Sampling sorts non-identifying IDs, collapses exact IDs/normalized text and selects
without replacement. Proportional domain/known UTC-month strata use largest-remainder
quotas and Python 3.11 seeded random selection. Missing metadata stays unknown;
no topic is inferred. Sparse strata may receive zero quota; representativeness is
not established. Insufficient unique records fail. Immutable manifests record
algorithm, seed, quotas, counts, selected order, source checksum, taxonomy approval,
human plan and keyed duplicate-group lineage. Near-duplicates are not merged.

Both annotators receive identical order and blank labels. Each delivery contains
`annotation.csv`, its STEP 06 metadata sidecar and `context.json` containing only
sanitized text, non-identifying ID, available time and domain. Never copy context
into aggregate reports.

Control storage is `data/private/annotation_pilots/`. Separate deliveries are in
`data/private/annotation_deliveries/<pilot>/A`, B and adjudicator. New artifact
directories have owner/SYSTEM permissions; each delivery additionally grants
Modify to its designated actor. A/B must use distinct ordinary Windows accounts,
never shared coordinator/admin credentials. Coordinator/admin access is trusted;
these controls do not prevent collusion or administrator access.

Before real use, test A cannot read B's delivery or control storage and vice versa.
Synthetic tests check ACL construction, not an actual multi-user deployment.
Protect parent ACLs, backups and transfers. No encryption or secure deletion is claimed.

## Submission and corrections

Annotators retain metadata, complete labels/justifications and actual timestamps.
After checking independent-submission evidence, the coordinator creates an existing
protected `SubmissionReceipt` request with fields:
`decision_ref`, `pilot_id`, `pilot_checksum`, `actor`, `revision`,
`previous_submission_checksum` (null initially), `input_checksum`,
`context_checksum`, `annotator_id`, `independent_attestation: true`,
`human_verified: true`, actual `reviewed_at`, `evidence_reference`.
Input SHA256 binds actual submitted bytes. Context checksum comes from the assignment.
Use coordinator-only `pilot.load_pilot`, `pilot.submissions` and `pilot_store.bundle`
read APIs for bundle checksums; a manifest-file hash is not a bundle checksum.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation import --annotator A --pilot pilot_v1 --input data/private/annotation_deliveries/pilot_v1/A/annotation.csv --receipt-ref ACTUAL_RECEIPT_A
.\.venv\Scripts\python.exe -m pfa.cli annotation import --annotator B --pilot pilot_v1 --input data/private/annotation_deliveries/pilot_v1/B/annotation.csv --receipt-ref ACTUAL_RECEIPT_B
```

Every selected ID must appear exactly once with matching actor, source, dataset
and taxonomy checksum. Strict STEP 06 validation applies. Annotation times lie
between export and receipt. Modified context, stale evidence and incomplete labels
fail without automatic repair. Prior independent records are never overwritten.

Before deadline, corrections require a changed input, new receipt, explicit
`--revision 2` (then 3, etc.) and predecessor checksum. Identical repeats fail.
After deadline or finalization imports are blocked. Agreement pins exact revisions.

## Storage and smoke

Bundles use protected staging, checksums, exclusive locks and atomic rename;
existing versions refuse overwrite. A crash may leave a lock or retained export
audit without delivery. Inspect evidence as coordinator; document recovery and
create a new pilot where needed. Never silently delete/reconstruct audit history.
Apply authorized retention/deletion policy to all copies and backups. Unlink is
not secure deletion.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation pilot-smoke
.\.venv\Scripts\python.exe -m pfa.cli annotation verify-pilot --pilot pilot_v1
```

Smoke uses eight invented Vietnamese records, predetermined SYNTHETIC labels and
simulated adjudication in temporary storage. It cleans up and reports
`PILOT_SMOKE_PASS_SYNTHETIC`, no real approvals or gold. Internal temporary-session
capability permits synthetic tests; there is no CLI bypass flag.
Exit codes: 0 success, 2 invalid input/integrity, 3 blocked permission/approval,
4 missing required artifacts. Absent real data never yields a fabricated PASS.
