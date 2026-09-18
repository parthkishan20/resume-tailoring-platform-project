# T6 Integration Tester Report

**Date:** 2026-07-06
**Status:** DONE_WITH_CONCERNS
**Docker build:** PASS (exit 0)
**Container runtime:** PASS (all 13 tests across 8 scenarios pass)

---

## Test Results Summary

| Scenario | Tests | Result |
|----------|-------|--------|
| 1 — Fresh start | 3 | PASS |
| 2 — Master resume CRUD | 3 | PASS |
| 3 — PDF upload / import | 1 | PASS |
| 4 — Resume generation | 1 | PASS |
| 5 — Chat assistant | 1 | PASS |
| 6 — Resume list sort | 1 | PASS |
| 7 — Evaluation | 1 | PASS |
| 8 — Generation rules | 2 | PASS |

**Total: 13/13 passed**

---

## Bugs Found and Fixed

Three bugs were discovered during integration testing. All were fixed before the final run.

### Bug 1 — Dockerfile WORKDIR (DevOps)

**File:** `Dockerfile`

The final `WORKDIR` directive was set to `/app` but the uvicorn CMD uses `app.main:app`, which requires Python to find the `app` package from `/app/backend`. The container exited immediately with `ModuleNotFoundError: No module named 'app'`.

**Fix:** Changed final `WORKDIR /app` to `WORKDIR /app/backend`.

**Severity:** Critical — container would not start without this fix.

---

### Bug 2 — SimulatedBackendAPI PDF import path (Backend API)

**File:** `backend/app/simulator.py`, `SimulatedBackendAPI.complete()`

The `complete()` method returned `json.dumps(MOCK_CHAT_RESULT)` for the PDF import path. The import route (`POST /api/master-resume/import`) expects `{"yaml_content": "..."}` but `MOCK_CHAT_RESULT` has shape `{"text": "...", "action": null}`. This caused a `KeyError: 'yaml_content'` and a 500 response, meaning PDF import never created a master resume in mock mode.

**Fix:** Added check — if `response_format` is provided (import passes it, chat does not), return `json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML})`.

**Severity:** High — Scenario 3 (PDF import) completely broken in mock mode.

---

### Bug 3 — Evaluation test used wrong textarea (Tester)

**File:** `test/e2e/07-evaluation.spec.ts`

The EvaluationPanel textarea has no `data-testid`. The plan spec used `page.locator("textarea").last()`. When the evaluate tab is active, two textareas are visible: the evaluation JD textarea and the chat panel textarea. `.last()` selected the chat textarea, leaving the evaluation textarea empty, so the Evaluate button remained disabled.

**Fix:** Changed locator to `page.locator("textarea[placeholder*='Paste the job description']")`.

**Severity:** Medium — test-only issue; the frontend UI works correctly.

---

## Port Note

Port 8000 was occupied by a separate local process on the test machine. The test container was mapped to port 8080 (`-p 8080:8000`) and Playwright tests run with `BASE_URL=http://localhost:8080`. The `docker-compose.test.yml` was not modified — it uses internal port 8000 correctly for container-to-container routing. On a clean CI environment, the standard `-p 8000:8000` mapping will work.

---

## Infrastructure Created

```
test/
├── package.json
├── playwright.config.ts          (workers: 1 to prevent inter-test state conflicts)
├── fixtures/
│   ├── sample-resume.yaml
│   ├── sample-jd.txt
│   └── mock-constants.ts         (matches simulator.py MOCK_* constants)
└── e2e/
    ├── 01-fresh-start.spec.ts
    ├── 02-master-resume.spec.ts
    ├── 03-pdf-upload.spec.ts
    ├── 04-generation.spec.ts
    ├── 05-chat.spec.ts
    ├── 06-resume-list-sort.spec.ts
    ├── 07-evaluation.spec.ts
    └── 08-rules.spec.ts
```

## How to Run

```bash
# Build image
docker build -t resumetailor .

# Start container (adjust port if 8000 is occupied)
docker run -d --name resumetailor-test -p 8080:8000 \
  -e LLM_MOCK=true -e OPENROUTER_API_KEY=mock-key \
  -v resumedb-test:/app/db -v resumepdf-test:/app/pdfs resumetailor

# Wait for health
until curl -sf http://localhost:8080/api/health; do sleep 3; done

# Run tests
cd test && npm install && npx playwright install chromium
BASE_URL=http://localhost:8080 npx playwright test --reporter=list

# Cleanup
docker stop resumetailor-test && docker rm resumetailor-test
docker volume rm resumedb-test resumepdf-test
```

---

## Recommendations for Owning Agents

1. **Frontend:** Add `data-testid="evaluate-jd"` to the EvaluationPanel textarea so tests can target it unambiguously without relying on placeholder text.

2. **Backend API:** The `SimulatedBackendAPI.complete()` fallthrough should ideally have explicit handling for the import system prompt (e.g., check `"resume parser"` in system) rather than relying on `response_format` presence. The current fix works but is fragile if future endpoints also use `response_format`.
