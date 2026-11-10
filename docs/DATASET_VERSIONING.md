# Frozen dataset versions

STEP 08A implements software infrastructure only. No authorized research corpus
exists. STEP 08B requires approved taxonomy/handbook, a completed real 200-record
pilot, full human-adjudicated annotations, privacy clearance and dataset/card approval.

## Authorized construction

Run as the designated Windows coordinator from STEP 07. Existing source permission
must cover internal analysis, training and publication, with verified license,
privacy, expiry and retention. The STEP 04 source manifest must still match its
current permission decision. Renewed source permission may require a separately
reviewed source version; do not edit old manifests to substitute approvals.

Use STEP 07 adjudicated batches to cover the full corpus, retaining independent
annotations, justifications and agreement reports. Batch sizes may differ from
the required 200-record research pilot. Select exactly one final revision for
each record: overlapping batch membership is rejected. Excluded records remain
accounted for through final decisions and aggregate exclusion counts.

The coordinator prepares a protected request using `pfa.data.corpus.BuildPlan` at
`data/private/annotation_pilots/requests/build_<version>.json`. Required fields:

- `version`, `source_id`, STEP 04 `dataset_version`, completed `research_pilot`;
- unique `gold_pilots` identifying the adjudicated batches;
- `seed`, `config_checksum` (canonical `pilot_store.digest(SplitConfig.model_dump())`);
- `relations`: every annotated feedback ID mapped to reviewed grouping references;
  empty lists explicitly mean no additional known relationships;
- `pilot_holdout_approved_ids`: pilot IDs explicitly cleared for later holdout;
- `unknown_severity_approved_ids`: explicit human acceptance of topic/sentiment-only use;
- actual `reviewer_id`, `evidence_reference`, nonfuture timezone-aware `reviewed_at`,
  `human_verified: true` only after genuine verification.

Relations must use `case:`, `thread:`, `source:` or `near:` followed by a keyed
64-character hexadecimal fingerprint. Generate these in protected preprocessing
using the existing secret fingerprint key; never use raw PII or unsalted case IDs.
Taxonomy, source membership and current adjudication evidence are revalidated.
Missing grouping entries or unresolved review conditions block construction.

With actual approvals in place, preview the proposed construction:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset build --version service_feedback_v1 --seed 42 --preview
```

The preview returns aggregate diagnostics, proposed card, `construction_checksum`
and `card_checksum`, without publishing files. Review warnings, annotation coverage,
unknown severity exceptions, holdout eligibility, retention and intended usage.
Unannotated source records are explicitly counted/warned; an approved subset must
not be represented as fully labeled source coverage.

After genuine human approval of that exact proposal and card, create a separate
protected request `dataset_<version>.json` conforming to `DatasetApproval`:
`version`, exact `construction_checksum`, exact `card_checksum`, `reviewer_id`,
`evidence_reference`, actual timezone-aware `reviewed_at`, `human_verified: true`,
`decision: APPROVED`. The CLI cannot grant this approval. The trusted coordinator
must authenticate the human decision and keep sensitive evidence outside Git.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset build --version service_feedback_v1 --seed 42
.\.venv\Scripts\python.exe -m pfa.cli dataset check-leakage --version service_feedback_v1
```

Optional `--config PATH` accepts strict JSON `SplitConfig`. Preserve the exact
policy and seed used in the plan. Build gates run again before atomic publication.
Do not execute real builds while project approval/data gates remain pending.

## Storage and integrity

`data/processed/<version>/` contains train/validation/test Parquet, `manifest.json`,
`checksums.json` and `DATASET_CARD.md`. All are Git-ignored and stored in restricted
coordinator-owned storage. The manifest is private: it includes non-identifying
membership, grouping/provenance and approval references. The card is aggregate-only
but still requires authorized release and human approval.

The manifest binds schema/algorithm versions, source manifest checksum, taxonomy
version/checksum/mappings, gold revisions and agreement references, permission and
retention snapshot, plan, processing configuration, build timestamp, exclusions,
split counts, frozen test membership hash and construction checksum. SHA256 covers
each artifact including the manifest/card. Seeded membership is deterministic;
build timestamps and byte-level Parquet output are not claimed reproducible across
different PyArrow versions. Preserve the environment for byte reproducibility.

Protected temporary directories, an exclusive per-version lock and directory rename
provide atomic local publication. Existing versions refuse overwrite. This is
application-level immutability, not WORM storage, digital signatures or encryption.
An administrator can modify storage; retain independently controlled approval evidence.
Inspect stale locks after crashes; never silently delete or reconstruct audit history.
Follow source-approved retention for all versions, deliveries and backups. File
deletion does not guarantee secure erasure.

Synthetic builds are restricted to internal temporary sessions. They cannot create
research gold, human approvals or completed real dataset cards. `split-smoke` cleans
its temporary corpus and labels its statistics SOFTWARE/SYNTHETIC.
