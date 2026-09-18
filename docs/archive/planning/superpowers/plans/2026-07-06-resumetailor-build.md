# ResumeTailor — Agent Team Build Plan (Master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ResumeTailor from zero using a 6-agent team across 3 sequential waves.

**Architecture:** Wave 1 — four agents build non-overlapping foundation layers in parallel. Wave 2 — one agent wires them into a working FastAPI app. Wave 3 — one agent validates the full system end-to-end with Playwright.

**Tech Stack:** Next.js 14 (TypeScript, static export), FastAPI (Python 3.12/uv), SQLite (stdlib sqlite3), LiteLLM → OpenRouter, rendercv + Typst (PDF via pip), Playwright (E2E), Docker (single container, port 8000)

## Global Constraints

- `planning/PLAN.md` is the authoritative spec — no agent invents endpoints, tables, or UI not in it
- Python 3.12+, Node 20+
- Single Docker container, port 8000 only
- No auth — single user, `user_id` always `"default"`
- Dark theme only on first load; monochrome semantic tokens (`error`/`warning`/`success` are grey — NOT red/green/yellow)
- Font: Inter (sans-serif)
- No texlive — rendercv v2.x uses Typst installed as a pip dep; no system TeX
- All long-running LLM ops use SSE (`text/event-stream`)
- `LLM_MOCK=true` env var activates `SimulatedBackendAPI` — required for all E2E tests

---

## Wave 1 — Foundation (run all 4 agents in parallel)

**Start condition:** This file exists. No Wave 1 agent waits for any other.

| Agent | Plan File | Owns |
|---|---|---|
| Database Engineer | `2026-07-06-wave1-database-engineer.md` | `backend/db/schema.sql`, `backend/app/database.py`, `backend/tests/test_database.py` |
| LLM Engineer | `2026-07-06-wave1-llm-engineer.md` | `backend/app/ports.py`, `backend/app/adapters.py`, `backend/app/simulator.py`, `backend/app/prompts.py`, `backend/tests/fixtures/mock.pdf`, `backend/tests/helpers/simulator.py`, `backend/tests/test_llm.py` |
| Frontend Engineer | `2026-07-06-wave1-frontend-engineer.md` | `frontend/` (entire directory) |
| DevOps Engineer | `2026-07-06-wave1-devops-engineer.md` | `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`, `scripts/`, `.env.example`, `.gitignore`, `db/.gitkeep` |

**Wave 1 done when:** All four agents have committed. Each agent's definition of done is in their plan.

---

## Wave 2 — Backend API (after Wave 1 complete)

**Start condition:** All four Wave 1 agents have committed their work.

**Pre-work:** Read `backend/app/database.py` and `backend/app/ports.py` before writing any route code.

| Agent | Plan File | Owns |
|---|---|---|
| Backend API Engineer | `2026-07-06-wave2-backend-api-engineer.md` | `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/routes/`, `backend/app/backend_api.py`, `backend/app/config.py`, `backend/tests/test_routes_*.py` |

**Wave 2 done when:** All route unit tests pass; `docker build -t resumetailor .` succeeds.

---

## Wave 3 — Integration Testing (after Docker build succeeds)

**Start condition:** `docker build -t resumetailor .` exits 0.

| Agent | Plan File | Owns |
|---|---|---|
| Integration Tester | `2026-07-06-wave3-integration-tester.md` | `test/` |

**Wave 3 done when:** All 8 E2E scenarios pass against the `LLM_MOCK=true` container.

---

## Fix Loop (Wave 3 failures)

When the Integration Tester reports a failure:

1. Tester posts structured failure report (format in `2026-07-06-wave3-integration-tester.md`)
2. Owning agent (Frontend / Backend API / DevOps) fixes the specific issue
3. `docker build -t resumetailor .` re-runs
4. Integration Tester re-runs only the affected scenario
5. Repeat until all 8 scenarios pass
