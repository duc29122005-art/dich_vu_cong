# Conservative preprocessing audit

STEP 05 reuses `pfa.data.preprocessing`; default `normalize_text` behavior stays
compatible with STEP 04. Transformation version `conservative-1` covers NFC
normalization, unsafe control removal, whitespace collapse and trimming. UTF-8
encoding, nonempty text and maximum length are validated. Lone Unicode surrogates
are rejected. Accents, negation (không, chưa, chẳng, chưa từng), punctuation and
classification-relevant metadata are preserved. No translation, spelling repair,
topic, sentiment, severity or missing metadata inference occurs.

`QualityConfig` can disable individual normalization operations for comparison.
Security screening always performs its own conservative normalization regardless
of those switches. Remaining unsafe controls fail quality gates. The audit records
change counts and warnings, never before/after text. Length distributions refer to
source strings; duplicate analysis uses normalized and sanitized text separately.

ISO timestamps reuse the canonical parser. A known offset is normalized to UTC;
naive timestamps remain timezone-ambiguous unless an explicitly configured zone
is supplied. UTC and fixed offsets work without new dependencies. IANA zones
require an installed timezone database; unsupported zones fail configuration.
DST gaps and ambiguous folds are rejected instead of guessing. Timestamp status
is recorded per field, including unchanged missing/ambiguous values.

`audit.json` binds per-row ordinal, keyed record reference, fixed change/warning
codes, transformation version and processing configuration hash. The hash binds
all policy fields plus preprocessing, privacy and profiler algorithm versions.
Source manifest version/checksum in the quality report preserves provenance.
Record references depend on dataset version and protected fingerprint key;
changing either changes group references and requires new lineage.

The CLI `preprocess` command creates a transformation summary and audit only.
It never overwrites input files, emits a second unreviewed dataset, or publishes
records. STEP 04 remains the controlled path for sanitized datasets and actual
human review. Source retention/deletion follows the existing authorized policy
in DATA_INGESTION.md; these reports do not extend retention permission.
