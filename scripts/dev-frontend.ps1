param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$FrontendEnv = Join-Path $Frontend ".env.local"
$FrontendEnvExample = Join-Path $Frontend ".env.example"

if (!(Test-Path $FrontendEnv)) {
    Copy-Item -Path $FrontendEnvExample -Destination $FrontendEnv
}

Push-Location $Frontend
try {
    if (!(Test-Path "node_modules")) {
        npm.cmd install
    }
    npm.cmd run dev -- --port $Port
}
finally {
    Pop-Location
}
