# Human taxonomy approval

Taxonomy v1.0.0 remains **PENDING** human approval. STEP 07A implements the
checkpoint, not an approval. Its exact SHA256 is
`500a61fd8f8fe49d31f3ec7eca955ebfe1856bb235e04ffc62d6f44f16f5af02`.
Approval also binds the actual SHA256 of `docs/ANNOTATION_GUIDELINES.md`.

## Recording a genuine decision

1. The research owner or domain reviewer reads the taxonomy, handbook, severity
   rubric and pilot protocol. Keep actual identity, signatures and supporting
   documents in protected evidence storage outside Git.
2. As the trusted coordinator, create the protected request directory:

   ```powershell
   .\.venv\Scripts\python.exe -c "from pathlib import Path; from pfa.annotation.pilot_store import private_directory; private_directory(Path('data/private/annotation_pilots/requests'))"
   Get-FileHash -Algorithm SHA256 docs/ANNOTATION_GUIDELINES.md
   ```

3. After authentic human verification, create `<decision_ref>.json` there using
   the strict `pfa.annotation.approval.TaxonomyDecision` fields:

   | Field | Required value |
   |---|---|
   | decision_ref | Unique safe identifier matching filename |
   | taxonomy_version | `1.0.0` |
   | taxonomy_checksum | Exact checksum above |
   | handbook_checksum | Actual reviewed handbook SHA256 |
   | reviewer_id | Non-sensitive actual reviewer reference |
   | reviewer_role | `research_owner` or `domain_reviewer` |
   | reviewed_at | Actual nonfuture ISO timestamp with timezone |
   | decision | `APPROVED`, `REJECTED` or `SUPERSEDED` |
   | evidence_reference | Existing protected evidence reference |
   | human_verified | `true` only after genuine verification |

4. Record the existing request:

   ```powershell
   .\.venv\Scripts\python.exe -m pfa.cli annotation taxonomy record --decision-ref ACTUAL_DECISION_REF
   ```

A command reference or JSON boolean does not authenticate a person or establish
legal permission. The trusted coordinator must verify evidence and identity.
No approval requests were generated for the actual project by STEP 07A.

## Audit and changes

Immutable checksum inventories under `data/private/annotation_pilots/taxonomy_history/`
form a chronological hash chain. Sequence gaps, altered requests, changed handbook,
modified taxonomy and repeated references fail closed. Preserve requests unchanged.
Append a new decision to reject or supersede; never edit prior decisions.

Only the latest APPROVED checkpoint permits sampling. Pilots bind that exact
checkpoint, so a replacement checkpoint requires a new pilot. Changed label meaning
requires a new taxonomy version and explicit migration/reannotation work. No
automatic migration exists. Source permission and privacy approval remain separate.

Checksums detect corruption, not malicious administrators replacing all files.
Protect audit storage and retain independently controlled evidence.
