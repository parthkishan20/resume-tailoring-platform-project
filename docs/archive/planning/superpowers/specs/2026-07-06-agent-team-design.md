# Agent Team Design — ResumeTailor Build

**Date:** 2026-07-06  
**Project:** resume-tailoring-platform  
**Strategy:** Option B — Foundation-First, then Backend API

---

## 1. Overview

ResumeTailor is fully specced in `planning/PLAN.md` with zero code written. This document defines how a 6-agent team builds it across three sequential waves, maximising parallelism while eliminating intra-backend import risk.

The source of truth for all agents is `planning/PLAN.md`. Additional reference docs in `planning/` scope to specific agents as noted below. If anything in an agent's output conflicts with PLAN.md, PLAN.md wins.

---

## 2. Wave Structure

### Wave 1 — Foundation (4 agents in parallel)

| Agent | File Ownership | Primary References |
|---|---|---|
| Database Engineer | `backend/db/schema.sql`, `backend/app/database.py` | PLAN.md §6 |
| LLM Engineer | `backend/app/ports.py`, `backend/app/adapters.py`, `backend/app/simulator.py`, `backend/app/prompts.py` | `backendAPI_interface.md`, `backend_simulator.md`, `backend_API.md`, `example-Prompt.md` |
| Frontend Engineer | `frontend/` (entire directory) | PLAN.md §2, §7, §8 |
| DevOps Engineer | `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`, `scripts/`, `.env.example`, `.gitignore` | PLAN.md §9, `backend_API.md §2` |

Wave 1 agents own completely non-overlapping files. They can commit independently at any time.

### Wave 2 — Backend API (1 agent, after all Wave 1 agents commit)

| Agent | File Ownership | Primary References |
|---|---|---|
| Backend API Engineer | `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/routes/`, `backend/app/backend_api.py`, `backend/app/config.py`, `backend/tests/` | All planning docs + Wave 1 output (`database.py`, `ports.py`, `adapters.py`) |

The Backend API Engineer reads `database.py` and `ports.py` before writing any route code — it does not assume function signatures or exception types.

### Wave 3 — Integration Testing (1 agent, after Docker image builds)

| Agent | File Ownership | Primary References |
|---|---|---|
| Integration Tester | `test/` | PLAN.md §10, §11; `docker-compose.test.yml` |

The Integration Tester's first action is to run `docker build`. If that fails, it reports the error to DevOps before running any Playwright tests.

---

## 3. Agent Briefs

### Database Engineer

**Deliverables:**
- `backend/db/schema.sql` — all 6 tables (`master_resume`, `master_resume_history`, `generated_resumes`, `chat_messages`, `generation_rules`, `system_prompt`) with `user_id` columns defaulting to `"default"`
- `backend/app/database.py` — async SQLite functions covering every CRUD operation the routes require; lazy-init logic that creates tables and seeds defaults on first use; history pruning (keeps last 10 master resume versions per user)

**Unit tests:** All query functions tested with an in-memory SQLite DB. No mocking — real SQL execution.

**Definition of done:** Schema creates cleanly from empty; all CRUD functions pass unit tests.

---

### LLM Engineer

**Deliverables:**
- `backend/app/ports.py` — `LLMPort`, `PDFRenderPort`, `PDFExtractPort` protocols; exception hierarchy (`BackendError`, `LLMAuthError`, `LLMUnavailableError`, `RenderError`, `PDFExtractError`)
- `backend/app/adapters.py` — `LiteLLMAdapter`, `RenderCVAdapter`, `PyMuPDFAdapter` (use rendercv CLI subprocess; no LaTeX — rendercv v2.x uses Typst via pip)
- `backend/app/simulator.py` — `SimulatedBackendAPI` (Tier 1 E2E mock) with all fixed payloads from PLAN.md §11; reads mock PDF from `backend/tests/fixtures/mock.pdf`; `MOCK_CHAT_RESULT`, `MOCK_GENERATION_RESULT_YAML`, `MOCK_EVALUATION_RESULT`, `MOCK_IMPORT_YAML` constants exported for E2E test assertions
- `backend/app/prompts.py` — `GENERATION_SYSTEM_PROMPT` and `CRITIQUE_SYSTEM_PROMPT` from `example-Prompt.md`
- `backend/tests/fixtures/mock.pdf` — committed static PDF fixture generated from `MOCK_GENERATION_RESULT_YAML`
- `backend/tests/helpers/simulator.py` — `SimulatedLLMPort`, `SimulatedPDFRenderPort`, `SimulatedPDFExtractPort`, `ConfigurableBackendAPI` (Tier 2 unit-test simulator)

**Unit tests:** Adapter error mapping (LiteLLM exception types → port exception types); `SimulatedBackendAPI` returns correct payload for each operation type.

**Definition of done:** All unit tests pass; `mock.pdf` fixture committed.

---

### Frontend Engineer

**Deliverables:**
- Full Next.js 14 TypeScript project in `frontend/` with `output: 'export'`
- Tailwind CSS with exact dark theme tokens from PLAN.md §2 (monochrome — do not use conventional red/green/yellow for semantic states)
- Font: Inter
- Single-page layout: header + collapsible panels (YAML editor + live preview, generation form, resume log, evaluation, chat)
- Guided empty state (no master resume): sample YAML download, rendered preview, setup instructions, drag-and-drop PDF import zone
- SSE stream handling for chat, generate, and evaluate — progress indicators, token streaming, done/error events
- PDF preview via `<iframe>` with blob URL
- Light/dark theme toggle
- `data-testid` attributes on all interactive elements (required by Integration Tester)
- API client calling `/api/*` — same-origin, no CORS config needed
- Mock API responses for local development (returns fixture data when backend unreachable)

**Unit tests:** React Testing Library — component rendering, master resume editor, resume list sort controls, chat message rendering, loading states.

**Definition of done:** `npm run build` produces static export; unit tests pass.

---

### DevOps Engineer

**Deliverables:**
- `Dockerfile` — multi-stage build: Stage 1 Node 20 slim (builds frontend static export); Stage 2 Python 3.12 slim (installs uv, installs rendercv + deps via `uv sync`, copies static build into `backend/static/`, exposes port 8000, HEALTHCHECK on `/api/health`, CMD: uvicorn)
- **No texlive** — rendercv v2.x uses Typst (installed as a pip dependency of rendercv); no system TeX required
- `docker-compose.yml` — mounts `resumedb-data:/app/db` and `resumepdf-data:/app/pdfs`, maps port 8000, passes `.env` file
- `docker-compose.test.yml` — app container with `LLM_MOCK=true` + Playwright container
- `scripts/start_mac.sh` — builds image if needed, runs container, prints URL, optionally opens browser; idempotent
- `scripts/stop_mac.sh` — stops and removes container, does NOT remove volumes; idempotent
- `scripts/start_windows.ps1` / `scripts/stop_windows.ps1` — PowerShell equivalents
- `.env.example` — `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_MOCK` with comments
- `.gitignore` — ignores `.env`, `db/resumedb.db`, `frontend/.next/`, `frontend/out/`, `backend/.venv/`, `__pycache__/`, `*.pyc`

**No unit tests.** Definition of done: `docker build -t resumetailor .` succeeds from the repo root.

---

### Backend API Engineer (Wave 2)

**Pre-condition:** Reads `backend/app/database.py` and `backend/app/ports.py` before writing any route code.

**Deliverables:**
- `backend/pyproject.toml` — uv project; deps: `fastapi`, `uvicorn[standard]`, `litellm`, `rendercv`, `pymupdf`, `pydantic-settings`; dev deps: `pytest`, `pytest-asyncio`, `httpx`
- `backend/app/config.py` — pydantic-settings `Settings` class reading `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_MOCK`
- `backend/app/backend_api.py` — `BackendAPI` facade + `create_real_backend()` factory
- `backend/app/main.py` — FastAPI app; exception handlers for all port error types; static file serving from `backend/static/` (Dockerfile copies frontend export there at build time); dependency injection via `get_backend()`; mounts all routers
- `backend/app/routes/` — one file per domain:
  - `health.py` — `GET /api/health`
  - `master_resume.py` — `GET/PUT/DELETE /api/master-resume`, `POST /api/master-resume/import`
  - `resumes.py` — `GET /api/resumes`, `POST /api/resumes/stream`, `GET/PATCH/DELETE /api/resumes/{id}`, `GET /api/resumes/{id}/pdf`, `POST /api/resumes/{id}/render`
  - `chat.py` — `GET/DELETE /api/chat`, `POST /api/chat/stream`
  - `rules.py` — `GET/PUT/DELETE /api/rules`
  - `system_prompt.py` — `GET/PUT/DELETE /api/system-prompt`
  - `evaluate.py` — `POST /api/evaluate/stream`
- `backend/tests/` — unit tests for every route using `ConfigurableBackendAPI`; covers happy path + all error paths (LLMUnavailableError → 503, RenderError → 500, 404 for unknown IDs, 422 for invalid YAML, etc.)

**Definition of done:** All unit tests pass; `uvicorn backend.app.main:app` starts without errors.

---

### Integration Tester (Wave 3)

**Pre-condition:** `docker build -t resumetailor .` succeeds.

**Deliverables:**
- `test/e2e/` — Playwright TypeScript test suite
- `test/fixtures/` — any static fixtures needed (sample YAML, mock JD text)
- All 8 scenarios from PLAN.md §10 with `LLM_MOCK=true`:
  1. Fresh start: empty state renders, sample YAML and preview visible
  2. Master resume: create from sample, edit YAML, live preview updates
  3. PDF upload: drag-and-drop triggers import, converted YAML appears
  4. Resume generation: paste JD, generate, PDF preview renders
  5. Chat (mocked): send message, receive response, action reflected in UI
  6. Resume list: sort by date and by JD works correctly
  7. Evaluation: score and critique displayed for resume + JD pair
  8. Rules: update a rule, regenerate, rule applied in output

**Failure reporting format:**
```
SCENARIO: <name>
ASSERTION: <what failed>
OWNER: <Frontend | Backend API | DevOps>
OBSERVED: <what actually happened>
```

If the cause is ambiguous, report `OWNER: triage` with full observed output.

**Definition of done:** All 8 scenarios pass against the `LLM_MOCK=true` Docker container.

---

## 4. Integration Handoff Rules

1. **Wave 1 → Wave 2:** Backend API Engineer waits for all four Wave 1 agents to commit before starting. It reads `database.py` function signatures and `ports.py` exception types directly — no assumptions.
2. **Wave 2 → Wave 3:** Docker image must build successfully before any Playwright tests run. First Integration Tester action is `docker build`.
3. **Fix loop:** Integration Tester reports failures with owner attribution. Owning agent fixes, Docker rebuilds, Integration Tester re-runs only the affected scenario.
4. **No scope creep:** No agent adds endpoints, UI panels, database tables, or behaviors not specified in PLAN.md.
