# Official dataset ingestion — STEP 04

## Scope and current state

The pipeline accepts authorized local UTF-8/UTF-8 BOM CSV and JSONL. It does not
download, scrape, read Excel, call external APIs, infer labels, or train models.
The master plan was absent; STEP 04 follows the supplied requirements.
No external source is currently approved and no real feedback was imported.

Flow: permission check → safe file open → streaming schema validation → Unicode
normalization and PII screening → keyed deduplication → protected preview → human
review → immutable processed version → manifest and quality verification.

## Permission and input prerequisites

Use the existing permission workflow. The registered source must be a reviewed
PRIMARY_CANDIDATE, with permission APPROVED and license VERIFIED. The current
audit snapshot must match the protected evidence metadata and supplied approval
reference. STEP 04 requires an explicit `expires_on` ISO date, known retention
policy, and `internal_analysis` scope. Expiry is inclusive through that date in
the host's local calendar. `commit` conservatively also requires `publication`
scope; it promotes a local dataset but does not upload it anywhere. Training
requires its own scope in a later step.

`expires_on` is an optional backward-compatible field on shared permission
decisions. Expired decisions grant no effective scopes. Existing historical
records without expiry still parse, but cannot authorize official imports.
No approval, expiry, or privacy review is created automatically for real data.

Prepare the source file in `data/private/`, with access limited to authorized
operators **before** copying it there. Check its existing ACL/mode: the importer
does not claim to secure a previously exposed input or its backups. Permission
checks precede opening input files or options files. Every supplied row must
identify the authorized source. Source mismatch aborts the complete build.

Keep a stable, randomly generated 32-byte fingerprint key in protected storage,
outside Git. Load it into the session without displaying it:

```powershell
$env:PFA_FINGERPRINT_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Persist that key in an approved secret store for repeatable versions. Do not
generate a new key for each import. Lost keys prevent reproducing source HMACs;
rotation produces different version IDs. Retain old keys only for the approved
retention period. The application never prints the key.

## Commands

Safe now, without external permissions:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset official schema
.\.venv\Scripts\python.exe -m pfa.cli dataset official smoke --fixture tests/fixtures/public_service_feedback_synthetic.csv
```

Smoke accepts only the checksum-bound bundled fixture. It uses isolated temporary
storage, an ephemeral key and an explicitly simulated synthetic review. All files
are removed afterward. It cannot relabel arbitrary files as synthetic or grant
external permissions. Its numbers are software-test metrics only.

After actual human permission verification, replace these placeholders:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset official import --source authorized_agency_export --input data/private/approved_export.csv --approval-ref APPROVAL_ID --mode preview
```

Preview creates `data/staging/VERSION_ID/` with sanitized `candidates.jsonl`,
`review_queue.json`, and `quality_report.json`. All unique candidates remain
PENDING_HUMAN_REVIEW, including records with no detected PII. Ambiguous text can
still be identifying: do not distribute staging files. Follow PRIVACY_REVIEW.md,
then use the protected review record's opaque reference:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset official import --source authorized_agency_export --input data/private/approved_export.csv --approval-ref APPROVAL_ID --mode commit --review-ref REVIEW_ID
.\.venv\Scripts\python.exe -m pfa.cli dataset official verify --dataset-version VERSION_ID
```

No `--force`, `--skip-permission`, or general synthetic import flag exists.
Exit codes: 0 completed operation, 2 invalid input/configuration/integrity failure,
3 blocked permission or review, 4 unavailable published version. Preview success
never means the data is approved for research or publication.

## Processing options and errors

`--options` accepts a reviewed JSON object validated by `ImportOptions`:

```json
{
  "max_input_bytes": 20971520,
  "max_records": 10000,
  "max_text_length": 20000,
  "near_duplicate_threshold": 0.85,
  "column_mapping": {},
  "pii_categories": ["email", "phone", "citizen_id", "personal_identifier", "address", "personal_name"]
}
```

Use non-sensitive configuration/column names. Disabling a detector is not evidence
of safety; human review still applies to every candidate. Defaults accommodate
2,000–5,000 records. Sizes, record counts, and text lengths are bounded. Input is
streamed; JSONL malformed records and recoverable row errors receive safe ordinal
diagnostics. Invalid encoding, ambiguous CSV structure, wrong source identity,
unsafe paths, unsupported formats, or changing input abort the build. No raw
record, matched identifier, original input path, or exception input is logged.

Deduplication prioritizes identical source records, repeated source feedback IDs,
then identical normalized sanitized content. The first unique record is retained
deterministically. Redaction can collapse different inputs to the same sanitized
text; reviewers must consider that limitation. Near duplicates use Jaccard overlap
of keyed Unicode word tokens, with at least three distinct tokens. They are pairs
for review, never automatic merges. The in-memory token index suits this bounded
workload; larger corpora need a disk-backed index. More than 10,000 candidate pairs
aborts the build instead of silently truncating statistics.

## Storage, versions, and recovery

- `data/private/`: operator-controlled inputs and protected review metadata.
- `data/staging/VERSION/`: candidate previews; never publish these files.
- `data/processed/VERSION/feedback.jsonl`: reviewed output only.
- `data/manifests/VERSION/`: manifest and quality report; presence marks commit.
- `data/synthetic/`: reserved synthetic storage; smoke uses this layout only in
  its isolated temporary root, never mixed with real output.

Version IDs are keyed digests of input HMAC, source, permission reference,
processing version, and options. Stable input/key/options give stable versions.
No raw-text SHA256 fingerprints or identity maps are persisted. Output checksums
use SHA256; source-file checksums use HMAC-SHA256 to resist guessing raw contents.
The source checksum is specifically HMAC-SHA256(key, `b"source-file\0" + file_bytes`).
Processing changes affecting outputs must increment PROCESSING_VERSION; never
rewrite an existing version to conceal a changed cleaning or screening policy.

Each application-created version/temp directory is restricted before any data
write: POSIX 0700 directories/0600 files, or Windows `icacls` owner and SYSTEM
full-control rules with inherited grants removed. Windows requires `whoami`,
`icacls`, and a filesystem supporting ACLs; failures block the build. Files inherit
the restricted Windows directory ACL. Administrators/SYSTEM can retain privileged
access; this is not encryption or protection from a compromised operator.
Parent directory names and preexisting inputs need operator-controlled security.

Publication uses temporary sibling directories and atomic directory renames.
The manifest directory is the final commit marker; handled failures roll back
uncommitted output. Readers require both directories. Published versions never
overwrite earlier versions. Repeated identical previews reuse matching immutable
staging files; conflicting content fails. A crash between directory renames can
leave an uncommitted orphan: restrict access, investigate, and remove it only after
checking that no manifest exists. Local storage assumes trusted maintainers and
no concurrent filesystem tampering. Manifests are not signed audit ledgers.

Apply the authorized retention policy to input, staging, processed data, keys,
reviews, backups, and snapshots. On expiry/revocation, stop use immediately,
inventory the exact versions, obtain the responsible reviewer's deletion decision,
and remove only checked paths within the intended storage root using PowerShell
`Remove-Item -LiteralPath`. Retain only permitted non-sensitive deletion/audit
metadata. Do not erase permission history to hide revocation. Ordinary deletion
does not guarantee secure erasure, including on SSDs, cloud copies, or backups.
