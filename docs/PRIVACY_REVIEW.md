# Privacy screening and human clearance

Regex screening detects candidates, not proven PII and not complete anonymity.
Structured email, phone, 12-digit citizen-ID and labeled identifier candidates
receive placeholders such as `[REDACTED_EMAIL]`, `[REDACTED_PHONE]`,
`[REDACTED_CITIZEN_ID]`, and `[REDACTED_PERSONAL_IDENTIFIER]`. Only categories and
match counts are recorded. Explicit name/address markers flag ambiguity; those
free-form values can remain in protected staging for human review.

Important limits: unmarked Vietnamese personal names, indirect identifiers,
free-form addresses, unusual number formats, encoded/obfuscated text, attachments,
and combinations of metadata can escape detection. Administrative numbers may
be false positives. Overlapping address markers can produce multiple matches in
one record; counts are pattern matches, not people. NFC normalization and removal
of invisible controls improve some detections but are not a privacy guarantee.

Every unique candidate requires a human decision, even if no pattern matched.
Inspect the protected candidates, optional metadata, near-duplicate pairs,
invalid-row exclusions, and quality report. Reject unsafe or ambiguous records
unless actual human verification establishes safety. If text needs further
redaction, correct the authorized input in protected storage and build a new
version. Never edit a reviewed immutable preview or restore redacted identifiers
into processed data merely to improve NLP performance.

## Protected review record

After actual human verification, create
`data/private/reviews/REVIEW_ID.json`. REVIEW_ID, reviewer and evidence reference
are opaque lowercase identifiers. Store supporting documents separately in
protected storage; do not put private URLs, signatures, PII, or free-form sensitive
comments into review metadata. There is no automatic real-review generator.

The record requires:

```text
dataset_version: exact preview version
source_id: exact registered source ID
source_checksum: exact preview HMAC
candidates_checksum: checksum returned by preview
queue_checksum: checksum returned by preview
permission_reference: current human permission reference
reviewer: responsible human's approved non-sensitive identifier
evidence_reference: opaque reference to existing protected review evidence
reviewed_at: actual ISO datetime with timezone, not in the future
provenance: REAL_EXTERNAL
quality_accepted: true only after acknowledging exclusions and quality limitations
decisions: one entry for every unique candidate
  feedback_id: generated candidate ID, never original source ID
  action: APPROVE or REJECT
  privacy_cleared: true required for APPROVE
```

Copy only the non-sensitive binding values from preview. Each candidate must
appear exactly once; omitted, duplicated, mismatched, future-dated or unbound
decisions fail closed. Do not invent a reviewer or tick clearance without
reviewing the candidate. Rejected records stay out of the processed dataset.

The CLI cannot establish that a human assertion is truthful or that a protected
document is authentic. Restrict who can write reviews and permission metadata;
use the organization's actual review process. Review checksum and membership are
checked again during dataset verification. Changed or deleted review records
invalidate verification. Keep non-sensitive review provenance only as permitted
by retention policy; original source identifiers are never mapped into it.

Synthetic smoke review is explicitly SIMULATED_SYNTHETIC and has no legal or
research authority. It rejects the fixture's ambiguous candidate and demonstrates
the pipeline only. It cannot approve any real source.
