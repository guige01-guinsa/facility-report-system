$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendEnv = Join-Path $Backend ".env"
$BackendEnvExample = Join-Path $Backend ".env.example"
$FrontendEnv = Join-Path $Frontend ".env.local"
$FrontendEnvExample = Join-Path $Frontend ".env.example"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (!(Test-Path $BackendEnv)) {
    Copy-Item -Path $BackendEnvExample -Destination $BackendEnv
}

if (!(Test-Path $FrontendEnv)) {
    Copy-Item -Path $FrontendEnvExample -Destination $FrontendEnv
}

if (!(Test-Path $Python)) {
    python -m venv (Join-Path $Backend ".venv")
}

& $Python -m pip install -r (Join-Path $Backend "requirements.txt")

Push-Location $Frontend
try {
    npm.cmd install
}
finally {
    Pop-Location
}
