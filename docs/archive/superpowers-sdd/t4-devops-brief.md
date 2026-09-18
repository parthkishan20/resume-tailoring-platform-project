# T4 Task Brief — DevOps Engineer

## Project Context
ResumeTailor: AI-powered resume tailoring workstation. You are Wave 1, DevOps Engineer. Your work owns the Docker build, docker-compose files, and start/stop scripts. Wave 1 frontend is complete (frontend/ exists with next.config.js output: 'export'). Wave 1 backend foundation files exist in backend/app/ (database.py, ports.py, adapters.py, simulator.py, prompts.py). Wave 2 Backend API Engineer will create backend/pyproject.toml and backend/app/main.py — so `docker build` cannot succeed until Wave 2 is done.

## Your Requirements
Read this file — it is your complete requirements spec with exact values to use verbatim:
`docs/superpowers/plans/2026-07-06-wave1-devops-engineer.md`

## Clarifications
- A `.gitignore` already exists at the repo root (created by T2 LLM Engineer). DO NOT overwrite it — only ADD the missing frontend and backend entries if they're not already there. Current .gitignore covers `__pycache__/`, `*.py[cod]`, `.venv/`, `.env`, `.pytest_cache/`, `.mypy_cache/`, `.DS_Store`, `node_modules/`, `frontend/.next/`, `frontend/out/`, `frontend/node_modules/`. Check what's missing from the DevOps plan's .gitignore spec and add only the missing lines.
- The `db/` directory does NOT need to be created — it will be created by the Docker volume mount at runtime. Just create `db/.gitkeep` if specified.
- `backend/pyproject.toml` does NOT exist yet (Wave 2 creates it). The Dockerfile will still fail to build until Wave 2 completes — that's expected. The docker build step in your plan is a "definition of done" that happens after Wave 2, not something you need to verify now.
- For Dockerfile: use `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv` to install uv. NO texlive — rendercv uses Typst installed as a pip dep.
- `.env.example` should be committed; `.env` is gitignored.

## No Earlier-Task Interfaces to Consume
This is a Wave 1 agent. You do not need to read or import any backend Python code.

## Produces
- `Dockerfile` — multi-stage Node 20 → Python 3.12
- `docker-compose.yml` and `docker-compose.test.yml`
- `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_windows.ps1`
- `.env.example`
- `db/.gitkeep`
- Updated `.gitignore` (add missing entries only — don't replace the file)

## Report File
Write your full report to:
/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.superpowers/sdd/t4-devops-report.md

Return ONLY: status, commit hash(es), one-line summary, concerns.
