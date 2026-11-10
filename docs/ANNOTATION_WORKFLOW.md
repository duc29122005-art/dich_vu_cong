# Proposed annotation workflow and taxonomy versioning

STEP 06 creates a proposed instrument, handbook, contracts and offline validation.
It performs no pilot, assignment, adjudication, annotation agreement measurement,
training or data acquisition. Real data remains BLOCKED_PERMISSION and research
annotation remains NOT_STARTED. The master plan was not present; the STEP 06
requirements define this implementation.

## Offline commands

Run from the repository root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation taxonomy show
.\.venv\Scripts\python.exe -m pfa.cli annotation template --output data/fixtures/annotation_template.csv
.\.venv\Scripts\python.exe -m pfa.cli annotation validate --input data/fixtures/annotation_template.csv --schema-only
# Expected rejection: a blank template is not a submitted annotation.
.\.venv\Scripts\python.exe -m pfa.cli annotation validate --input data/fixtures/annotation_template.csv
```

The template has headers only, plus a mandatory metadata sidecar. CSV and JSONL
templates are supported. Generation refuses existing output or sidecar files;
choose a new path for another version. It stages protected files and uses
exclusive hard links to publish without overwrite, with the sidecar as the commit
marker. NTFS or a filesystem supporting same-volume hard links is required;
failure rolls back the newly created output. Windows ACLs/POSIX modes are reused
from STEP 04. These controls are not encryption or secure deletion.

Schema-only validation accepts an empty valid template. Strict validation requires
a submission sidecar, known source membership and complete or explicitly deferred
annotation states. Validation reads existing files without assigning labels,
overwriting records, publishing data or declaring human gold status. Generated
data files/sidecars remain excluded from Git under `data/`. Protect all actual
annotation inputs as sensitive: free-form reasons can contain PII despite warnings.
Retention/deletion must follow the source's authorized STEP 04 policy.

## Human approvals before STEP 07

1. The research owner and Vietnamese NLP/domain reviewers approve topic scope,
   tie rules, sentiment boundaries, severity evidence matrix and exclusion rules.
   Keep a dated non-sensitive approval reference with the reviewed version and
   checksum; store sensitive evidence in protected storage. The taxonomy file
   currently records proposed status. Do not relabel it scientifically validated.
2. The data owner/privacy reviewer establishes actual source license, scope,
   expiry and retention through existing governance. No annotation CLI argument
   substitutes for approval. Validate real data and complete human privacy review.
3. A coordinator assigns random pseudonyms to trained, authorized annotators;
   keep any identity mapping outside Git and outside label exports. Do not use
   names/email addresses in `annotator_id`. Preview actual data quality findings
   and resolve privacy/duplicate issues before making annotation assignments.
4. An authorized coordinator binds a submission sidecar to the verified source
   and immutable dataset version. No public CLI for assigning real rows exists
   in STEP 06. Do not turn the synthetic test inventory into a research dataset.

Human approval of the taxonomy does not approve a dataset, and dataset permission
does not scientifically validate the taxonomy. Validators establish structural
and provenance consistency, not factual truth of reasoning or reliability of
human decisions. Current metadata intentionally remains `human_gold=false`.

## Independent annotation and adjudication — planned STEP 07

Two annotators should work independently on the same privacy-cleared version,
without viewing each other's labels. Preserve each original record under its
own pseudonym and record key. Never replace one annotator's judgment with the
other's. Keep revisions immutable and explicitly linked in the later assignment
workflow; the current validator checks duplicate keys within each input only.

STEP 07 may compare independently completed labels, document disagreements and
route them to an authorized adjudicator. Adjudication should create a separate
decision linked to both originals, version/checksum and rationale, rather than
editing originals. Unknown severity and unresolved review records must remain
excluded from supervised labels until explicitly resolved with permitted evidence.
Agreement measurement must name tasks, sample, exclusions and metric; no such
measurement or adjudication implementation exists now.

## Immutable taxonomy semantics

`configs/taxonomy_v1.yaml` uses the project's JSON subset of YAML 1.2, avoiding a
new YAML dependency. The strict model fixes version `1.0.0`, three independent
tasks, exact ordered label codes and separate workflow states. The checksum uses
canonical UTF-8 JSON with sorted object keys and compact separators; formatting
and mapping-key order do not matter, but list order and definitions do.
SHA256 is frozen in `pfa.annotation.taxonomy.CHECKSUM` and recorded in both
template metadata and submitted rows. Loader errors if v1 changes. A digest is
integrity/reproducibility evidence, not a signature or scientific validation.

Do not rename/reorder meanings or edit v1 silently. Future changes need an
explicitly approved new version/file, changelog, new checksum, compatibility
assessment and migration plan retaining original labels/version references.
Approval evidence should reference the frozen instrument rather than modifying
its proposed-status bytes. No migration is implemented because only v1 exists.

STEP 07 is technically prepared by these contracts. Starting its pilot still
requires human approval, authorized/verified data, trained annotators and a
protected assignment/review plan. No real annotation work is authorized by tests.
