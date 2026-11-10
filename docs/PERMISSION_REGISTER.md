# Permission register and controlled workflow

## Current register

No verified human decisions exist. `configs/permission_evidence.json` contains an
empty decision list; `configs/permission_history.jsonl` is an empty audit journal.
No approval is implied by source inclusion or a command returning successfully.

| Source | Confirmed local action | Blocked pending verification |
|---|---|---|
| uit_vsfc | Inspect registered metadata offline | Download, processing, training, internal analysis, publication |
| public_service_official | Draft permission request | Scraping, download, processing, training, analysis, publication |
| authorized_agency_export | Request documented agency approval | Transfer, processing, training, analysis, publication |
| neu_esc | Record reported gated status | Access, download, processing, training, analysis, publication |
| vn_mps_qa | Record intended reference role | Retrieval, reference processing, training, analysis, publication |
| sipas | Record aggregate context role | Retrieval, processing, training, analysis, publication |
| synthetic_demo | Design isolated invented test fixtures | Materialized dataset use/distribution without scoped review |

Confirmed facts here describe **repository state**, not externally verified source
terms. The brief's roles, gated status, and URLs are unverified source assertions.
License and source owner remain UNKNOWN for all entries. No real records were
accessed. No external evidence documents were obtained.

## Human decision workflow

1. A responsible human verifies the rights-holder's authority, license or written
   authorization, privacy conditions, usage scopes, and retention/deletion terms.
   Keep original documents in access-controlled storage outside this repository.
2. Assign an opaque non-sensitive document ID (lowercase letters, digits,
   underscores; first character a letter). Do not store document contents, private
   URLs, tokens, signatures, citizen data, or private storage paths in Git.
3. Through normal repository review, add a record to the `decisions` list in
   `configs/permission_evidence.json`. Use a responsible reviewer's approved public
   identifier. Do not invent reviewer identities or mark an unreviewed record true.
   The following field outline is **not an approval record**:

```text
approval_ref: unique opaque decision ID
source_id: exact registered source ID
reviewer: responsible human's approved public identifier
evidence_reference: opaque ID for existing protected evidence
decision_date: actual verification date, YYYY-MM-DD, never future
decision: APPROVED, DENIED, or REVOKED
allowed_scope: subset of software_tests, training, internal_analysis, publication
human_verified: true only after human verification
license_verified: boolean confirming rights for the stated scope
privacy_verified: boolean confirming privacy review for the stated scope
retention_policy: non-sensitive summary of actual approved terms
expires_on: optional YYYY-MM-DD expiry; required for STEP 04 official imports
```

4. For APPROVED, license/privacy verification must both be true; scope must be
   nonempty and retention known. DENIED/REVOKED must have empty scope. Missing
   fields, blank evidence IDs, unknown reviewer, duplicate references, invalid
   types, and future dates fail validation. The registry's UNKNOWN license can
   remain as historical unverified metadata: the effective scope requires the
   separate scope-specific human verification record, which the CLI identifies.
5. After review, record the exact reference:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset approve --source SOURCE_ID --approval-ref REF
.\.venv\Scripts\python.exe -m pfa.cli dataset assess --source SOURCE_ID
```

The historically named `approve` command records the supplied human decision,
including DENIED or REVOKED. It cannot verify document authenticity, contact a
rights-holder, or independently establish legal authorization. A reference alone
does nothing unless its fully validated evidence record already exists.

6. Record changes with a new decision ID. Never edit/delete earlier evidence or
   journal entries. Record revocation immediately with empty scope. Last appended
   decision for a source governs, and dates cannot move backward. Keep all old
   evidence records for audit. Changes to the active evidence snapshot fail closed.
   Registry DENIED/REVOKED is an additional hard stop.
7. Review and commit non-sensitive metadata and audit changes together. Commit
   history provides review provenance; the application journal is not a signed or
   tamper-proof ledger. Restrict write access to trusted maintainers. Software
   cannot prove that a `human_verified` assertion is truthful.

## Operational behavior

`sources` shows declared permission state and effective scopes separately.
`assess` shows recommendation, scores, rationales, and blockers. Exit codes: 0
successful command (not necessarily approved), 2 invalid arguments/source/metadata
or unavailable files, 3 permission failure. Error output excludes input values
and evidence contents. No evidence is logged.

The journal uses a local exclusive writer lock and flushed/fsynced append. A
second writer fails safely. If a process crashes, inspect the journal for a partial
last entry and stale lock under human review before recovery. Do not delete audit
history or blindly retry a decision. Missing/corrupt evidence or history blocks
permission evaluation. This local workflow needs transactional storage and stronger
audit controls before multi-host deployment. Every later dataset access path must
call `require_access` before acquisition or processing; no downloader exists yet.

When no real source is approved, use only SYNTHETIC offline unit-test fixtures.
Do not acquire real feedback or report research results from synthetic examples.
