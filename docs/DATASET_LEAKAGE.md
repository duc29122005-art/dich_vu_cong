# Frozen dataset leakage checks

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset check-leakage --version service_feedback_v1
```

The coordinator check revalidates current governance, manifest schema/configuration,
all file checksums, taxonomy mappings, test membership and source/gold references.
It reads partitions, validates canonical rows, checks recorded membership and
recomputes construction, split assignments and diagnostics. Missing/corrupt files
never yield PASS. No check changes the frozen version.

Critical failures include cross-split record IDs, duplicate groups, reviewed
case/thread/source/near relations, exact normalized text, provenance mismatch,
unapproved pilot holdout membership and inconsistent assignments. Build-time
union-find prevents known linked groups from crossing boundaries. An overlap is
a build/verification failure, never repaired by silently deleting rows.

Potential near-duplicates use shared three-word shingles to generate candidate
pairs, followed by token-set Jaccard similarity. Matches above `near_threshold`
are WARN and require human review; they are not proof of duplicate identity.
The detector is lexical and incomplete: paraphrases, very short texts and
different word forms can evade it. Topic similarity is not enough to merge records.
`max_candidate_pairs` bounds comparisons; exceeding it fails explicitly rather
than reporting incomplete PASS. Review large/common-template corpora and choose
a documented policy before building; the maximum supported cap is 1,000,000 pairs.

Known reviewed near-duplicates should be supplied as keyed relations before the
build so they remain together. Uncertain cross-split candidates remain visible in
the preview/card and require human judgment. Approved warnings never bypass source,
privacy, taxonomy or pilot gates. Aggregate reports contain counts/categories,
not raw text, private IDs, matched PII or original case/thread numbers.

Statuses: PASS means implemented critical/heuristic checks found no issues, not a
proof that all possible leakage is absent. WARN signals reviewable quality/risk
findings. FAIL blocks integrity/leakage publication. BLOCKED_PERMISSION,
BLOCKED_TAXONOMY and BLOCKED_PILOT identify mandatory governance failures;
NOT_AVAILABLE identifies missing artifacts. CLI exits are 0 for PASS/WARN,
2 for invalid data/integrity, 3 for blocked governance, and 4 for unavailable data.
