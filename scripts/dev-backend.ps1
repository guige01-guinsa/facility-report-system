param(
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$BackendEnv = Join-Path $Backend ".env"
$BackendEnvExample = Join-Path $Backend ".env.example"

if (!(Test-Path $BackendEnv)) {
    Copy-Item -Path $BackendEnvExample -Destination $BackendEnv
}

if (!(Test-Path $Python)) {
    Write-Error "Backend virtual environment is missing. Run scripts\setup.ps1 first."
}

$UvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
if ($Reload) {
    $UvicornArgs += "--reload"
}

Push-Location $Backend
try {
    & $Python @UvicornArgs
}
finally {
    Pop-Location
}
