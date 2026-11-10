# Technical handover

Responsible researcher: Dương Thị Hồng Vân, EEP002-K49, BIT, UEH. This is one student's
independent project; there is no supervisor, research team or confirmed independent
annotation team. No official institutional representation or approval is implied.

Start with DEMO_QUICKSTART.md, then DEMO_WALKTHROUGH.md. `release smoke` is the one-command
offline verification. Where script policy permits, `scripts/verify_demo.ps1` additionally
runs doctor and isolated preflight without a server. The API/dashboard
scripts run foreground services in separate protected terminals. Ctrl+C stops them.
The dedicated local demo never reuses pfa_test/PFA_DB_URL and never imports real data.

Architecture: data/governance and normalization; separate model adapters/registry;
FastAPI provider cache; SQLAlchemy review repository and immutable history; authenticated
analytics; Streamlit/Plotly consuming API aggregates; locked research protocols;
integration/release orchestration. STEP 17 reuses those layers rather than adding a
second approval authority. See architecture.md and STEP17_VERIFICATION.md for inventory.

Operational checks: `/health/live`, `/health/ready`, ADMIN `/api/v1/operations/status`.
`python -m pfa.cli ml registry list` inspects governed registry metadata; model status
API shows mock mode. No real model is automatically activated. DB health is separate
from prediction readiness. Use BACKUP_RESTORE.md and BACKUP_RESTORE_REHEARSAL.md before
any future operation; no backup/restore was implied by preparing instructions.

Reproduce: install requirements-ci.lock and editable project, run doctor/preflight,
all documented smokes, pytest and Ruff. `release manifest --output reports/releases/NEW_ID`
publishes a new immutable JSON inventory bundle, not a distributable archive.
`release verify --manifest reports/releases/NEW_ID` detects public source/configuration
drift. STEP17_VERIFICATION.md is an external generation attestation excluded to avoid
self-referential checksums. Keep the bundle hash separately if authenticity matters.

Security: secrets in protected process environment only, no citizen data now, no
unrestricted bind/CORS, no arbitrary model paths, no automatic approval or publication.
Private datasets/models/consent mappings/dumps/logs stay ignored. Review workflow and
lock changes before any authorized push; CI_GUIDE.md explains the first hosted run.

Next work is evidence collection, not invented completion: follow RESEARCH_READINESS_MATRIX.md
and docs/research/EXPERIMENT_EXECUTION_CHECKLIST.md. Missing approvals, gold, genuine
training, consent and observations must remain blocked. Technical demo acceptance is
a human review still to be performed; no acceptance signature is fabricated here.
