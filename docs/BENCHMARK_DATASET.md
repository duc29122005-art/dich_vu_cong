# UIT-VSFC benchmark adapter — STEP 03

## Purpose and current state

UIT-VSFC is a Vietnamese **student feedback** benchmark, not citizen feedback
about public services. It can test ingestion and later NLP baselines. Education
topic IDs must never be mapped directly to public-service topic labels. No
preprocessing, model training, or later-step implementation is included here.

The master plan was absent. This implementation follows the STEP 03 prompt.
No live source metadata, dataset card, or data file was accessed. Current license
status is UNKNOWN, permission is PENDING, and effective scopes are empty.
The repository contains no real benchmark dataset and no real manifest.

## Fields, splits, and mappings

Expected fields are exactly `sentence` (UTF-8 string), `sentiment` (integer), and
`topic` (integer). Splits are `train`, `validation`, and `test`. Field ordering may
vary, but missing, duplicate, extra, and incorrectly typed columns are rejected.
Null/blank text, invalid UTF-8, null labels, booleans, floating-point labels, and
out-of-range IDs fail validation. No row is silently dropped. Text and original
numeric IDs are preserved; no normalization or relabeling takes place.

| Field | Expected reference IDs |
|---|---|
| sentiment | 0 negative; 1 neutral; 2 positive |
| topic | 0 lecturer; 1 training_program; 2 facility; 3 others |

Both reference mappings are currently **UNVERIFIED**. After authorized access,
available ClassLabel names from pinned repository card metadata or embedded
Hugging Face Parquet metadata are compared with the reference, including IDs.
Conflicts fail validation. Missing label metadata stays UNVERIFIED; numeric range
validation alone does not verify semantic labels. A synthetic metadata test does
not verify the real source. Unknown metadata layouts require adapter review.

Expected row counts for all splits are UNKNOWN. Actual row counts are unavailable
until file validation completes. Metadata discovery never counts as a download.
`verify` counts every local row in batches of at most 1,024 rows and checks those
counts against the manifest. No whole-dataset pandas conversion is used.

## Setup and local inspection

Python 3.11 and the existing environment are required. PyArrow is declared in the
existing `data` extra; it is not a default dependency. Install data support with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,data]'
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark inspect --source uit_vsfc
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark verify --source uit_vsfc
```

Inspection defaults to offline expectations from the adapter and local registry.
It reports no verified source fields, no invented counts, and whether a local
manifest exists. It does not claim that an existing manifest has passed integrity
checks; run `verify`. With no local data, verification reports NOT_AVAILABLE and
returns exit 4. It does not fabricate a successful setup.

## Authorization prerequisites

Follow PERMISSION_REGISTER.md. A responsible human must verify the license,
privacy requirements, retention, and **internal_analysis** scope for benchmark
ingestion. Record the decision and its evidence reference in the reviewed
repository workflow. This step also requires the UIT-VSFC registry entry to be
reviewed as permission APPROVED and license VERIFIED, with consistent scope
fields and evidence references. This is an additional benchmark condition; STEP
02's generic scoring and effective-scope behavior remains unchanged.

CLI arguments alone are never evidence. The supplied reference must match the
current audited decision. Missing scope, pending permissions, unresolved license,
revocation, changed evidence, corrupt history, or a journal lock blocks remote
access. There is no permission override flag. Training and publication require
their own explicitly authorized scopes; ingestion approval does not grant them.

**Do not run the following network commands until authorization is established.**
Replace the placeholders with a reviewed decision ID and an actual repository
commit SHA; do not use fabricated evidence or a made-up revision.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark inspect --source uit_vsfc --remote --approval-ref APPROVAL_ID --revision COMMIT_SHA
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark fetch --source uit_vsfc --approval-ref APPROVAL_ID --revision COMMIT_SHA
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark verify --source uit_vsfc
```

Remote inspection is explicit and permission-gated. It fetches repository JSON
metadata only. Discovery reads Parquet filenames from repository siblings, rather
than assuming file URLs. It requires an unambiguous configuration and all three
splits. The default requested revision is `refs/convert/parquet`, a moving
conversion reference; it is resolved once to an immutable 40-character SHA and
all file URLs use that SHA. Prefer supplying a known pinned SHA. A SHA mismatch
fails. No repository Python code is executed; no `trust_remote_code` is used.
Live service compatibility remains unverified while permission is pending.

## Transfer, storage, and manifest

Downloads use credential-free HTTPS, including redirects, with a 30-second
connection/read socket timeout. Transient connection errors, 429, and server
errors receive at most three attempts with 1- and 2-second backoff. 403 and 404
fail immediately. Response bodies and row text are never included in errors.
Metadata responses are capped at 4 MiB; each data file at 2 GiB. This client does
not send authentication tokens. Gated/private sources fail closed rather than
attempting to bypass access controls.

Files are streamed into a temporary sibling directory under `data/benchmarks`.
Each shard must pass full Parquet schema/row validation. The adapter computes
SHA256 and file sizes, writes a manifest, rechecks the complete staged dataset,
and rechecks permission before atomically renaming the directory to:

```text
data/benchmarks/uit_vsfc/
```

The manifest records source ID/URL, role, repository, resolved revision, approval
reference, UTC timestamp, individual pinned file URLs, checksums, sizes, schema,
split names, actual counts, label IDs/mapping evidence status, provenance, and
adapter version. No manifest is produced from online metadata alone.

Existing destinations are never silently overwritten. `verify` checks exact file
inventory, SHA256, sizes, schema, actual row counts, mapping evidence, and manifest
consistency. Real local datasets also require current permission. Verification
is an integrity check, not a new legal authorization or guarantee of model utility.
The manifest is not a signed defense against a malicious local maintainer.

Partial staging files and the local download lock are cleaned after handled
failures. A process crash may leave a staging directory or stale lock: inspect
them before manual recovery; never replace a verified dataset blindly. Git ignores
all downloaded data, manifests, temporary files, and locks under `data`.

## Offline synthetic tests

`tests/fixtures/uit_vsfc_synthetic.json` contains invented Vietnamese examples,
explicitly marked SYNTHETIC. Tests generate temporary Parquet files, including
valid and invalid records, outside the real dataset directory. These fixtures
require no external dataset approval and do not activate `synthetic_demo` or any
real-source permission. They never enter real benchmark counts.

Synthetic manifests use `source_id=synthetic_fixture`, revision SYNTHETIC,
provenance SYNTHETIC, and no external approval reference. CLI verification reports
VERIFIED_SYNTHETIC, never a real benchmark success. Mocked fetch tests also
exercise the external branch entirely in temporary test workspaces with invented
payloads and simulated review metadata. These are not real approvals or downloads.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Exit codes: 0 completed inspection/verification/fetch; 2 invalid arguments, schema,
metadata, manifest, or transfer failure; 3 blocked permission; 4 unavailable local
dataset. Pending permissions must not be interpreted as a technical failure of
the adapter. Future researchers should retain the manifest and environment,
verify source label meanings, obtain separate training approval, and preserve
the distinction between education benchmarks and public-service research.
