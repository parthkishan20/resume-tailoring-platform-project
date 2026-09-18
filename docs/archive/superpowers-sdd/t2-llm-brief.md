# T2 Task Brief — LLM Engineer

## Project Context
ResumeTailor: AI-powered resume tailoring workstation. You are Wave 1, LLM Engineer. Your work is fully independent of other Wave 1 agents — no other agent's output is needed. Wave 2 (Backend API Engineer) will import your ports.py and adapters.py to wire real LLM/PDF calls.

## Your Requirements
Read this file — it is your complete requirements spec with exact values to use verbatim:
`docs/superpowers/plans/2026-07-06-wave1-llm-engineer.md`

## Clarifications
- `backend/app/` directory already exists (created by T1 Database Engineer). Do NOT touch `database.py` or `schema.sql`.
- Create `backend/__init__.py` and `backend/app/__init__.py` only if they don't exist.
- For `mock.pdf`: create it with pure Python bytes — a minimal valid %PDF-1.4 structure. Do NOT use rendercv or any external tool.
- For `backend/tests/conftest.py`: check if it already exists before creating it. If it does, only add to it without removing existing content.
- Run tests with: `python -m pytest backend/tests/test_llm.py -v`
- LiteLLM, rendercv, and pymupdf are NOT installed yet (Wave 2 creates pyproject.toml). Write adapters.py code that compiles without errors but won't run without those deps. Tests use the mock/simulator pattern — no real LLM calls.
- The SimulatedBackendAPI in simulator.py must dispatch based on system prompt content: "ResumeTailor" → generation flow, "ResumeAuditor" → audit flow, "evaluation" in user message → evaluation flow.

## No Earlier-Task Interfaces to Consume
This is a Wave 1 agent. Do not read or import database.py.

## Produces (for Wave 2 to consume)
- `backend/app/ports.py` — LLMPort, PDFRenderPort, PDFExtractPort Protocol classes
- `backend/app/adapters.py` — LiteLLMAdapter, RendercvAdapter, MuPDFExtractAdapter
- `backend/app/simulator.py` — SimulatedBackendAPI class
- `backend/app/prompts.py` — GENERATION_SYSTEM_PROMPT, CRITIQUE_SYSTEM_PROMPT constants
- `backend/tests/fixtures/mock.pdf` — minimal valid PDF bytes
- `backend/tests/helpers/simulator.py` — ConfigurableBackendAPI test helper
- `backend/tests/test_llm.py` — full test suite

## Report File
Write your full report to:
/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.superpowers/sdd/t2-llm-report.md

Return ONLY: status, commit hash(es), one-line test summary, concerns.
