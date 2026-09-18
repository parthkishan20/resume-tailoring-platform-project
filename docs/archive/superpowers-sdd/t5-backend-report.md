# T5 Backend API Engineer — Implementation Report

## Status: DONE

---

## What Was Built

### Wave 1 Integration
All Wave 1 foundation files consumed as-is:
- `backend/app/database.py` — CRUD functions wrapped via `asyncio.to_thread()` in routes
- `backend/app/ports.py` — LLMPort, PDFRenderPort, PDFExtractPort protocols
- `backend/app/simulator.py` — SimulatedBackendAPI used by E2E mock path
- `backend/app/adapters.py` — LiteLLMAdapter, RenderCVAdapter, PyMuPDFAdapter

### New Files Created

| File | Purpose |
|---|---|
| `backend/pyproject.toml` | Project config; deps: fastapi, uvicorn, litellm, rendercv, pymupdf, pydantic-settings, python-multipart; dev: pytest, anyio[asyncio], httpx |
| `backend/app/config.py` | `Settings` (pydantic-settings) with LRU cache; reads OPENROUTER_API_KEY, LLM_MODEL, LLM_MOCK, DB_PATH, PDFS_DIR from env |
| `backend/app/backend_api.py` | `BackendAPI` facade: `complete()`, `stream()`, `render()`, `extract()`; `create_real_backend()` factory |
| `backend/app/deps.py` | `get_backend()` FastAPI dependency — prevents circular import (main → routes → deps, never routes → main) |
| `backend/app/main.py` | FastAPI app: exception handlers for all BackendError subtypes, startup event (init_db + mkdir), all 7 routers, optional static file mount |
| `backend/app/routes/health.py` | `GET /api/health` |
| `backend/app/routes/master_resume.py` | `GET/PUT/DELETE /api/master-resume`, `POST /api/master-resume/import` |
| `backend/app/routes/resumes.py` | `GET /api/resumes`, `POST /api/resumes/stream` (SSE 2-pass pipeline), `GET/PATCH/DELETE /api/resumes/{id}`, `GET /api/resumes/{id}/pdf`, `POST /api/resumes/{id}/render` |
| `backend/app/routes/chat.py` | `GET /api/chat`, `POST /api/chat/stream` (SSE), `DELETE /api/chat` |
| `backend/app/routes/rules.py` | `GET/PUT/DELETE /api/rules` |
| `backend/app/routes/system_prompt.py` | `GET/PUT/DELETE /api/system-prompt` |
| `backend/app/routes/evaluate.py` | `POST /api/evaluate/stream` (SSE) |

### Modified Files
- `backend/tests/conftest.py` — Extended (not replaced): kept existing litellm stub; added `sim` (ConfigurableBackendAPI) and `client` (httpx AsyncClient with dependency override) fixtures

### New Test Files (7)
All use `@pytest.mark.anyio` on async functions; no pytest-asyncio required.

---

## Test Results

```
57 passed, 0 failed, 2 warnings (deprecation: on_event)
```

Wave 1 tests (26 db + 13 llm) — all still passing after conftest merge.
Wave 2 route tests (18) — all passing.
The 3 ConfigurableBackendAPI tests previously skipped now pass.

---

## Key Decisions

### anyio over pytest-asyncio
Brief constraint: "Use `@pytest.mark.anyio` (NOT asyncio)". Used `anyio[asyncio]>=4.0.0` as dev dep. All async test functions decorated with `@pytest.mark.anyio`. The anyio pytest plugin (built into anyio) handles collection.

### deps.py circular import prevention
Routes import `get_backend` from `..deps`; `main.py` imports from `.deps` and re-exports it so `from app.main import get_backend` works in conftest for dependency override.

### PDFS_DIR monkeypatch in SSE test
Plan only monkeypatched `DB_PATH`. The SSE generation route also writes a PDF file to `PDFS_DIR` (default `/app/pdfs`). Added `monkeypatch.setenv("PDFS_DIR", str(tmp_path / "pdfs"))` to the test to fix the PermissionError that caused the error SSE event instead of done.

### on_event deprecation warning
Two deprecation warnings from FastAPI 0.111+ about `@app.on_event("startup")`. API still functional — kept to stay faithful to the plan. Can be migrated to lifespan context manager separately.

---

## Commits

1. `51a95e9` — feat(api): pyproject.toml, settings, BackendAPI facade, deps
2. `a9e24e2` — feat(api): FastAPI app, startup handler, health route, route stubs
3. `09d2d87` — feat(api): route unit tests — all endpoints covered

---

## SSE Format

All SSE routes emit exactly: `event: {type}\ndata: {json}\n\n`

Generation pipeline (2-pass):
1. GENERATION_SYSTEM_PROMPT → `complete()` → JSON `{"yaml_content": ...}` → draft_yaml
2. CRITIQUE_SYSTEM_PROMPT → `complete()` → strip `AUDIT_START..AUDIT_END` block → final_yaml
3. `render(final_yaml)` → PDF bytes → save to `PDFS_DIR/{id}.pdf`
4. `create_resume()` + `update_resume(pdf_path=...)` → SSE `done` event with full resume row

---

## Fix Session — 2026-07-06

### Status: DONE
### Commit: `d481e27`

### Changes Made

**Fix 1 — Spec SSE error codes in all three streaming routes**

Each generator now catches domain exceptions before the blanket `except Exception`, mapping them to spec-required codes:

| Exception | code |
|---|---|
| `LLMAuthError` | `LLM_AUTH_ERROR` |
| `LLMUnavailableError` | `LLM_UNAVAILABLE` |
| `RenderError` | `RENDER_FAILED` |
| `PDFExtractError` | `PDF_EXTRACT_FAILED` |
| fallback `Exception` | `GENERATION_FAILED` / `CHAT_FAILED` / `EVALUATION_FAILED` |

Files modified:
- `backend/app/routes/resumes.py` — added import from `..ports`; added 4 domain-specific handlers + fallback
- `backend/app/routes/chat.py` — added import from `..ports`; added `LLMAuthError` + `LLMUnavailableError` handlers + fallback
- `backend/app/routes/evaluate.py` — added import from `..ports`; added `LLMAuthError` + `LLMUnavailableError` handlers + fallback

**Fix 2 — SSE error-path tests**

Three new tests added (one per route):
- `test_routes_resumes.py::test_generate_resume_sse_error_llm_auth` — `set_complete_error(LLMAuthError(...))`, verifies `code == "LLM_AUTH_ERROR"` in SSE stream
- `test_routes_chat.py::test_chat_stream_error_llm_unavailable` — `set_stream_error(LLMUnavailableError(...))`, verifies `code == "LLM_UNAVAILABLE"`
- `test_routes_evaluate.py::test_evaluate_stream_error_llm_auth` — `set_complete_error(LLMAuthError(...))`, verifies `code == "LLM_AUTH_ERROR"`

**Fix 3 — Two-pass call count assertion in generation test**

In `test_generate_resume_sse_stream`, added after the `done` event assertion:
```python
assert sim.sim_llm.complete_call_count == 2
```
The existing single `set_complete_response` value works for both passes (Pass 1 parses JSON, Pass 2 uses it as raw YAML — no `AUDIT_END` present so `final_yaml = audit_response.strip()`).

### Test Results

```
60 passed, 0 failed, 2 warnings (deprecation: on_event)
```
All 60 tests pass including 3 new error-path tests and the updated two-pass count assertion.
