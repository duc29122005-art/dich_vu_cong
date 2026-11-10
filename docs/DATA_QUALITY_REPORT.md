# Quality report interpretation

Reports describe observed processing, not representative sampling, label quality,
model accuracy, or proof of anonymization. Synthetic reports use provenance
SYNTHETIC and metrics usage SOFTWARE_TEST_ONLY; they are not research results.

Each successful preview/build records:

| Field | Interpretation |
|---|---|
| dataset_version, source_id | Immutable build and registered provenance |
| input_records | Parsed CSV logical records or JSONL lines; excludes CSV header |
| valid_records / invalid_records | Canonical validation result, before deduplication |
| duplicate_count / exact_duplicate_count | Removed exact duplicates, counted once each |
| duplicate_reasons | Mutually exclusive source-record, ID, or sanitized-content priority |
| unique_record_count | Valid records minus exact duplicates |
| suspected_duplicate_count | Near-duplicate pairs for human consideration; not merged records |
| privacy_flagged_count | Valid records with detector matches, including exact duplicates |
| pii_detections | Match counts by category, including duplicate records |
| human_review_pending_count | All unique candidates in preview; zero only after complete review |
| published_count | Zero in preview; accepted unique candidates in committed output |
| human_review_rejected_count | Explicit rejections on commit |
| missing_values | Null counts per optional/nullable field across valid pre-dedup records |
| text_length_distribution | Min/max/mean and discrete lower p50/p95 over unique sanitized candidates |
| date_coverage | Min/max supplied creation calendar dates over unique candidates, or null |
| source_checksum | HMAC-SHA256 of original file bytes, requiring the protected key to reproduce |
| output_checksum | SHA256 of candidate file in preview or reviewed output on commit |
| output_kind | STAGED_CANDIDATES or REVIEWED_DATASET |
| processing_version, options | Processing contract and reviewed non-sensitive configuration |
| permission_reference | Current human decision reference; null for isolated synthetic smoke |
| provenance, storage_protection | Real/synthetic distinction and applied storage mechanism |

All unique candidates, including those with missing dates, enter text-length
statistics. Dates are not imputed; day-level coverage does not prove temporal
representativeness. A missing-value key absent from the sparse counter means zero
observed nulls for that field. No feedback text, original IDs, matched values,
identity mapping, or input path is included. Do not add these to reports.

Accounting invariants:

```text
input_records = valid_records + invalid_records
valid_records = unique_record_count + duplicate_count
published_count + human_review_rejected_count = unique_record_count  (commit)
```

Fatal encoding/structure/permission/storage errors abort the build; no successful
quality report is published for partially processed input. Recoverable invalid
rows are excluded with safe row ordinals and generic error codes in the protected
review queue. Human review must acknowledge those exclusions before commit.

The manifest binds the quality and output checksums, review checksum, source HMAC,
permission reference, schema processing version, configuration, timestamp,
provenance and actual published count. Verification checks file inventory,
checksums, canonical schema, approved record membership and report accounting.
Current permission and expiry are rechecked before reading real processed rows.
Verification is not a declaration that a real research dataset is scientifically
validated or ready for modeling.
