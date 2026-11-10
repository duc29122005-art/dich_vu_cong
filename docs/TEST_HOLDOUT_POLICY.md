# Final test holdout policy

Dataset construction can use adjudicated labels for stratification. After
freezing, test membership, file SHA256 and membership checksum must remain fixed.
No test-based hyperparameter selection, feature design, prompt selection or
taxonomy revision is permitted. Never resplit until a desirable score appears.

`pfa.data.corpus.model_selection(root, registry, version, partition)` accepts only
`train` and `validation`. It rejects test/all/path-like requests before opening
artifacts. It verifies current governance and checksums, then deserializes only the
requested partition. Integrity hashing can read test bytes without exposing labels
to the caller. Regression tests track partition readers and prove test Parquet
labels are never loaded through this interface.

Test evaluation uses the separate `evaluation_data` reader. A protected existing
human request must include exactly `version`, frozen `test_checksum`, actual
`reviewer_id`, timezone-aware `reviewed_at`, future timezone-aware `expires_at`,
`purpose: FINAL_EVALUATION`, `human_verified: true`, and `evidence_reference`.
The trusted coordinator authenticates the human evidence; a boolean alone is not
proof. Access records an immutable one-use request snapshot under
`data/private/evaluation_access/<reference>/` before returning test records.
Reusing that reference fails. No evaluation CLI or model training is implemented.

This is an application interface boundary, not a sandbox for arbitrary Python or
a prohibition enforced against administrators. Frozen files remain coordinator-owned
with restrictive ACLs. Do not grant developers raw storage access or coordinator
credentials; provide only authorized train/validation deliveries through a controlled
process. Real multi-user account ACLs and transfer channels require deployment
verification. Do not claim encryption or protection against malicious administrators.

Pilot examples may have influenced handbook/taxonomy changes. By default all
research pilot records and their connected groups remain train-only. Inclusion
in validation/test requires explicit record-level human holdout eligibility in the
build plan and review of the resulting bias. Do not describe such reviewed pilot
data as a completely unseen population without justification.

Future model artifacts must record dataset version, train/validation/test hashes,
configuration checksum and the final evaluation reference. Training/model artifact
implementation belongs to later steps. No models were trained in STEP 08A.
