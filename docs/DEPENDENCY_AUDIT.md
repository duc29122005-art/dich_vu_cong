# Explicit release dependency audit

Routine release smoke/preflight never contacts advisory services. To audit explicitly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-audit.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pfa.cli release audit --output reports/releases/NEW_AUDIT_ID
```

The optional audit lock adds pip-audit 2.10.1 and its pinned dependencies while preserving
requirements-ci.lock. The release audit queries that application lock's 84 exact pins,
not unlisted environment packages or local research data. Direct/transitive roles derive
from the project extras used by the technical demo. Tool version, timestamp, lock SHA256,
original versions, advisory query versions, advisory IDs and fix versions are recorded.
Only public package metadata reaches the advisory service. No dataset, source document,
feedback, API key, DB URL or participant identifier is uploaded.

PEP 440 local build tags such as torch's `+cpu` are recorded but removed for upstream
advisory lookup. This checks the corresponding upstream public version, not binary build
provenance or platform-specific exploitability. The first unnormalized run may report
torch as skipped; that incomplete result must not be presented as a clean full audit.

Exit 0 / PASS: completed lookup of all requested public versions with no known findings.
Exit 2 / FINDINGS: affected versions and advisory IDs require assessment. Exit 4 /
AUDIT_NOT_AVAILABLE: missing checker, unavailable network/service or skipped packages.
Tool installation alone is not execution evidence. Reports are immutable ignored bundles;
use a new output ID for every run. Never overwrite earlier incomplete evidence.

For findings: check runtime reachability and advisory applicability, choose a compatible
fix without silently upgrading major ML components, update the release lock deliberately,
rerun subsystem/full regression tests and audit again. Do not suppress an advisory merely
to obtain PASS. Absence of reported advisories is not proof of complete security.
