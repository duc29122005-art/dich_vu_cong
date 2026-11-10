# Real-data acquisition workflow

STEP 03B implements discovery records, unsigned request drafts and permission-gated
local reception. No request is sent and no real corpus has been received. The
V2.1 master plan and detailed STEP 03B prompt are present and were reviewed.
Implementation preserves the existing STEP 02/04 contracts.

## Discovery and request

`configs/acquisition_candidates.yaml` is descriptive research only. The effective
source registry and append-only permission audit remain authoritative. See
REAL_DATA_SOURCE_SHORTLIST.md for dated metadata evidence and UNKNOWN fields.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition status --source authorized_agency_export
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition request-pack --source authorized_agency_export --output reports/acquisition/agency_request_v1
```

The package contains the existing Vietnamese data-request template, checklist,
transfer specification, candidate metadata and file checksums. It refuses an
existing output directory. It is unsigned, grants no rights and is never sent by
the CLI. A responsible human must verify the owner/contact, customize/sign it and
send it separately. Document actual request/response evidence in protected storage.
Status reports permission readiness, not proof of data receipt or privacy clearance.

## Permission and authenticated handoff

After authentic human approval, use STEP 02 to record the actual license, scope,
expiry, retention and evidence. Reception requires a PRIMARY_CANDIDATE with verified
license, current matching approval and internal_analysis scope. Training/publication
remain independently gated in later steps. Expired/revoked/inconsistent evidence
blocks reception before the input file is inspected or opened.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition preflight --source authorized_agency_export --scope internal_analysis
```

Preflight does not establish supplier identity or validate a file. The coordinator
must verify the supplier/export, approved transfer channel, externally authenticated
SHA256 and byte size. Create protected handoff storage:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from pfa.annotation.pilot_store import private_directory; private_directory(Path('data/private/acquisition/handoffs'))"
```

After genuine verification, create `<handoff_id>.json` there using the strict
`pfa.data.acquisition.models.Handoff` contract:

- `handoff_id`, `source_id`, current `approval_ref`;
- non-sensitive `source_export_ref`, `supplier_reference`, responsible `reviewer_id`,
  protected `evidence_reference`;
- optional `source_manifest_ref` only when an actual supplier manifest exists;
- `transfer_method`: APPROVED_SECURE_CHANNEL or APPROVED_OFFLINE_MEDIA;
- actual `expected_sha256`, `expected_bytes`, `file_format`: `.csv` or `.jsonl`;
- actual nonfuture timezone-aware `reviewed_at`, `provenance: REAL_EXTERNAL`;
- `human_verified: true` only after human verification of authentic evidence.

No CLI flag or JSON boolean proves authorization. Protect original signed documents
separately; use pseudonymous references here. No approval/handoff is created automatically.

```powershell
# Conditional examples only: do not run until actual permission and handoff evidence exist.
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition receive --source authorized_agency_export --input data/private/incoming/approved_export.csv --approval-ref ACTUAL_APPROVAL --handoff-id agency_export_v1
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition verify --receipt-id agency_export_v1
```

The input may be a human-approved local path; use a protected incoming directory.
Traversal, symlinks/junctions, unsupported formats, mismatched bytes/hash, malformed
UTF-8/containers and duplicate source/export or payload are rejected. Transport
validation does not assert the canonical schema or remove PII.

## Receipt and STEP 04 handoff

Reception atomically publishes `data/private/acquisition/receipts/<id>/` containing
`payload.csv` or `.jsonl`, `receipt.json` and `checksums.json`. The receipt binds
source snapshot, permission/retention, human handoff, SHA256, size, actual row count,
timestamp and storage protection. Existing receipt IDs cannot be overwritten.
Verification rechecks current permission and unchanged handoff evidence before
reading payload, then checks inventory, hashes and transport counts.

`VERIFIED` means transport integrity only. `privacy_cleared` and `published` stay
false. The internal API retains a relative input path for the existing importer;
normal CLI output omits that protected path. Use the optional receipt binding:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset official import --source authorized_agency_export --input data/private/acquisition/receipts/agency_export_v1/payload.csv --approval-ref ACTUAL_APPROVAL --receipt-id agency_export_v1 --mode preview
```

The CLI checks exact source, approval and payload path against the verified receipt.
STEP 04 still runs its original authorization, schema, normalization, privacy,
deduplication and human-review gates. Source-specific mappings use its existing
`--options` contract. Commit remains separate and requires publication scope and
a valid actual privacy review; reception never commits or creates labels.

## Offline checks and status meaning

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Smoke pins the bundled synthetic fixture, uses isolated temporary storage and an
internal synthetic capability, verifies reception and STEP 04 synthetic preview,
checks unauthorized real reception and cleans up. There is no synthetic CLI bypass.
It creates no real permission, human review or research dataset.

Exit codes: 0 successful operation/draft/synthetic test; 2 invalid file/evidence;
3 blocked permission; 4 missing required evidence/receipt. Current real state is
PERMISSION_PENDING / BLOCKED_PERMISSION / STEP04_HANDOFF BLOCKED. A generated
draft is not REQUESTED; only real human request evidence can justify that claim.
RECEIVED_QUARANTINED is not privacy approval. VERIFIED is not a publishable dataset.

## Audited acquisition states

Contact milestones are recorded separately from usage permission. After verifying
actual correspondence, place a strict `ContactEvent` JSON document at
`data/private/acquisition/contact_audit/requests/<event_ref>.json`. Protect this
directory using the same `private_directory` helper as handoff storage. Required
fields are `event_ref`, `source_id`, `state`, pseudonymous `reviewer_id`, protected
`evidence_reference`, actual timezone-aware `reviewed_at`, and `human_verified: true`.
Do not include correspondence text, names or contact details in this document.

```powershell
# Conditional: requires existing genuine human contact evidence.
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition record-event --source authorized_agency_export --event-ref ACTUAL_EVENT
```

The permitted progression is DISCOVERED, CONTACT_PENDING, REQUESTED,
PERMISSION_REVIEW. REJECTED and NOT_AVAILABLE may be recorded with evidence;
reopening starts at CONTACT_PENDING. These events cannot grant usage rights.
Each immutable event bundle binds its preceding checksum and original request.

APPROVED_FOR_SCOPE derives only from current STEP 02 authorization;
READY_FOR_HANDOFF also needs matching human transfer evidence.
Reception records RECEIVED_QUARANTINED. Successful verification records
VERIFIED_RECEIPT and READY_FOR_STEP04 in a protected, immutable verification bundle
with timestamp, receipt hash, permission hash and payload hash. Repeated verify
checks the payload again without replacing that first verification record.
Revoked, denied or inconsistent authorization blocks subsequent access.

`status` reads metadata only. Its last recorded receipt state is historical and
does not prove current payload integrity; run `verify` before STEP 04. Contact
audit files and receipts remain private and Git-ignored. Hashes detect changes;
they are not signatures or protection against a privileged local administrator.

Analysis, annotation, training/evaluation, publication, redistribution and derivative
artifact rights must be reviewed explicitly. A signed request or permitted scope
for one operation does not grant the other rights. Retention/deletion evidence
remains in the existing STEP 02 permission record, referenced by the receipt;
supplied source-manifest references remain in the handoff. No missing evidence is
invented to fill these fields.
