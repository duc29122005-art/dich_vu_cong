# Known limitations

- Demo predictions are constant fixtures unrelated to input meaning. Scores are null,
  calibration is false, and every prediction requires human review.
- Analytics fixture labels/dates and review histories are invented; no population
  inference, accuracy, independent agreement, usability or public-service quality claim follows.
- No authorized real dataset, approved gold, genuine PhoBERT fine-tuning or RQ1–RQ4 results.
- Local SQLite demo does not verify PostgreSQL behavior. Historical PostgreSQL 18.6
  verification remains separate from current TEST_DATABASE_URL-dependent execution.
- Temporary demo state lasts only for the API process. Ctrl+C removes the owned store;
  abnormal termination may leave an orphan. There is no persistent production intake.
- API keys have no automatic expiry; protected configuration and worker restart implement
  revocation. Public service needs TLS, managed authentication, rate limits and deployment review.
- Small-cell suppression is not complete protection against repeated-query inference.
  Privacy screening is heuristic, not guaranteed anonymization.
- Application audit immutability cannot prevent a privileged DB administrator changing triggers.
- Version pins aid reproducibility but are not signed package provenance or a hash-locked
  supply-chain guarantee. Advisory audit coverage/execution must be reported explicitly.
- Hosted CI, clean-machine installation and PostgreSQL restore rehearsal are not proven
  by local tests or documentation. No production readiness is claimed.
- Hash manifests detect changes relative to their inventory; they are not digital signatures,
  immutable external attestations or proof of scientific validation.
