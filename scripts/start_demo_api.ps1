param([ValidateRange(1024,65535)][int]$Port = 8000, [ValidateRange(0,2147483647)][int]$Seed = 17)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install the locked Python 3.11 environment first.' }
Push-Location $projectRoot
try {
    & $python -m pfa.cli release api --port $Port --seed $Seed
    if ($LASTEXITCODE -ne 0) { throw 'Demo API failed preflight or startup. Check configuration and occupied ports.' }
} finally { Pop-Location }
