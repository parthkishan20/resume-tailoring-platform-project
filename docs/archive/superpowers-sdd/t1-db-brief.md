# T1 Task Brief — Database Engineer

## Project Context
ResumeTailor: an AI-powered resume tailoring workstation. You are Wave 1, Database Engineer. Your work is fully independent — no other agent's output is required before you start. Wave 2 (Backend API Engineer) will read your `backend/app/database.py` after you commit.

## Your Requirements
Read this file — it is your complete requirements spec with exact values to use verbatim:
`docs/superpowers/plans/2026-07-06-wave1-database-engineer.md`

## Clarifications
- Use Python 3.12 stdlib `sqlite3` only — no external DB deps whatsoever.
- `backend/app/database.py` must be standalone: it opens its own connection, creates tables (via schema.sql), and exposes CRUD functions. No FastAPI, no imports from other backend modules.
- `backend/tests/test_database.py` uses `unittest` (stdlib) with a temporary in-memory or temp-file SQLite DB — NOT the production DB path.
- Run tests using: `python -m pytest backend/tests/test_database.py -v` from the repo root (pytest is available globally via pip).
- If `backend/` directory doesn't exist yet, create it along with any needed `__init__.py` files.
- Commit frequently after each passing test suite as specified in the plan.

## No Earlier Task Interfaces
This is T1 — you produce the first output. No interfaces to consume.

## Produces (for Wave 2 to consume)
- `backend/db/schema.sql` — 6 CREATE TABLE statements
- `backend/app/database.py` — all CRUD functions with exact signatures as specified in the plan
- `backend/tests/test_database.py` — full test suite

## Report File
Write your full report (what you built, test results, self-review findings) to:
`/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.superpowers/sdd/t1-db-report.md`

Return to the controller ONLY: status (DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED), commit hash(es), one-line test summary, and any concerns.
