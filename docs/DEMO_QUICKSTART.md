# Local TECHNICAL_DEMO_ONLY quickstart (Windows)

Use invented inputs only. No approved model, research dataset or scientific validation
is included. The local API seeds a NEW temporary SQLite store; it never uses `pfa_test`
or PFA_DB_URL. Stopping the API removes that session's synthetic records and corrections.
PostgreSQL and Docker are optional. No public service starts during verification.

## 1. Install and verify

From `D:\congviec\nckh-van`, with Python 3.11 installed:

```powershell
py -3.11 -m venv .venv   # Only when .venv does not already exist.
.\.venv\Scripts\python.exe -m pip install -r requirements-ci.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pfa.cli release smoke
```

Package installation needs network and uses pinned versions plus the official PyTorch
CPU package index. It does not download model weights or datasets. Verification is offline.
Existing environments must match all lock pins; unexpected versions block preflight.
Do not recreate a working environment unnecessarily. A clean Windows-machine install
has not been independently rehearsed. If PowerShell script policy blocks execution,
follow local policy or run the documented Python CLI commands directly; scripts do not
change execution policy. The Python command above works under the observed Restricted
PowerShell script policy. Where scripts are permitted, `verify_demo.ps1` also runs doctor
and preflight, and `verify_demo.ps1 -FullTests` additionally runs pytest and Ruff.

## 2. Prepare credentials in a protected parent PowerShell

Disable any transcript/session recording before generating secrets. These commands
generate values in memory and do not print or hardcode credentials. Do not persist these
values in Git, shell profiles or screenshots. All roles below are synthetic local identities,
not evidence of multiple human researchers.

```powershell
$env:PFA_ENVIRONMENT = 'development'
$env:PFA_API_MODE = 'DEMO_ONLY'
$env:PFA_API_OBSERVABILITY_ENABLED = 'true'
$env:PFA_DASHBOARD_API_URL = 'http://127.0.0.1:8000'
function New-DemoKey {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes); [Convert]::ToBase64String($bytes) } finally { $rng.Dispose() }
}
$adminKey = New-DemoKey
$reviewKey = New-DemoKey
$analystKey = New-DemoKey
$principals = @(
  @{actor_id='demo_admin'; role='ADMIN'; source_ids=@('synthetic_demo'); can_view_text=$true; key=$adminKey},
  @{actor_id='demo_reviewer'; role='REVIEWER'; source_ids=@('synthetic_demo'); can_view_text=$true; key=$reviewKey},
  @{actor_id='demo_analyst'; role='ANALYST'; source_ids=@('synthetic_demo'); can_view_text=$false; key=$analystKey}
)
$env:PFA_API_PRINCIPALS = ConvertTo-Json -InputObject $principals -Compress
$env:PFA_DASHBOARD_API_KEY = $analystKey
.\.venv\Scripts\python.exe -m pfa.cli release preflight
```

The credential helper works in Windows PowerShell 5.1 and PowerShell 7.

Expected preflight: WARNING, exit 0, with mandatory checks PASS. Warnings explicitly
retain research, hosted CI and restore blockers. BLOCKED means do not launch. A default
APPROVED_MODEL configuration, production environment, missing role credentials or
non-ANALYST dashboard key fails closed.

## 3. Start two foreground services in separate inherited terminals

From the same protected parent PowerShell, open two visible child terminals so they
inherit the generated credentials. No secret appears in process arguments:

```powershell
$python = (Resolve-Path '.venv\Scripts\python.exe').Path
Start-Process powershell -WindowStyle Normal -ArgumentList '-NoProfile','-NoExit','-Command',("& '" + $python + "' -m pfa.cli release api --port 8000 --seed 17")
Start-Process powershell -WindowStyle Normal -ArgumentList '-NoProfile','-NoExit','-Command',("& '" + $python + "' -m pfa.cli release dashboard --port 8501")
```

These direct Python invocations do not execute .ps1 files or alter execution policy.
API terminal runs `release api --port 8000 --seed 17`; dashboard terminal runs
`release dashboard --port 8501`. Keep BOTH running. Open http://127.0.0.1:8501 manually.
API documentation: http://127.0.0.1:8000/docs. Dashboard process receives only its ANALYST
key; API/research/DB secrets are removed from its child environment. No browser form
accepts credentials. Both listeners bind 127.0.0.1; occupied ports are rejected.

Alternative where script policy permits: run the wrappers directly in two shells that obtain the same credentials
from a protected local environment manager. Arbitrary new terminals do not inherit the
parent shell's process-only variables automatically. No shared credential file is created.

## 4. Health, prediction and stop

In the protected parent shell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/health/live'
Invoke-RestMethod 'http://127.0.0.1:8000/health/ready'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/operations/status' -Headers @{'X-API-Key'=$adminKey}
$body = @{text='SYNTHETIC: Hướng dẫn thủ tục giả lập chưa rõ.'; request_id='demo-001'} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/predict' -Method Post -Headers @{'X-API-Key'=$reviewKey} -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Prediction is constant mock output, null score, calibrated=false and review required.
It does not save input. Follow DEMO_WALKTHROUGH.md for explicit fixture intake/review.
Press Ctrl+C in the dashboard and API terminals; then close both terminals and the parent
credential shell. No stop script kills unrelated processes. On abnormal termination,
an orphan temporary directory may remain; identify its exact disposable ownership before
manual removal. Never delete a broad directory prefix automatically.

Troubleshooting: 401 = wrong/missing key; 403 = role/source/text access denial; 409 = stale
version/assignment; 503 = unavailable service/model/DB; preflight dependency failure = install
the lock, do not bypass checks. Empty charts: clear filters or select 2025-01-06–2025-01-13.
For a custom API port, update PFA_DASHBOARD_API_URL before launching both services.
