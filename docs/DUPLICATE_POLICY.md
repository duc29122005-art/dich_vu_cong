# Duplicate audit and lineage

STEP 05 reuses STEP 04's keyed fingerprints and token-overlap candidate matcher.
It does not delete records, merge near duplicates, or infer same-case membership
from shared topics. The canonical schema has no explicit case/thread field;
same-case/thread analysis reports NOT_AVAILABLE rather than inventing links.

Valid records are compared independently for exact source-record equality,
source feedback ID equality, normalized content equality and sanitized content
equality. The output category `feedback_id` identifies source feedback ID matches.
Categories overlap. The exact duplicate total counts a
row once if its source record, feedback ID or sanitized content appeared before.
Normalized-text groups are reported separately. Invalid rows remain in validation
counts and are excluded from duplicate groups.

Near matches use case-folded sanitized word-token Jaccard similarity, default
0.85, with at least three distinct tokens. Exact duplicates are connected first;
near candidates are generated between retained unique representatives. This is
a lexical heuristic; synonymous or very short duplicates can be missed. Candidate
pairs require human review and never trigger automatic record deletion.

`audit.json` contains overlapping exact groups, near candidate pairs, per-row
keyed references/ordinals and connected group assignments, including singletons.
These conservative assignments can support group-aware splitting in STEP 08
after human adjudication. Transitive links can join rows that do not directly
match; a group is a review unit, not a verified common case. No split is created
in STEP 05. Review or invalidate candidates before using them for research.

Raw identifiers, raw text, token dictionaries and unsalted raw-text hashes are
never persisted. Real records use the external secret `PFA_FINGERPRINT_KEY` with
domain-separated HMAC-SHA256; keep the key outside Git. The bundled fixture uses
a separate public synthetic-only key and gains no real-data confidentiality
claim. Group assignments are deterministic for the same dataset version, key,
policy and input order. Preserve these versions and audit artifacts for lineage.

Indexes remain in memory for bounded research-scale inputs (default 10,000
records). The maximum candidate-pair limit fails rather than hiding pairs;
use an approved disk index if larger corpora require it. Similarity thresholds
are operational defaults, not scientifically validated duplicate decisions.
