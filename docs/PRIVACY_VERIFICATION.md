# Privacy and governance verification

Synthetic engineering checks are not permission to process citizen feedback. Real data
remains BLOCKED_PERMISSION. Public visibility does not grant training or publication rights.

- The persistence endpoint accepts bundled synthetic fixture IDs only. `source_id`,
  `is_synthetic`, role headers and extra metadata cannot bypass STEP 03B/04 gates.
- `/predict` and `/predict/batch` remain transient. Explicit synthetic persistence is
  a separate operation. No raw citizen input column or automatic request archive is added.
- Existing screening removes candidate identifiers before inference; it is heuristic,
  may miss PII, and never guarantees anonymization. Use only invented inputs now.
- App logs contain a generated trace ID, allowlisted route, status and elapsed time.
  Query strings, bodies, record IDs, credentials, participant IDs and SQL exception text
  are excluded. Uvicorn access logging remains disabled by the existing local CLI.
- Dashboard and analytics return source-authorized aggregate data only. Small cohort,
  cell and complementary-cell suppression remain enabled. They expose no record drilldown
  or protected holdout labels. Repeated aggregate queries can still permit inference;
  public deployment needs stronger query controls and a privacy review.
- Research readiness is not research authorization. Locked STEP 11 evaluation rules,
  consent, gold provenance and genuine-model gates remain unchanged. No human observations,
  approvals, independent annotators or scientific conclusions are invented.
- Backups, local documents, model artifacts, data and logs remain excluded from Git.
  Existing public contact details were replaced with placeholders; private local originals
  were preserved. This scan does not inspect ignored private files or historical commits.

The integration smoke captures application logs and checks that persisted invented texts
and ephemeral API keys do not occur. Security findings never print matched secret values.
Observe [data retention](DATA_RETENTION.md), [research retention](RESEARCH_DATA_COLLECTION.md)
and [backup restrictions](BACKUP_RESTORE.md) before handling any future authorized data.
