param([switch]$FullTests)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv with Python 3.11 and install requirements-ci.lock first.' }
Push-Location $projectRoot
try {
    & $python -m pfa.cli doctor
    if ($LASTEXITCODE -ne 0) { throw 'Project doctor failed.' }
    & $python -m pfa.cli release preflight --isolated
    if ($LASTEXITCODE -ne 0) { throw 'Isolated release preflight blocked.' }
    & $python -m pfa.cli release smoke
    if ($LASTEXITCODE -ne 0) { throw 'Technical demo smoke failed.' }
    if ($FullTests) {
        & $python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
        & $python -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed.' }
        & $python -m ruff format --check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff format failed.' }
    }
} finally { Pop-Location }
