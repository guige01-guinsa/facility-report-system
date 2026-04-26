$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    Write-Error "Backend virtual environment is missing. Run scripts\setup.ps1 first."
}

Push-Location $Backend
try {
    & $Python -m compileall app
    & $Python -m unittest discover -s tests -p "test_*.py" -v
}
finally {
    Pop-Location
}

Push-Location $Frontend
try {
    npm.cmd run build
}
finally {
    Pop-Location
}
