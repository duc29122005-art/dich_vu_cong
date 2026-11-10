# Annotation data contract — proposed v1

This contract supports independent records, not a pilot or a gold dataset.
Taxonomy approval is PENDING. No agreement or scientific validity is claimed.
`pfa.annotation.schema` uses the existing strict Pydantic base, rejects unknown
fields and preserves reasoning exactly. It never silently repairs human labels.

## Columns

Every CSV header/JSONL object has these 17 columns. CSV column order may vary;
metadata records the canonical order. JSONL contains all keys, using null for
missing values. CSV uses empty cells for null and exactly `true`/`false` for booleans.

| Field | Contract |
|---|---|
| feedback_id | Non-identifying STEP 04-style `f_` plus 32 lowercase hex digits; membership checked |
| dataset_version | Immutable `of_` plus 32 lowercase hex digits |
| taxonomy_version | Exactly `1.0.0` |
| taxonomy_checksum | Frozen SHA256 of the canonical taxonomy |
| source_id | Source registry identity, matched to submission context |
| dataset_type | SYNTHETIC or RESEARCH; never inferred from a filename |
| annotator_id | Pseudonym `ann_` plus 16 lowercase random hex digits; no names/email |
| topic_label | Exactly one of eight codes or null |
| sentiment_label | negative / neutral / positive or null |
| severity_label | low / medium / high; unknown is a review state; null allowed for incomplete review |
| multiple_issues | Boolean; does not introduce a second topic |
| annotation_status | DRAFT / SUBMITTED / REQUIRES_REVIEW / OUT_OF_SCOPE / UNLABELABLE |
| topic_justification | Required for a provided topic label |
| sentiment_justification | Required for a provided sentiment label |
| severity_justification | Required for a provided severity value, including unknown |
| review_reason | Required for review/exclusion states; absent on complete SUBMITTED records |
| annotated_at | ISO datetime with explicit timezone, not in the future |

Reasons are nonblank, single-line, at most 2,000 characters. Do not copy sensitive
source text, identifiers or names into reasons. Existing privacy audit patterns
reject detected PII/context candidates; this conservative check can flag harmless
text and cannot detect every sensitive detail. Rewrite a safe abstract explanation
after human review; the validator itself does not alter input.

## State consistency

- Blank templates have no rows. `BlankAnnotation` permits missing field values
  for structural checks; invalid populated labels/version/timestamps still fail.
- DRAFT is a workflow option but strict submission rejects it.
- SUBMITTED requires all three supervised labels, their separate justifications,
  identity/provenance/timestamp, and no unresolved review reason. It means contract
  completion, not human approval, agreement, gold status or permission to train.
- REQUIRES_REVIEW requires an explicit review reason. Each supplied label requires
  its own justification; missing labels have no invented justification. Unknown
  severity requires both severity justification and review reason. A partial
  record can be valid for review but is not a complete supervised record.
- OUT_OF_SCOPE and UNLABELABLE require a reason, null labels and justifications,
  and `multiple_issues=false`. Neither is represented as topic `other`.

The record key is `(dataset_version, feedback_id, taxonomy_version, annotator_id)`.
Duplicate keys fail within a submission. Distinct annotators retain separate
records for the same feedback. Validation is read-only and does not upsert or
overwrite any annotation. Cross-file revisions/assignment management are future
STEP 07 workflow responsibilities; do not concatenate duplicate revisions as
independent judgments.

## Required metadata sidecar

Each input has `<filename>.metadata.json` (for example
`annotation_template.csv.metadata.json`). It contains `format_version=annotation-1`,
`purpose`, taxonomy version/checksum, dataset type/source/version, canonical
`columns`, and `human_gold=false`. Unknown keys and mismatched types fail.
The generated template uses `purpose=BLANK_TEMPLATE`, `dataset_type=TEMPLATE`,
null source/version, no fake records and no identity inventory.

For actual submissions, an authorized coordinator prepares
`purpose=ANNOTATION_SUBMISSION`, matching source/version and SYNTHETIC/RESEARCH
type. Never declare gold status or use a sidecar as permission evidence.
RESEARCH context is checked against current STEP 02 approval and verified,
human-reviewed STEP 04 storage before annotation contents are read, even with
`--schema-only`. Existing STEP 04 verification requires publication scope for
published storage; STEP 06 does not weaken that requirement or grant new scope.
Source, provenance and record membership must match; synthetic storage cannot
be reclassified as research by editing metadata.
Validation binds the exact manifest checksum and membership inventory, rechecking
both with current permissions before returning. A concurrent manifest change fails.

SYNTHETIC context is restricted to the existing checksum-bound bundled fixture,
not arbitrary input data. `synthetic_inventory()` derives deterministic software
fixture version/IDs using the existing fingerprint helper and separate public
synthetic key; invalid and privacy-flagged source rows are excluded. These IDs
describe software fixtures, not a real published dataset or a gold annotation.
Tests construct all annotation examples in temporary directories.

## Validation and diagnostics

CSV supports UTF-8 and UTF-8 BOM; JSONL supports UTF-8. Limits are 20 MiB and
10,000 rows, matching current research scale. Unsupported formats, missing/extra
columns, malformed CSV, invalid encoding, taxonomy edits and missing sidecars fail.
Malformed JSONL rows fail individually. Empty submissions fail strict validation.
Safe diagnostics contain counts, row ordinals, allowlisted field names and fixed
rule codes (such as LABEL_JUSTIFICATION_MISMATCH or UNSAFE_REASON), never original text,
IDs, reasoning, matched PII, unexpected key names or annotation file paths.
Reports show at most 100 row errors and count omitted errors; none are silently
accepted. Validation output goes to stdout and does not export annotation rows.

Exit codes follow the existing CLI: 0 valid, 2 invalid/incomplete/schema/integrity
failure, 3 permission failure. Schema-only PASS does not validate complete labels,
measure correctness or establish research readiness.
