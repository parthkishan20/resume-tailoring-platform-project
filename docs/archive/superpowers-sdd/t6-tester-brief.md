# T6 Task Brief — Integration Tester (Wave 3)

## Project Context
ResumeTailor: AI-powered resume tailoring workstation. You are Wave 3, Integration Tester. All Wave 1 and Wave 2 agents have completed. Your job is to build the Docker container, run Playwright E2E tests against it with LLM_MOCK=true, and report any failures with the owning agent identified.

## Your Requirements
Read this file — it is your complete requirements spec with exact values to use verbatim:
`docs/superpowers/plans/2026-07-06-wave3-integration-tester.md`

## System Architecture (what you're testing)
- Single Docker container running on port 8000
- FastAPI backend at `/api/*` with SSE endpoints for generate, chat, evaluate
- Next.js 14 static frontend served from `backend/static/` (copied from `frontend/out/` at build time)
- SQLite database at `/app/db/resumedb.db` (in Docker volume)
- `LLM_MOCK=true` activates SimulatedBackendAPI — deterministic responses for all tests

## Mock Constants (for assertions)
These are imported from `backend/app/simulator.py` — use them in your Playwright test assertions:
- `MOCK_EVALUATION_RESULT.match_score = 72`
- `MOCK_EVALUATION_RESULT.missing_keywords[0] = "Kubernetes"`
- `MOCK_EVALUATION_RESULT.matched_keywords[0] = "Python"`
- `MOCK_CHAT_RESULT = "I've reviewed your resume and made some suggestions..."` (check the actual value in simulator.py)
- `MOCK_RESUME_NAME_FRAGMENT = "Mock User"` (fragment of the name in generated resume YAML)

## Key data-testid attributes available
All 19 testids from the frontend:
empty-state, yaml-editor, save-master-resume, resume-preview, pdf-import-zone,
job-description, generate-button, generated-resume-preview, resume-name,
chat-input, chat-send, chat-message, resume-list, resume-list-item,
sort-date, sort-jd, evaluate-button, evaluate-result, rules-form, **rules-toggle**

## Docker Build Context
Run `docker build -t resumetailor .` from the repo root. This MUST exit 0 before running any Playwright tests. If it fails, report BLOCKED with the build error.

## Report Format
Write your full report to:
/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/.superpowers/sdd/t6-tester-report.md

For any test failures, use this format:
```
SCENARIO: <N> — <name>
ASSERTION: <what failed>
OWNER: Frontend | Backend API | DevOps | triage
OBSERVED: <actual behavior>
```

Return ONLY: status, which scenarios passed/failed, any failure reports.
