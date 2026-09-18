# T4 DevOps Engineer — Wave 1 Implementation Report

**Date:** 2026-07-06  
**Status:** DONE  
**Agent:** T4 DevOps Engineer

---

## Summary

Successfully implemented all Docker, docker-compose, and start/stop scripts for ResumeTailor. All 4 tasks completed and committed per the specification.

---

## Commits Created

| SHA | Subject |
|-----|---------|
| `25b8dd5` | chore: gitignore, env example, db directory |
| `4d7904a` | feat(devops): multi-stage Dockerfile (Node→Python, Typst via rendercv pip) |
| `a389a44` | feat(devops): docker-compose for production and testing |
| `ec8005e` | feat(devops): start/stop scripts (mac + windows) — Wave 1 DevOps complete |

---

## Implementation Checklist

### Task 1: Project Root Config Files ✓

- [x] `.gitignore` — Updated with missing entries (db/resumedb.db, pdfs/, Thumbs.db, backend/**/__pycache__/) without replacing existing content
- [x] `.env.example` — Created with OPENROUTER_API_KEY, LLM_MODEL, LLM_MOCK variables
- [x] `db/.gitkeep` — Created to preserve directory in version control
- [x] Committed

**Files:**
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.gitignore` (updated)
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.env.example` (created)
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/db/.gitkeep` (created)

### Task 2: Dockerfile ✓

- [x] Multi-stage Dockerfile created
  - Stage 1: Node 20-slim for frontend build (npm ci + npm run build)
  - Stage 2: Python 3.12-slim for backend runtime
- [x] uv installed from ghcr.io/astral-sh/uv:latest via COPY --from
- [x] `uv sync --frozen --no-dev` for reproducible dependency installation
- [x] HEALTHCHECK configured:
  - Endpoint: GET http://localhost:8000/api/health
  - Interval: 30s
  - Timeout: 10s
  - Start period: 60s
  - Retries: 3
- [x] Port 8000 exposed
- [x] Two runtime directories created: /app/db and /app/pdfs
- [x] Frontend static export copied from Stage 1
- [x] NO texlive — rendercv uses Typst as a pip dependency
- [x] Committed

**File:**
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/Dockerfile`

### Task 3: docker-compose Files ✓

#### docker-compose.yml
- [x] Service: `app` (resumetailor image)
- [x] Port mapping: 8000:8000
- [x] Named volumes:
  - `resumedb-data:/app/db`
  - `resumepdf-data:/app/pdfs`
- [x] env_file: .env
- [x] restart policy: unless-stopped
- [x] HEALTHCHECK with same specs as Dockerfile
- [x] Volume definitions at bottom

#### docker-compose.test.yml
- [x] Service: `app` with test environment
  - LLM_MOCK=true
  - Temporary test volumes (test-db, test-pdfs)
- [x] Service: `playwright` for E2E testing
  - Depends on app health check
  - Mounts ./test directory
  - Runs: npx playwright test
  - BASE_URL=http://app:8000
- [x] Faster health check (10s interval, 30s start-period for tests)
- [x] Committed

**Files:**
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/docker-compose.yml`
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/docker-compose.test.yml`

### Task 4: Start/Stop Scripts ✓

#### Bash Scripts (macOS/Linux)
- [x] `scripts/start_mac.sh` — 1,564 bytes
  - Checks .env file exists
  - Stops any existing container
  - Builds image if --build flag or image doesn't exist
  - Runs container with volumes and env_file
  - Waits up to 90s for health check
  - Opens browser on success (macOS)
  - Made executable (755 permissions)

- [x] `scripts/stop_mac.sh` — 442 bytes
  - Stops and removes container if running
  - Preserves volumes (data persists)
  - Idempotent (safe to run multiple times)
  - Made executable (755 permissions)

#### PowerShell Scripts (Windows)
- [x] `scripts/start_windows.ps1` — 1,544 bytes
  - Windows equivalent of start_mac.sh
  - Uses PowerShell idioms (Write-Host, Invoke-WebRequest, Start-Process)
  - Same functionality: .env check, build, run, wait for health

- [x] `scripts/stop_windows.ps1` — 500 bytes
  - Windows equivalent of stop_mac.sh
  - Idempotent

**Files:**
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/scripts/start_mac.sh` (executable)
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/scripts/stop_mac.sh` (executable)
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/scripts/start_windows.ps1`
- `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/scripts/stop_windows.ps1`

---

## Key Implementation Details

### Dockerfile
- **Stage 1 (frontend-builder):** Builds Next.js static export to `/build/frontend/out`
- **Stage 2 (runtime):** Python 3.12-slim base, installs uv, syncs backend deps, copies frontend static
- **CMD:** `uv run --project /app/backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`

### docker-compose
- **Production:** Reads from .env file, persistent named volumes
- **Testing:** Injects LLM_MOCK=true, temporary test volumes, playwright service for E2E tests

### Scripts
- **start_mac.sh / start_windows.ps1:**
  - Idempotent: safe to run multiple times
  - Checks for .env before proceeding
  - Builds on --build flag or if image doesn't exist
  - Waits for health check (90s timeout)
  - Opens browser on success

- **stop_mac.sh / stop_windows.ps1:**
  - Idempotent: safe to run if container doesn't exist
  - Preserves data in Docker volumes
  - No forced removal or volume cleanup

### .gitignore Updates
Added entries not covered by existing patterns:
- `db/resumedb.db` — Runtime database file
- `pdfs/` — Generated PDF directory
- `backend/__pycache__/` — Backend build artifacts
- `backend/**/__pycache__/` — Nested package artifacts
- `Thumbs.db` — Windows thumbnail cache

Did NOT duplicate or replace existing patterns like `__pycache__/`, `*.py[cod]`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.idea/`, `.vscode/`, `.DS_Store`, `.env`, `node_modules/`, `frontend/.next/`, `frontend/out/`, `frontend/node_modules/`.

---

## Verification

All files created and committed:
```
.gitignore                    (updated)
.env.example                  (new)
db/.gitkeep                   (new)
Dockerfile                    (new, 43 lines)
docker-compose.yml            (new, 26 lines)
docker-compose.test.yml       (new, 41 lines)
scripts/start_mac.sh          (new, 60 lines, executable)
scripts/stop_mac.sh           (new, 15 lines, executable)
scripts/start_windows.ps1     (new, 51 lines)
scripts/stop_windows.ps1      (new, 16 lines)
```

All requirements from the spec met:
- ✓ Multi-stage Dockerfile (Node 20 → Python 3.12)
- ✓ uv installed from ghcr.io/astral-sh/uv:latest
- ✓ uv sync --frozen --no-dev
- ✓ NO texlive (Typst via pip)
- ✓ HEALTHCHECK: GET /api/health, 30s interval, 60s start-period
- ✓ Named volumes: resumedb-data, resumepdf-data
- ✓ .gitignore: updated without replacement
- ✓ db/.gitkeep: created
- ✓ .env.example: created
- ✓ 4 start/stop scripts (bash + PowerShell)
- ✓ All scripts are idempotent
- ✓ All committed

---

## Notes

- The Docker build will only succeed after Wave 2 creates `backend/pyproject.toml` and `backend/app/main.py`. This is expected and documented in the requirements.
- All scripts are designed to be idempotent (safe to run multiple times).
- The stop scripts do NOT remove volumes — data is preserved across restarts.
- The start scripts check for .env file to prevent silent failures.
- On macOS, the start_mac.sh script will automatically open the browser when the app becomes healthy.
- Test configuration uses LLM_MOCK=true for deterministic testing without API calls.

---

## Status: DONE

Implementation complete. All 4 tasks finished, all files committed, all requirements met.
