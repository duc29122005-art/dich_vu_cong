# Canonical citizen feedback schema

STEP 04 defines a data contract, not topic, sentiment, or severity labels.
`dataset official schema` prints the authoritative Pydantic JSON Schema.

| Field | Required | Type and meaning |
|---|---|---|
| feedback_id | Yes | Nonblank string, at most 256 characters; supplied source identifier |
| content | Yes | Nonblank Vietnamese Unicode text |
| created_at | Yes | ISO datetime or null; a missing column is not equivalent to null |
| source_id | Yes | Registered source ID, exactly matching the authorized import source |
| domain | No | String or null |
| agency | No | String or null |
| channel | No | String or null |
| processing_status | No | String or null |
| response_date | No | ISO datetime or null |

CSV blank optional values and blank timestamps become null. JSONL uses JSON null.
No missing agency, date, channel, status, or label is inferred. Datetimes require
a time component; invalid dates and numeric epoch values are rejected. Supplied
timezones are retained. Naive datetimes remain naive; no timezone is invented.

Canonical models reject extra fields. Source readers select mapped canonical
columns and ignore unmapped source columns; those values never enter outputs.
Mapping is canonical name to input column name, including Vietnamese headers:

```json
{"column_mapping": {"feedback_id": "MaPhanAnh", "content": "Nội dung"}}
```

Put this object in a reviewed, non-sensitive options JSON file and pass `--options`.
Effective mapped column names must be unique. Required columns/fields must exist.
Duplicate CSV headers fail the build; duplicate JSON keys invalidate that row.

Content is normalized to NFC, unsafe control characters are removed, whitespace
is collapsed, and leading/trailing whitespace is trimmed. Vietnamese accents,
negation, and punctuation remain. Default maximum text length is 20,000 Unicode
characters before normalization. The same screening applies to optional text
metadata, which must not carry unreviewed PII into processed records.

Input IDs are used transiently for validation and keyed duplicate detection.
Output `feedback_id` is a dataset-specific HMAC-derived pseudonym. No source-ID
mapping is written. `source_id` remains as source-level provenance. Source checksum,
permission reference, processing configuration and version are stored separately
in the quality report and manifest. A pseudonym is not proof of anonymization.

The bundled CSV is SYNTHETIC, with `source_id=synthetic_fixture`; it contains no
real citizen records. Its examples are not a research dataset or annotation set.
