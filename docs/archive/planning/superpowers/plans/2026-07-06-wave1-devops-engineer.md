# DevOps Engineer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create all Docker, docker-compose, start/stop scripts, and project-root config files so the app can be built and run with a single command.

**Architecture:** Multi-stage Dockerfile (Node 20 → Python 3.12). Stage 1 builds the Next.js static export. Stage 2 installs Python deps via uv, copies the static build into `backend/static/`, and runs uvicorn. No texlive — rendercv v2.x uses Typst installed as a pip dep.

**Tech Stack:** Docker, docker-compose, bash (macOS/Linux scripts), PowerShell (Windows scripts)

## Global Constraints

- Reference: `planning/PLAN.md §9`, `planning/backend_API.md §2` (Typst, not LaTeX)
- Single container, port 8000
- Two named volumes: `resumedb-data:/app/db`, `resumepdf-data:/app/pdfs`
- HEALTHCHECK: `GET http://localhost:8000/api/health` every 30s, start-period 60s
- All scripts are idempotent (safe to run multiple times)
- Stop scripts do NOT remove volumes (data persists)
- `.env` is gitignored; `.env.example` is committed

---

## File Structure

```
resume-tailoring-platform/
├── .gitignore              CREATE
├── .env.example            CREATE
├── db/
│   └── .gitkeep            CREATE
├── Dockerfile              CREATE
├── docker-compose.yml      CREATE
├── docker-compose.test.yml CREATE
└── scripts/
    ├── start_mac.sh        CREATE
    ├── stop_mac.sh         CREATE
    ├── start_windows.ps1   CREATE
    └── stop_windows.ps1    CREATE
```

---

## Task 1: Project Root Config Files

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `db/.gitkeep`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
# Environment
.env

# Database (runtime file, not committed)
db/resumedb.db

# Generated PDFs (runtime, not committed)
pdfs/

# Frontend build
frontend/.next/
frontend/out/
frontend/node_modules/

# Backend
backend/.venv/
backend/__pycache__/
backend/**/__pycache__/
**/*.pyc
**/*.pyo
*.egg-info/

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
```

- [ ] **Step 2: Create `.env.example`**

```bash
# .env.example
# Copy this file to .env and fill in your values before running the app.

# Required: Your OpenRouter API key
# Get one at https://openrouter.ai/keys
OPENROUTER_API_KEY=your-openrouter-api-key-here

# LLM model used for all tasks (generation, evaluation, chat, PDF import)
# Default: openai/gpt-oss-120b:free (free tier, no billing required)
LLM_MODEL=openai/gpt-oss-120b:free

# Set to true to use deterministic mock LLM responses (for testing only)
LLM_MOCK=false
```

- [ ] **Step 3: Create `db/.gitkeep`**

```bash
mkdir -p db && touch db/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example db/.gitkeep
git commit -m "chore: gitignore, env example, db directory"
```

---

## Task 2: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

```dockerfile
# Dockerfile

# ── Stage 1: Build Next.js static export ────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --quiet
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python runtime ──────────────────────────────────────────────────
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy backend source and lockfile
COPY backend/ ./backend/

# Install Python dependencies (rendercv pulls in typst automatically — no texlive needed)
WORKDIR /app/backend
RUN uv sync --frozen --no-dev

# Copy frontend static export into backend/static/
COPY --from=frontend-builder /build/frontend/out ./static/

# Runtime directories for volumes
RUN mkdir -p /app/db /app/pdfs

WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uv", "run", "--project", "/app/backend", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
```

- [ ] **Step 2: Verify Dockerfile syntax (no Docker daemon needed)**

```bash
docker build --help > /dev/null && echo "Docker available" || echo "Docker not available — syntax check skipped"
# If Docker is available, do a dry-run:
# docker build --no-cache -t resumetailor . --progress=plain 2>&1 | head -40
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat(devops): multi-stage Dockerfile (Node→Python, Typst via rendercv pip)"
```

---

## Task 3: docker-compose Files

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.test.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
# docker-compose.yml
version: "3.9"

services:
  app:
    build: .
    image: resumetailor
    ports:
      - "8000:8000"
    volumes:
      - resumedb-data:/app/db
      - resumepdf-data:/app/pdfs
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  resumedb-data:
  resumepdf-data:
```

- [ ] **Step 2: Create `docker-compose.test.yml`**

```yaml
# docker-compose.test.yml
version: "3.9"

services:
  app:
    build: .
    image: resumetailor
    ports:
      - "8000:8000"
    volumes:
      - test-db:/app/db
      - test-pdfs:/app/pdfs
    environment:
      - LLM_MOCK=true
      - OPENROUTER_API_KEY=mock-key-not-used
      - LLM_MODEL=openai/gpt-oss-120b:free
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  playwright:
    image: mcr.microsoft.com/playwright:v1.44.0-jammy
    depends_on:
      app:
        condition: service_healthy
    volumes:
      - ./test:/test
    working_dir: /test
    command: npx playwright test
    environment:
      - BASE_URL=http://app:8000

volumes:
  test-db:
  test-pdfs:
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml docker-compose.test.yml
git commit -m "feat(devops): docker-compose for production and testing"
```

---

## Task 4: Start/Stop Scripts

**Files:**
- Create: `scripts/start_mac.sh`
- Create: `scripts/stop_mac.sh`
- Create: `scripts/start_windows.ps1`
- Create: `scripts/stop_windows.ps1`

- [ ] **Step 1: Create `scripts/start_mac.sh`**

```bash
#!/usr/bin/env bash
# scripts/start_mac.sh — Start ResumeTailor (macOS/Linux)
set -euo pipefail

CONTAINER_NAME="resumetailor"
IMAGE_NAME="resumetailor"
PORT=8000

# Check for .env file
if [ ! -f ".env" ]; then
  echo "Error: .env file not found. Copy .env.example to .env and set OPENROUTER_API_KEY."
  exit 1
fi

# Stop any existing container with this name
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping existing container..."
  docker stop "${CONTAINER_NAME}" 2>/dev/null || true
  docker rm "${CONTAINER_NAME}" 2>/dev/null || true
fi

# Build if --build flag passed or image doesn't exist
if [[ "${1:-}" == "--build" ]] || ! docker image inspect "${IMAGE_NAME}" &>/dev/null; then
  echo "Building Docker image..."
  docker build -t "${IMAGE_NAME}" .
fi

echo "Starting ResumeTailor..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  -p "${PORT}:${PORT}" \
  -v resumedb-data:/app/db \
  -v resumepdf-data:/app/pdfs \
  --env-file .env \
  --restart unless-stopped \
  "${IMAGE_NAME}"

echo ""
echo "ResumeTailor is starting at http://localhost:${PORT}"
echo "Waiting for health check..."

# Wait up to 90s for health
for i in $(seq 1 18); do
  if curl -sf "http://localhost:${PORT}/api/health" > /dev/null 2>&1; then
    echo "Ready! Opening http://localhost:${PORT}"
    # Open browser if on macOS
    if command -v open &>/dev/null; then
      open "http://localhost:${PORT}"
    fi
    exit 0
  fi
  sleep 5
done

echo "Warning: app did not become healthy within 90s. Check: docker logs ${CONTAINER_NAME}"
```

- [ ] **Step 2: Create `scripts/stop_mac.sh`**

```bash
#!/usr/bin/env bash
# scripts/stop_mac.sh — Stop ResumeTailor (macOS/Linux)
set -euo pipefail

CONTAINER_NAME="resumetailor"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping ResumeTailor..."
  docker stop "${CONTAINER_NAME}"
  docker rm "${CONTAINER_NAME}"
  echo "Stopped. Your data is preserved in Docker volumes (resumedb-data, resumepdf-data)."
else
  echo "ResumeTailor is not running."
fi
```

- [ ] **Step 3: Create `scripts/start_windows.ps1`**

```powershell
# scripts/start_windows.ps1 — Start ResumeTailor (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ContainerName = "resumetailor"
$ImageName = "resumetailor"
$Port = 8000

if (-not (Test-Path ".env")) {
    Write-Error "Error: .env file not found. Copy .env.example to .env and set OPENROUTER_API_KEY."
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
    -p "${Port}:${Port}" `
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
```

- [ ] **Step 4: Create `scripts/stop_windows.ps1`**

```powershell
# scripts/stop_windows.ps1 — Stop ResumeTailor (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ContainerName = "resumetailor"

$existing = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $ContainerName }
if ($existing) {
    Write-Host "Stopping ResumeTailor..."
    docker stop $ContainerName
    docker rm $ContainerName
    Write-Host "Stopped. Your data is preserved in Docker volumes (resumedb-data, resumepdf-data)."
} else {
    Write-Host "ResumeTailor is not running."
}
```

- [ ] **Step 5: Make shell scripts executable and commit**

```bash
chmod +x scripts/start_mac.sh scripts/stop_mac.sh
git add scripts/ Dockerfile docker-compose.yml docker-compose.test.yml .gitignore .env.example db/.gitkeep
git commit -m "feat(devops): start/stop scripts (mac + windows) — Wave 1 DevOps complete"
```

---

**Definition of done:** All files committed. `docker build -t resumetailor .` succeeds once Wave 2 (Backend API) is complete and `backend/pyproject.toml` + `backend/app/main.py` exist.
