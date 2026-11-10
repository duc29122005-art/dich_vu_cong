# Dataset quality profiling (STEP 05)

STEP 05 audits existing inputs; it does not annotate, train, acquire data, or
publish datasets. The master plan file was unavailable during implementation;
the STEP 05 request defines this scope. No external source has been approved.

## Running an audit

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset profile --source synthetic_demo
.\.venv\Scripts\python.exe -m pfa.cli dataset preprocess --source synthetic_demo
.\.venv\Scripts\python.exe -m pfa.cli dataset audit-privacy --source synthetic_demo
```

All three commands run the same audit and create an immutable protected bundle
under `reports/dataset/q_<SHA256>/`: `quality_report.json`, `summary.md`, and
`audit.json`. Repeating identical inputs, policy, versions and fingerprint key
reuses identical reports after integrity checking. Existing bundles are never
overwritten. Writes use a protected temporary directory and atomic directory
rename. Reports are excluded from Git. Restrictive ACLs/permissions are not
encryption; administrators and backups require their own controls.

`synthetic_demo` resolves only the checksum-bound project CSV fixture. There is
no arbitrary input path option. Its results remain SYNTHETIC, cannot authorize
research publication, and are not research quality measurements.

After actual STEP 02 approval and STEP 04 import, human review and publication:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset profile --source authorized_agency_export --dataset-version VERSION_ID
```

The same version option works for `preprocess` and `audit-privacy`. Permission
validation precedes reading manifests, data and optional policy files. The real
route requires current authorization, matching source identity, protected
`PFA_FINGERPRINT_KEY`, and verified STEP 04 published storage and review evidence.
It rechecks integrity and permission after profiling. A benchmark is never
reclassified as citizen feedback. The reusable report model supports BENCHMARK;
these commands currently require the canonical STEP 04 contract for real data.

## Metrics and denominators

- Record count includes unparseable rows; valid plus invalid equals record count.
- Missing values and missing field counts cover parseable objects, including
  invalid records. Unparseable rows are reported separately, not assigned
  invented missing values. Gate fractions use total record count.
- Raw content lengths cover string content, including invalid/empty text.
  Distribution includes minimum, maximum, mean and deterministic lower-rank
  p50/p95. Short and long counts use strict comparisons to configured limits.
- Unicode metrics count non-NFC records, invalid UTF-8 Unicode, replacement
  characters, unsafe controls and records containing Latin diacritics compatible
  with Vietnamese. This does not establish Vietnamese language identity.
- Mixed-language candidates use English word cues and non-Latin scripts.
  Uncertain-language candidates lack diacritic cues. These heuristics miss cases
  and produce false positives; no validated language detector is installed.
- Timestamp counts distinguish missing, invalid, known offset, configured zone,
  ambiguous timezone and invalid local time. Date bounds include only timestamps
  with known zones and are expressed as UTC dates. No missing dates are inferred.
- Agency/domain/status distributions use opaque HMAC buckets plus `MISSING`.
  Raw labels are deliberately excluded because free-form metadata can carry PII.
- Exact duplicate diagnostics use valid records. Categories overlap; their
  counts must not be summed. Near duplicates are candidates for human review.
- Privacy counts include parseable records regardless of schema validity and
  aggregate category matches across content, identifiers and textual metadata.

The known CSV yields 10 input records, 8 valid, 2 invalid, 3 exact duplicates,
5 unique valid records, 1 near-duplicate pair, and 3 privacy-flagged records.
Agency is missing in 10 records, domain in 9, created_at in 7. Created_at has
2 aware timestamps and 1 invalid value. These are computed software-fixture
statistics; STEP 04 counts missingness only among valid rows and therefore has
a different denominator.

## Operational quality policy

Use `--config PATH` with a JSON object of `QualityConfig` fields. Unknown fields,
coerced types, invalid timezones, out-of-range values and inconsistent thresholds
fail validation. Example:

```json
{
  "max_invalid_fraction": 0.1,
  "missingness_warn_fraction": 0.5,
  "duplicate_warn_fraction": 0.2,
  "duplicate_fail_fraction": 0.5,
  "known_timezone": "+07:00"
}
```

Defaults are engineering review triggers, not scientifically validated cutoffs:

| Check | Default and rationale |
|---|---|
| Invalid records | Warn when present; fail above 25%, preventing heavily broken builds |
| Missing created_at/agency/domain/status | Warn above 50%; failure disabled because metadata is optional |
| Duplicate fraction among valid records | Warn above 20%, fail above 50%; prompt sampling/lineage review |
| Text length | Flag below 10 or above 1,000 characters; reject above 20,000 |
| Input limits | 10,000 records, 20 MiB, 10,000 near pairs; bounded research-scale operation |
| Invalid/ambiguous timestamps | Warn; invalid schema also counts as processing failure |
| Unsafe controls left by disabled cleanup | Fail |
| Unresolved privacy screening | Warn for synthetic/benchmark, mandatory fail for research |
| Research provenance/review/schema | Mandatory fail when manifest, human review or valid records are absent |
| Research permission | BLOCKED_PERMISSION regardless of numerical thresholds |

Comparisons are strictly greater than thresholds. Missingness failure can be
enabled with `missingness_fail_fraction`; warning must not exceed failure.
Near-pair overflow fails without silently truncating diagnostics. No warnings
remove records, and no near matches are merged. New privacy findings on previously
reviewed research inputs require renewed human review; an old approval is not
treated as clearance for newly detected risks.

PASS means configured technical checks passed. WARN means review is needed.
FAIL means a mandatory/configured check failed. BLOCKED_PERMISSION means lawful
scope has not been established. NOT_AVAILABLE means no dataset/records are
available. CLI exits: PASS/WARN 0, FAIL 2, BLOCKED_PERMISSION 3, NOT_AVAILABLE 4.
Malformed configuration or audit metadata returns 2; permission denial returns 3.
None of these statuses is a legal approval or proof of anonymity. Publication
eligibility in a report is advisory; only STEP 04 can publish records.

## STEP 06 prerequisites

Resolve source permissions, retention and licensing, validate actual data,
complete privacy and duplicate review, and acknowledge quality exceptions before
research annotation. Preserve source version, manifest checksum, policy hash,
algorithm versions and keyed lineage. Until then use synthetic fixtures only.
