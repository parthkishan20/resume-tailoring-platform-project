# T5 Task Brief — Backend API Engineer (Wave 2)

## Project Context
ResumeTailor: AI-powered resume tailoring workstation. You are Wave 2, Backend API Engineer. All Wave 1 agents have committed. You wire together the database layer and LLM/PDF adapters into a working FastAPI application.

## Your Requirements
Read this file — it is your complete requirements spec with exact values to use verbatim:
`docs/superpowers/plans/2026-07-06-wave2-backend-api-engineer.md`

## Wave 1 Outputs You Can Consume
Read these files before writing any route code (the plan says to do this as pre-work):
- `backend/app/database.py` — all CRUD function signatures
- `backend/app/ports.py` — LLMPort, PDFRenderPort, PDFExtractPort Protocol signatures
- `backend/app/simulator.py` — SimulatedBackendAPI class
- `backend/app/adapters.py` — LiteLLMAdapter, RendercvAdapter, MuPDFExtractAdapter

## Key Implementation Details
- `backend/pyproject.toml` does NOT exist yet — you create it (first task in the plan)
- Use `uv` for dependency management: `cd backend && uv init --no-workspace && uv add ...`
- OR write pyproject.toml directly (the plan has the complete file)
- Run tests with: `cd backend && uv run pytest tests/ -v` (after uv sync)
- `backend/app/deps.py` contains `get_backend()` to avoid circular imports (main.py imports routes, routes import get_backend)
- All long-running operations (generate, evaluate, chat) use SSE format: `event: <type>\ndata: <json>\n\n`
- SSE events: progress, token, done, error
- `LLM_MOCK=true` env var activates SimulatedBackendAPI (via settings.LLM_MOCK in config.py)
- Two-pass generation: GENERATION_SYSTEM_PROMPT → draft JSON → CRITIQUE_SYSTEM_PROMPT → audit → strip AUDIT_START..AUDIT_END block → final YAML → render PDF → save
- asyncio.to_thread() for all synchronous DB calls from async route handlers

## Important Notes from T2 (LLM Engineer)
- Tests use `@pytest.mark.anyio` (NOT `@pytest.mark.asyncio`) — pytest-anyio is available, pytest-asyncio is not installed yet
- conftest.py already has a litellm stub — do NOT replicate it; import from the existing conftest.py
- 3 ConfigurableBackendAPI tests in test_llm.py were skipped waiting for `app.backend_api.BackendAPI` — once you create BackendAPI, those tests will activate automatically
- litellm imports in adapters.py are lazy (inside methods) — this is intentional
- stream() returns a coroutine that returns an async generator: `async for chunk in await port.stream(messages):`

## Report File
Write your full report to:
/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.superpowers/sdd/t5-backend-report.md

Return ONLY: status, commit hash(es), one-line test summary, concerns.
