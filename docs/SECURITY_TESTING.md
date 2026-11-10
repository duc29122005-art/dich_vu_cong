# Security testing

Run `python -m pfa.cli integration security-check` and
`python -m pytest -q tests/test_integration.py tests/test_api.py tests/test_db.py`.
All ordinary checks are offline and use synthetic data.

Regression coverage includes missing/wrong/revoked configured keys, RBAC and forged
role headers, source-scoped IDOR, assigned reviewer ownership, stale versions, SQL-shaped
input, malformed JSON/Unicode, text/body/batch limits, blocked real intake, immutable
predictions/audit history, privacy-safe errors/logs, small cohorts and unavailable models.
Existing artifact checksum, label mapping, preprocessing and model registry tests remain
the authority for model integrity. No public endpoint mutates model approval.
Local credentials have no built-in expiry clock: remove/revoke credentials in protected
server configuration and restart workers. Full identity-provider expiry is not claimed.

The repository scanner inventories Git-tracked files AND unignored candidate files.
This matters before the first commit: a zero tracked-file count is reported explicitly.
Ignored private directories are not opened; an already tracked forbidden artifact still
fails. It checks recognizable service tokens, private-key markers, literal secrets,
credential-bearing URLs, contact emails, contextual identifier patterns, unexpected
datasets/models/backups/binaries and populated official research templates. The permitted
synthetic CSV must match its existing pinned checksum. Reports contain rule/path/line,
never matched values. No file is automatically deleted.

False positives require an exact path, rule and SHA-256 of the entire reviewed line,
plus a reason in `configs/integration_v1.yaml`. Current exceptions cover invented privacy
fixtures and deliberate nonsecret error sentinels. Editing the line invalidates an
exception. Do not add blanket test-directory or secret-pattern exclusions. Treat scanner
policy changes as security-sensitive review. The scanner cannot identify all PII, names,
obfuscated secrets or previously committed Git history; independent review is still required.

STEP 16 found personal contact details in an existing public request template. Public
template now uses protected contact placeholders. Original private Word source documents
remain local and are ignored by Git; they are not public test fixtures or release inputs.

Optional dependency check:

```powershell
python -m pip install pip-audit==2.9.0
python -m pfa.cli integration dependency-check
```

Only package names/versions are sent to the advisory service, never feedback or project
files. Exit 0 means the completed audit found no known vulnerabilities; exit 2 means
advisories were found; exit 4 means the tool/service was unavailable. Unavailability is
never a clean vulnerability result. Normal tests mock this boundary and use no network.
No third-party application-data scanning service is used.
