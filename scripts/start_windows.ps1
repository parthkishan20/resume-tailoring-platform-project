# scripts/start_windows.ps1 — Start ResumeTailor (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ContainerName = "resumetailor"
$ImageName = "resumetailor"
# Override with $env:PORT to move the dev stack off 8000
# (the e2e stack uses 18173 and never 8000).
$Port = if ($env:PORT) { $env:PORT } else { 8000 }

if (-not (Test-Path ".env")) {
    Write-Error "Error: .env file not found. Copy .env.example to .env and set OPENAI_API_KEY."
    exit 1
}

# Stop existing container
$existing = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $ContainerName }
if ($existing) {
    Write-Host "Stopping existing container..."
    docker stop $ContainerName 2>$null
    docker rm $ContainerName 2>$null
}

# Build if needed
if ($args -contains "--build" -or -not (docker image inspect $ImageName 2>$null)) {
    Write-Host "Building Docker image..."
    docker build -t $ImageName .
}

Write-Host "Starting ResumeTailor..."
docker run -d `
    --name $ContainerName `
    -p "${Port}:8000" `
    -v resumedb-data:/app/db `
    -v resumepdf-data:/app/pdfs `
    --env-file .env `
    --restart unless-stopped `
    $ImageName

Write-Host ""
Write-Host "ResumeTailor is starting at http://localhost:$Port"
Write-Host "Waiting for health check..."

for ($i = 1; $i -le 18; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:$Port/api/health" -UseBasicParsing -ErrorAction Stop | Out-Null
        Write-Host "Ready! Opening http://localhost:$Port"
        Start-Process "http://localhost:$Port"
        exit 0
    } catch {
        Start-Sleep -Seconds 5
    }
}

Write-Warning "App did not become healthy within 90s. Check: docker logs $ContainerName"
