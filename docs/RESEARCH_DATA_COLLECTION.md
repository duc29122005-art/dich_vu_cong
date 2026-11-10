# Collection contracts and protected storage

Official blank templates are in `templates/research/`: participants, assignments,
manual observations, assisted observations, dashboard tasks, questionnaire, gold
references, deviations and consent events. Each has a CSV header, empty JSONL and
JSON Schema. They contain **zero** participants, consent decisions or observations.
Invented examples exist only in `pfa.research.smoke` and tests, not official templates.

Do not fill the committed blank files. Export a fresh protected copy:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli research templates
.\.venv\Scripts\python.exe -m pfa.cli research templates --output data/private/research/collection_v1
.\.venv\Scripts\python.exe -m pfa.cli research validate --kind manual_observations --input data/private/research/collection_v1/manual_observations.jsonl
```

Export refuses an existing directory, preventing accidental overwrite. Schema-only
validation establishes no permission, valid consent, independent gold or experiment
eligibility. CSV headers must exactly match the exported schema; cells containing
objects use JSON, blank cells represent null. JSONL has one JSON object per line.
Malformed rows, extra fields, unsafe paths and inconsistent durations fail without
echoing submitted values. File ceiling is 20 MiB/20,000 records; typed payload list
ceilings also apply. No free-text participant comments are collected in version 1;
use fixed reason codes rather than storing identities or citizen PII in comments.

## Observation semantics

Each RQ4 row records mode, experiment/assignment/case/session IDs, pseudonym, condition
and order; nullable primary topic `model_version` and three-task `model_versions`;
aware start/end timestamps and measured duration; completion state; three reviewer
labels; a protected gold-reference ID; actual displayed suggestion and acceptance/
override flags; reason/measurement source, consent and protocol references; optional
usefulness/workload. Manual rows cannot contain AI assistance. Completed rows require
labels and measured end/duration. Unknown severity is allowed as an uncertain response.

Model references identify the three actual evaluated registered models. Freeze their
mapping in allocation before collection. Keep gold answers and reference maps away
from participant material. An observation's `reference_gold_id` is coordinator-side
linkage, not something displayed to the participant. Assignment exports contain no
reference labels. Clock source must distinguish real instrument/manual observations
from invented SYNTHETIC_FIXTURE measurements.

## Private bundle contract

`pfa.research.schemas.Request` is small control metadata. `Payload` contains typed
cases, participants, consent events, observations, usability/questionnaire rows,
gold references, deviations, numerical checks and reference alert windows. The
control request declares mode, experiment, protocol/taxonomy hashes, source,
frozen model-dataset version where applicable, exact case membership, payload ID
and checksum, evidence refs, assistance models and participant involvement.

Coordinator packaging uses existing immutable storage, not a public API upload:

```python
from pfa.annotation import pilot_store as store
from pfa.research.protocol import base
from pfa.research.schemas import Payload

# root is the approved workspace; actual_payload contains authorized collected data.
validated = Payload.model_validate(actual_payload)
checksum = store.publish(
    base(root) / "inputs" / payload_id, {"payload.json": validated.model_dump(mode="json")}
)
```

This packaging operation does **not** authorize ingestion, participant access or
reporting. A trusted coordinator must possess those rights before creating a real
input bundle. There is deliberately no ungated research-file importer. Control
metadata points only to `data/private/research/inputs/<payload_id>`; no arbitrary
payload path or protected dataset file is accepted. Integrity inventory/atomic
publication reuse STEP 07 storage. Keep signed identity/consent originals in a
separate protected location; do not package names, emails, signatures or raw text.

## Evidence records

Reuse the existing protected `model_registry.Authorization` schema and coordinator
request storage. No second model approval authority is introduced. All approvals
must be genuine, currently valid, human-verified and bound to exact target hashes.
The CLI never creates approval records. Required actions are:

| Evidence action | Target |
|---|---|
| RESEARCH_PACKAGE | Canonical digest of the control request excluding authorization_ref |
| PARTICIPANT_PROTOCOL | Exact research protocol SHA256, with actual institutional applicability/ethics determination |
| HUMAN_PARTICIPANT_ACCESS | Digest of protocol_sha256, source_id, dataset_version, mode and sorted case_membership |
| VERIFY_CONSENT_EVENT | Canonical digest of the exact typed consent event in JSON mode |
| RESEARCH_ALLOCATION | Digest of `{protocol: exact_protocol, allocation: exact_manifest}` from reviewed preview |

Real-data participant-display evidence requires a `data_steward` reviewer role, in
addition to current source internal-analysis rights. Neither student/admin access
nor generic research approval expands provider rights. Ethics/access/allocation
review dates must precede observed tasks. Supporting institutional/provider documents
stay private; software does not determine legal or ethics approval applicability.
Consent-state verification attests an actual event, not that software granted consent.

Gold references point to disjoint verified existing STEP 07 adjudication bundles.
Their source/version, labels and checksums must match. A pilot containing any frozen
train/validation/test member is rejected before gold is read. Human group/content
isolation review still covers related cases and person-ID aliases across versions.

## Versions, deviations and withdrawal

Freeze allocation before observations. Later input packages get new immutable IDs
and checksums; never overwrite an input, assignment or report. A deviation references
the existing experiment and optional assigned item, with a fixed code and protected
evidence. Missing observations remain missing, not fabricated incomplete rows.
Do not automatically exclude deviations to improve estimates; report their counts
and resolve a prospective exclusion rule through human protocol review.

On withdrawal, block retained observations, remove/withhold them through an approved
steward process and submit a new authorized input while keeping original allocation
and minimal withdrawal audit. Declined/withdrawn participants with no retained rows
can remain as missing assignments; they cannot receive a new allocation without
current consent. Retention and backup rules are in
[the participant protection policy](RESEARCH_PARTICIPANT_CONSENT.md) and
[existing retention documentation](DATA_RETENTION.md).
