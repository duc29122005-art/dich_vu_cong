# Reproducible research commands

Run locally from the repository root with Python 3.11. Research metadata, assignment,
schema and statistics code uses the standard library and existing Pydantic. RQ2
metric tests additionally use the installed scikit-learn dependency. No new package,
GPU, external dataset or pretrained download is needed.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli research status
.\.venv\Scripts\python.exe -m pfa.cli research protocol-check
.\.venv\Scripts\python.exe -m pfa.cli research templates
.\.venv\Scripts\python.exe -m pfa.cli research smoke
.\.venv\Scripts\python.exe -m pytest tests/test_research.py -q
```

`status` is a prospective capability/blocker checklist, not automatic certification
of datasets or ethics. `protocol-check` verifies schemas and pinned STEP 11 hashes;
it is not human approval. `smoke` creates and removes isolated invented inputs,
assignments and reports, uses an internal synthetic capability, and prints
RESEARCH_SMOKE_PASS_SYNTHETIC. Invented participants are explicitly labeled.

Protocol-check also pins STEP 14 analytics/KPI definitions, dashboard questions and
participant-information text. Allocation freezes research/metric implementation
checksums; changed code cannot silently analyze an old allocation. Reports record
implementation and Python/Pydantic versions for reproduction.

## Conditional human collection

First complete the actual permissions, participant protocol, consent, data/gold,
model and source-access evidence described in [the collection contract](RESEARCH_DATA_COLLECTION.md).
Create an authorized **pre-collection** control request pointing to an immutable
protected package containing the exact consenting pseudonyms and eligible case pool,
without observations. Obtain a concrete protected allocation preview:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli research assignments --source data/private/research/collection_request.json --preview
```

The returned target SHA256 binds the full protocol and exact allocation. The private
preview contains assignment pseudonyms/case IDs and should be reviewed only by the
authorized coordinator. CLI output contains counts/checksums only. Review pool
independence, group/content isolation, person aliases, material blinding, difficulty,
model references, timing and sample-size assumptions. Record genuine existing
RESEARCH_ALLOCATION evidence against that exact target, add its reference to the
control metadata and renew RESEARCH_PACKAGE evidence for the changed control metadata.
The manifest target itself does not depend on the approval-reference spelling.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli research assignments --source data/private/research/collection_request.json
```

This freezes allocation atomically. It never creates participant observations,
consent or approval. Repeated calls cannot overwrite it. Human collection remains
blocked today; no participant web UI or actual recruitment is supplied by STEP 15.

## Aggregate reports

After actual collection, create a new immutable observations package, validate its
control metadata/evidence and retain the original allocation reference. Then:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli research report --rq all --source data/private/research/report_request.json
# Individual RQs are also supported:
.\.venv\Scripts\python.exe -m pfa.cli research report --rq rq4 --source data/private/research/report_request.json
```

Current research attempts block. There is no override flag. Real permission and
taxonomy checks precede observation-bundle reads. Report validation checks consent,
frozen allocations, source/dataset/gold/model provenance, mode and all checksums.
It rechecks current rights/inputs before publication. Invalid values are not echoed.

Reports live under `data/private/research/reports/report_<digest>` as immutable
checksum bundles. Identical authorized input/protocol/RQ yields the same report and
ID; changed observations require a new input version. Reports contain aggregate
tables, denominators, exclusions, limitations and statuses, with no participant/case
IDs or citizen text. Small participant groups still require human disclosure review
before external publication; private files are not automatically public-safe.

No scientific narrative, p-value, participant or result is invented. Numerical
engineering outputs remain visibly synthetic; feasibility reports explicitly deny
effectiveness claims. Missing observation/gold/support produces BLOCKED_ON_EXPERIMENT
or INSUFFICIENT_EVIDENCE. RQ2 reads already authorized STEP 11 aggregate manifests
only; STEP 15 never invokes final_evaluate, corpus.evaluation_data, test tuning or
model promotion. A genuine PhoBERT run remains unavailable until actually verified.

Exit codes: 0 successful checks/templates/smoke or supported requested report;
2 invalid/missing schema, file or integrity; 3 governance blocker or insufficient
requested evidence. A structurally valid report may be written with explicit blocked
RQ statuses and exit 3. Do not interpret exit 0 from smoke as a research result.

For PostgreSQL, retain the existing dedicated local TEST_DATABASE_URL procedure.
Research functions add no database schema or reset command. Never reuse a production
database or infer PostgreSQL verification from this filesystem/statistical smoke.
