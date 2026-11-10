# Acquisition security and trust boundary

The acquisition module performs no network transfer, scraping, email or dataset
download. Source research uses public metadata only. Humans choose/authenticate
the sender and transfer channel, obtain legal permission and record actual evidence.

## Checks enforced

- Existing STEP 02/04 authorization runs before real input path inspection/content
  reads. Invalid source roles, incomplete license review, wrong scope, missing,
  expired or revoked approval and inconsistent audit/evidence fail closed.
- A protected pre-existing Handoff binds source, current approval, supplier/export
  references, human review, byte size and expected SHA256. A CLI reference alone
  never grants permission. Sensitive original evidence remains outside Git.
- Only local regular CSV/JSONL files are accepted. Existing `safe_path` rejects
  symlinks and Windows reparse points throughout the path; lexical `..` is rejected.
  Targets remain inside protected project storage. The incoming directory must be
  controlled by the custodian; this is not a sandbox against administrators racing
  filesystem changes. Do not use attacker-writable directories or public shares.
- Copying is streamed and bounded at 20 MiB. Transport inspection accepts UTF-8/BOM,
  unique CSV headers/JSON keys and at most 10,000 rows. No raw content, source
  filenames, matched identifiers or personal evidence is logged. STEP 04 handles
  semantic validation and privacy; receipt verification does not claim anonymity.
- Protected staging directories use Windows owner/SYSTEM ACLs or POSIX 0700;
  POSIX payloads and JSON receipts use 0600. A local exclusive writer lock,
  temporary protected bundle and rename provide atomic publication. Failed copies
  clean temporary payloads and release locks. Duplicate handoff/source exports and
  identical source payloads are rejected instead of silently overwritten.
- Verification checks current rights before payload reads, unchanged handoff/source
  snapshot, inventory, hashes, bytes and row count. Only aggregate counts and safe
  references are returned. All private payloads/evidence/receipts are Git-ignored.

## Limits and operations

SHA256 proves byte consistency with the expected digest, not sender authenticity.
Authenticate the checksum through an independently verified channel. Receipt
checksums are not digital signatures or a tamper-proof external journal. A trusted
coordinator/admin can replace storage and evidence; retain independently controlled
approval documents and audit their access. Application immutability is refusal to
overwrite, not WORM storage or protection from privileged modification.

Receipt directories contain quarantined potentially sensitive data. Keep them
restricted even after integrity verification. Windows deployment ACLs, transfers,
backups and account separation need human verification. Local encryption, secure
deletion, malware scanning and automatic retention enforcement are not implemented.
Use institution-approved controls where required before accepting data.

Follow the actual authorization's retention/deletion and incident/recall policy
for incoming files, receipts, STEP 04 staging and backups. Do not invent a retention
period or claim unlink is secure erasure. After a crash, stop and inspect stale locks
or inconsistent receipts as coordinator; never silently repair audit history.
Renewed permission/source metadata may invalidate old receipts; do not edit them to
substitute a new approval. Review a new export/handoff through the custodian.
## Contact and verification audit

Contact-event history binds existing human evidence and never grants data usage
permission. Verification audit binds the receipt, current permission and timestamp;
metadata-only status does not reread payloads. Reverify before ingestion.
Keep private acquisition directories outside unauthorized cloud synchronization,
telemetry, shared folders and backup destinations. Apply the authorized retention
policy to copies and backups as well as the primary receipt.

