# scripts/run_e2e.ps1 — Run the e2e suite against the isolated test stack (Windows PowerShell)
#
# The test stack is a separate compose project (`resumetailor-e2e`) on a
# separate host port with tmpfs storage and a mock LLM. It cannot reach the
# dev stack's data. Nothing survives the run: `down -v` removes the containers
# and the network, and tmpfs storage is gone with the container.
#
# Usage:
#   .\scripts\run_e2e.ps1
#   $env:E2E_HOST_PORT = "19000"; .\scripts\run_e2e.ps1
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "docker-compose.test.yml"

# Must not be 8000: that is the dev stack's port. Also refuse it if the caller
# overrides it, so this script cannot be talked into a collision.
if (-not $env:E2E_HOST_PORT) { $env:E2E_HOST_PORT = "18173" }
if ($env:E2E_HOST_PORT -eq "8000") {
    Write-Error "E2E_HOST_PORT=8000 is the dev stack's port. Pick another."
    exit 1
}

Write-Host "Starting the e2e stack (project resumetailor-e2e, host port $($env:E2E_HOST_PORT))..."
try {
    docker compose -f $ComposeFile up --build --abort-on-container-exit --exit-code-from playwright
    $exitCode = $LASTEXITCODE
} finally {
    Write-Host ""
    Write-Host "Tearing down the test stack..."
    docker compose -f $ComposeFile down -v --remove-orphans 2>$null | Out-Null
}

exit $exitCode
