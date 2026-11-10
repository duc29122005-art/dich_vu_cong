# Local technical demo threat model

Assets: sensitive citizen feedback, API and database credentials, source permission
evidence, model artifacts/registry, participant mappings and human-review history.
Trust boundaries: client/API, API/database, API/model artifacts, dashboard/API,
research evidence/reporting and untrusted repository contributions/CI.

| Threat | Current control | Remaining requirement |
| --- | --- | --- |
| Sensitive feedback or secret exfiltration | transient prediction, fixed errors, safe logs, no response text, ignored private artifacts | approved intake/privacy review, outbound-network policy and reviewed exports |
| Stolen API credentials | protected environment, constant-time checks, restricted local demo, server-side role/source grants | TLS, managed identity, expiry/rotation and rate limits before remote deployment |
| Source permission bypass/admin overreach | source scopes checked server-side; ADMIN never overrides ingestion rights | renewed provider evidence and verified handoff for each real source |
| Cross-source or cross-record IDOR | UUID validation, per-record source check, reviewer assignment ownership | independent penetration testing with actual deployment configuration |
| Database injection or lost updates | ORM bound parameters, constraints, transactions and version compare-and-swap | least-privilege DB accounts and operational monitoring |
| History tampering | immutable prediction and append-only audit triggers | privileged DB administrators can alter/drop triggers; external restricted audit export and backup controls |
| Unsafe/corrupt model artifacts | registry approval scope, taxonomy/label/preprocessing checks and artifact hashes | approved real model and verified pretrained checkpoint; hashes require trusted evidence |
| Protected holdout leakage | separate locked evaluation authorization; API/dashboard have no dataset reader | preserve final-test access audit and prohibit tuning on final results |
| Dashboard re-identification | no raw text/IDs, small-cell suppression, server-side authenticated source scopes | query budget/differential privacy assessment before sensitive public aggregates |
| CI secret theft by pull request | contents:read, pull_request instead of pull_request_target, no production secrets/artifact upload | branch protection, review workflow/lock changes and action revisions |
| CI supply-chain compromise | exact package versions, pinned action revisions, CPU-only environment, offline model flags | review advisories, verify package provenance/hashes; hosted execution not yet verified |
| Resource exhaustion | body/text/batch/concurrency bounds and local binding | proxy rate limits, timeouts and deployment-specific capacity tests |

No control eliminates all security risks. The local demo has no production service or
real-data authorization. Synthetic security tests verify behavior, not deployment assurance.
