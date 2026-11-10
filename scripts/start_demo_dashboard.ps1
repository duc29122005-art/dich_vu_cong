param([ValidateRange(1024,65535)][int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the locked Python 3.11 environment first.' }
Push-Location $projectRoot
try {
    & $python -m pfa.cli release dashboard --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Demo dashboard failed preflight or startup.' }
} finally { Pop-Location }
