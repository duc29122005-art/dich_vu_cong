# TECHNICAL_DEMO_ONLY release checklist

Engineering acceptance and human review of the demo do not constitute scientific approval.

| Gate | Requirement / verification | Current evidence |
| --- | --- | --- |
| Environment | Python 3.11, exact requirements-ci.lock pins, `doctor`, `pip check` | Execute and record in STEP17_VERIFICATION.md |
| Preflight | `release preflight --isolated`; live mode additionally requires role credentials | Mandatory failures block; optional blockers produce WARNING |
| E2E | `release smoke`, `integration smoke`, existing subsystem smokes | Synthetic engineering only |
| Privacy/security | scanner, RBAC, source rights, audit immutability, holdout regression tests | No real citizen inputs allowed |
| Tests | full pytest and Ruff lint/format | Record exact counts/skips/exits |
| Manifest | create new immutable bundle and `release verify` | Hashes bind public source/configuration; no archive/publication |
| Launch | localhost API + authenticated Streamlit, occupied port rejection | Foreground user action only |
| Cards/protocol | accurate synthetic cards, blank result templates, readiness matrix | No scientific findings |
| PostgreSQL | `release postgres-check` and explicit test files when configured | Current-run result separate from historical VERIFIED |
| Advisory audit | explicit `release audit --output reports/releases/NEW_ID` | PASS/FINDINGS/NOT_AVAILABLE; never inferred from tool installation |
| Restore | explicit disposable source/target rehearsal | NOT_VERIFIED until actually executed |
| Hosted CI | inspect a real GitHub run after authorized push | NOT_VERIFIED until executed |
| Research | permission, real gold, genuine models, experiment observations | BLOCKED; not required for labeled technical demo |

Do not remove gates to obtain green output. Do not publish private stores, dumps, keys,
restricted models or participant mappings. Remaining operational gaps prevent claims
of full operational or production readiness.
