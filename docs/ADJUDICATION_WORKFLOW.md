# Human adjudication

The designated adjudicator explicitly reviews **every** pilot record, including
agreements. No majority rule or model prediction determines gold. Preserve both
original independent submissions; agreement always compares those originals.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation adjudicate --pilot pilot_v1
```

Without a decision reference, this creates protected `review.json` for the
designated account: sanitized selected text, independent labels/reasons,
disagreements and submission checksums. It refuses overwrite. If submissions
change after export, document a new pilot/review cycle; stale references cannot
finalize. Aggregate reports never contain feedback text.

## Explicit decisions

Use the approved Vietnamese handbook. Resolve tasks independently and justify
each decision. Unknown severity retains an explicit reason and REQUIRES_REVIEW.
OUT_OF_SCOPE/UNLABELABLE remain exclusions. New privacy concerns return to human
privacy review; never force training labels from insufficient evidence.

After checking genuine evidence, the coordinator stores a protected request
conforming to `pfa.annotation.pilot.AdjudicationDecision`:

- `decision_ref`, `pilot_id`, exact definition `pilot_checksum`;
- `submission_checksums`: exact A/B bundle checksums, in order;
- `adjudicator_id`: designated plan pseudonym;
- actual timezone-aware `reviewed_at`, protected `evidence_reference`;
- `human_verified: true`, `approve_final: true` only after actual review;
- `final_records`: one strict STEP 06 Annotation per selected ID, using the
  adjudicator pseudonym, original provenance and exact taxonomy checksum.

Real adjudication and human review must follow the correction deadline. Final
annotation timestamps cannot exceed the decision time. The coordinator verifies
authentic reviewer identity/evidence; JSON booleans do not authenticate humans.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation adjudicate --pilot pilot_v1 --decision-ref ACTUAL_FINAL_DECISION
.\.venv\Scripts\python.exe -m pfa.cli annotation verify-pilot --pilot pilot_v1
```

## Finalization

The atomic immutable `adjudicated/` bundle includes decision snapshot, manifest
and resolved records. Only SUBMITTED final decisions become gold candidates.
Review/unknown rows stay unresolved; explicit exclusions remain counted.
Unresolved rows prevent research pilot completion. A completed 200-record pilot
can have fewer than 200 gold records because of documented exclusions; do not
silently add replacements.

Final manifests bind pilot, taxonomy, agreement version and original submissions.
Finalization locks imports and refuses overwrite. Corrections need a separately
reviewed cycle. Verification checks current permissions, request snapshots,
checksums, membership, provenance and counts. External release requires its own
source authorization and retention conditions.

Synthetic adjudication always has `human_gold: false`, `gold_count: 0`. Resolved
synthetic fixtures cannot be promoted into research gold.
