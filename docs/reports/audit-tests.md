# Test Suite & Quality Gates Audit — resume-tailoring-platform

Repo: `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform`
Stack: FastAPI backend (`backend/app`, 2080 LOC) · Next.js 14 frontend (`frontend/src`, 1729 LOC) · Playwright e2e (`test/`)
Audit date: 2026-09-18. Read-only; no files modified.

Measured on this machine:

| Suite | Files | Tests | Wall time | Result |
|---|---|---|---|---|
| `backend/` pytest | 10 test modules (1252 LOC incl. conftest/helpers) | 89 | 15.7 s | 89 passed |
| `frontend/` jest | 3 | 6 | 7.5 s | 6 passed |
| `test/` Playwright | 8 specs | 10 | not runnable in sandbox | last-run.json: passed |

Source-to-test ratio: backend 2080 LOC / ~1100 LOC tests. Frontend **1729 LOC / 97 LOC tests (6 tests)**.

---

## P0

### P0-1. Order-dependent test that fails in isolation — `backend/tests/test_routes_master_resume.py:76`

`test_import_pdf_returns_yaml` never sets `DB_PATH` and never clears the settings cache. It passes only because `test_preview_master_resume_not_found` (line 64) ran first **in the same file** and left `get_settings`'s `lru_cache` populated with a `tmp_path` DB. Verified directly:

```
$ .venv/bin/python -m pytest -q tests/test_routes_master_resume.py::test_import_pdf_returns_yaml
app/routes/master_resume.py:157: in import_pdf
    row = await asyncio.to_thread(upsert_master_resume, _db_path(), yaml_content)
db_path = '/app/db/resumedb.db', yaml_content = 'cv:\n  name: John Doe\n'
E   sqlite3.OperationalError: unable to open database file
app/database.py:70: OperationalError
1 failed in 0.71s
```

Any `-k` filter, test shard, `--last-failed`, IDE single-test run, or `pytest-randomly` breaks it.

The root cause is broader than one test. `get_settings` is `@lru_cache(maxsize=1)` (`backend/app/config.py:21-23`). **21 tests call `get_settings.cache_clear()` on entry and none call it on exit**, so every test leaks a stale `Settings` object pointing at a now-deleted `tmp_path` into whatever runs next. The same applies to `_backend()` which is also `@lru_cache(maxsize=1)` (`backend/app/deps.py:7-13`).

Full list of the leaking call sites:
`test_routes_chat.py:9, 19, 34, 57` · `test_routes_resumes.py:10, 23, 81, 109, 118` · `test_routes_rules.py:7, 19, 33, 44` · `test_routes_master_resume.py:9, 21, 37, 50, 67` · `test_routes_system_prompt.py:7, 17`

### P0-2. No CI and no quality gates of any kind

There is **no `.github/` directory** and no CI configuration anywhere in the repo (`find .github -type f` → empty). Nothing runs the 89 backend tests, 6 frontend tests, or 8 e2e specs on any push, PR, or merge.

What is missing, verified against the actual config files:

| Gate | Status | Evidence |
|---|---|---|
| Python lint (ruff/flake8) | **absent** | not in `backend/pyproject.toml:15-20` dev group; `importlib.util.find_spec("ruff")` → `False` in `backend/.venv` |
| Python format (black/ruff format) | **absent** | same |
| Python types (mypy) | **absent** | `find_spec("mypy")` → `False`; no `mypy.ini`, no `[tool.mypy]` |
| Python coverage | **absent** | `find_spec("coverage")` and `find_spec("pytest_cov")` → `False`; no `[tool.coverage]`; no `--cov-fail-under` |
| pytest config | **2 lines** | `backend/pyproject.toml:22-23` is `[tool.pytest.ini_options]` + `testpaths = ["tests"]`. No `addopts`, no `--strict-markers`, no `filterwarnings = error`, no `-p randomly` |
| ESLint | **absent** | `frontend/package.json:20-34` has **zero** lint dependencies — no `eslint`, no `eslint-config-next`. No `.eslintrc*`, no `eslint.config.*` anywhere. No `lint` script. `next lint` would fail on first invocation. |
| Prettier | **absent** | not a dependency, no config |
| TypeScript check | **not wired** | `frontend/tsconfig.json:12` sets `"strict": true` and `"noEmit": true`, but there is **no `typecheck` script** and nothing invokes `tsc`. Type errors surface only incidentally inside `next build` during `docker build` (`Dockerfile:10`). |
| JS coverage | **absent** | no `collectCoverage`, no `coverageThreshold` in the `jest` block (`frontend/package.json:36-55`) |
| Pre-commit hooks | **absent** | no `.pre-commit-config.yaml` |

`frontend/package.json:9` is `"test": "jest --passWithNoTests"` — **deleting every frontend test file still exits 0.**

The only thing resembling a gate is `Dockerfile:10` (`npm run build`), which will fail the image build on a TS error but runs no tests.

### P0-3. E2E suite is neither hermetic nor isolated, and can destroy production data

`test/playwright.config.ts:10`:
```ts
baseURL: process.env.BASE_URL ?? "http://localhost:8000",
```
Port 8000 is hardcoded as the default. Both compose files bind host port 8000:
- `docker-compose.yml:6-13` — **dev/production** stack: `ports: ["8000:8000"]`, `env_file: .env` (a **real** `OPENAI_API_KEY`), persistent named volumes `resumedb-data` / `resumepdf-data`, `restart: unless-stopped`.
- `docker-compose.test.yml:8-12` — test stack: `ports: ["8000:8000"]`, `LLM_MOCK=true`, named volumes `test-db` / `test-pdfs`.

`scripts/start_mac.sh:7` and `scripts/start_windows.ps1:6` also hardcode `PORT=8000` with `--restart unless-stopped`, so the dev container comes back automatically after a machine reboot.

Consequences:

1. **Port collision.** Bringing up the test stack while the dev container is running fails the bind. (Checked live: port 8000 is currently free and the Docker socket is not reachable from this sandbox, so this is a structural hazard rather than a currently-active failure — but the configuration guarantees it recurs.)
2. **Silent cross-stack testing — the severe case.** If the dev container holds 8000 and a developer runs `cd test && npx playwright test` (exactly what `README.md:109-110` instructs), Playwright drives the **production container with a live API key against the user's real resume data**. Every spec's `beforeEach` is a destructive API call against whatever answers on 8000:
   - `test/e2e/01-fresh-start.spec.ts:7-8` — `DELETE /api/master-resume`, `DELETE /api/chat`
   - `test/e2e/02-master-resume.spec.ts:10` — `DELETE /api/master-resume`
   - `test/e2e/03-pdf-upload.spec.ts:6` — `DELETE /api/master-resume`
   - `test/e2e/05-chat.spec.ts:11` — `DELETE /api/chat`
   - `test/e2e/08-rules.spec.ts:12` — `DELETE /api/rules`

   and `04`, `05`, `06`, `07`, `08` all `PUT /api/master-resume` with the mock fixture, overwriting the real one. The `.catch(() => {})` on several of these hides the fact that they succeeded against the wrong target.
3. **No state isolation even in the correct stack.** `docker-compose.test.yml:11-12,37-39` uses **named** volumes (`test-db`, `test-pdfs`), which persist across runs. There is no global setup, no global teardown, no per-spec DB reset beyond the ad-hoc `DELETE`s above. `generated_resumes` rows and PDF files accumulate indefinitely.
4. **A spec that depends on that residue.** `test/e2e/06-resume-list-sort.spec.ts:12-14`:
   ```ts
   await request.post("/api/resumes/stream", {
     data: { job_description: "Alpha Corp — Engineer" },
   }).catch(() => {}); // SSE endpoint, response may not parse as JSON
   ```
   The error is swallowed and completion is never awaited (an SSE stream returns headers immediately; the body may still be generating). The test's assertions at lines 29 and 34 (`resume-list-item` first item visible) therefore pass on **leftover rows from previous runs** — the spec would stay green with generation entirely broken, and would fail on a genuinely fresh volume.
5. **Cannot run in CI without Docker-in-Docker.** Playwright only runs via the `playwright` service in `docker-compose.test.yml:25-35`. `test/package.json:5-9` has no `webServer` block, so a local `npx playwright test` silently assumes a manually started container on 8000.

---

## P1

### P1-4. Tests that assert nothing meaningful

| Location | Test | Why it is hollow |
|---|---|---|
| `backend/tests/test_llm.py:148` | `test_mock_constants_match_plan` | Asserts module constants against themselves. Line 154 — `assert MOCK_IMPORT_YAML == MOCK_GENERATION_RESULT_YAML` — restates the alias assignment at `app/simulator.py:59`. Cannot fail unless someone edits a constant, at which point it fails without indicating any defect. |
| `backend/tests/test_llm.py:35` | `test_llm_port_is_protocol` | `issubclass(LLMPort, Protocol)` is true by construction for every `Protocol` subclass. Zero information. |
| `backend/tests/test_llm.py:40` | `test_ports_are_runtime_checkable` | `runtime_checkable` protocols check **method names only**, never signatures or arity. A `FakeLLM` whose `complete(self)` took no arguments would still satisfy `isinstance`. Proves nothing about conformance. |
| `backend/tests/test_routes_master_resume.py:47-60` | `test_preview_master_resume` | Asserts `response.content[:4] == b"%PDF"`, but `SimulatedPDFRenderPort._response` is hardcoded `b"%PDF-1.4 mock"` (`tests/helpers/simulator.py:64`). The test verifies the stub's own constant. The route's real work — `normalize_to_rendercv(row["yaml_content"])` at `routes/master_resume.py:120` — is never inspected. |
| `backend/tests/test_routes_master_resume.py:87-89` | `test_import_pdf_returns_yaml` | Only `assert "yaml_content" in data`. The route's actual transformation at `master_resume.py:156` (`normalize_to_rendercv(json.loads(result_str)["yaml_content"])`) is unverified, as is the persisted row. |
| `backend/tests/test_routes_chat.py:55-60` | `test_clear_chat` | Deletes from an empty DB and asserts 204. Never inserts a message first, so it cannot detect a `clear_chat` that deletes nothing. |
| `backend/tests/test_routes_resumes.py:8-16` | `test_list_resumes_empty` | Asserts an empty list from an empty DB — no insert, so no ordering, pagination, or serialization is exercised. (Redundant with `test_database.py:144`.) |
| `frontend/src/__tests__/ChatPanel.test.tsx:19-31` | `displays message after send` | `expect(screen.getAllByTestId("chat-message").length).toBeGreaterThan(0)` — `ChatPanel.tsx:33-36` appends the **user's own** message optimistically before the SSE stream opens. **This assertion passes with the entire `sse` mock removed.** The test named "displays message after send" never checks that the assistant reply rendered, never checks the streamed text, never checks `sse.readSseStream` was called with the right path/body. |
| `frontend/src/__tests__/MasterResumePanel.test.tsx:33-38` | `yaml-editor testid is present` | Asserts a `data-testid` exists (`getAllByTestId(...).length >= 1`). No behavior at all; the test's own comment acknowledges the testid is duplicated across the wrapper and the mocked CodeMirror. |
| `test/e2e/02-master-resume.spec.ts:20-22` | `load sample, edit YAML, save…` | Clicks save, then asserts **the save button is still visible**. Passes if the save request 500s. |
| `test/e2e/02-master-resume.spec.ts:25-39` | `edit YAML content and save` | Named "edit" — clicks the editor at line 35 but **types nothing**, then saves unmodified content and again asserts only that the button is visible (line 38). |
| `test/e2e/08-rules.spec.ts:22-27` | `rules form is visible and can update a value` | Fills an input, blurs to trigger the save, then asserts **the form is still visible**. Never reads the value back via `GET /api/rules`, never checks persistence. |
| `test/e2e/08-rules.spec.ts:30-45` | `generate after rule change works` | Sets `experience.max_entries = 1` then asserts a preview appears. Never verifies the rule affected the output — and cannot, because the simulator returns a fixed YAML regardless (`app/simulator.py:79-82`). |
| `test/e2e/01-fresh-start.spec.ts:11-24` | all three | Pure `toBeVisible()` smoke assertions on a static empty state. Reasonable as smoke tests; noted so the suite's real coverage isn't overstated. |

### P1-5. Over-mocked: `resume-preview` is the same testid on success, loading, AND error

`frontend/src/components/PdfPreview.tsx` puts the identical `data-testid={testId}` on all three render branches:
- line 42 — the **error** div (`Preview failed (500)`)
- line 49 — the **loading** spinner (`Rendering PDF…`)
- line 57 — the **success** iframe

So these e2e assertions are satisfied by a red error box:
- `test/e2e/02-master-resume.spec.ts:47` — `expect(page.locator("[data-testid=resume-preview]")).toBeVisible()`
- `test/e2e/04-generation.spec.ts:24` — `expect(page.locator("[data-testid=generated-resume-preview]")).toBeVisible({ timeout: 30_000 })`
- `test/e2e/08-rules.spec.ts:42-44` — same locator

**The generation and PDF-render e2e assertions cannot distinguish success from failure.** These are the only end-to-end checks of the core feature.

### P1-6. Mock PDF renders blank — confirmed by inspection

`backend/tests/fixtures/mock.pdf` is 313 bytes. Hex dump of the full file shows:
```
%PDF-1.4
1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj
2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj
3 0 obj<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>endobj
xref … trailer<</Size 4 /Root 1 0 R>> startxref 190 %%EOF
```
The single `/Page` has **no `/Contents` stream and no `/Resources`** — it is a structurally valid, permanently blank US-Letter page.

`app/simulator.py:6` and `:103-104`:
```python
_FIXTURE_PDF = Path(__file__).parent.parent / "tests" / "fixtures" / "mock.pdf"
async def render(self, yaml_content: str) -> bytes:
    return _FIXTURE_PDF.read_bytes()
```
Under `LLM_MOCK=true` — which is exactly the e2e configuration (`docker-compose.test.yml:14`) — **every** PDF in **every** e2e run is this blank page, regardless of input YAML. No e2e test can detect that rendering produced wrong content, only that *some* bytes arrived. Combined with P1-5, the entire render path is e2e-unverified end to end.

The same blank fixture is reachable in `test/e2e/03-pdf-upload.spec.ts:15-22`, which inlines a byte-identical minimal PDF as the upload payload.

### P1-7. LLM adapter tests validate against a fake `litellm`, not the real one

`backend/tests/conftest.py:25-58` defines four hand-rolled exception classes and installs stub modules:
```python
sys.modules.setdefault("litellm", _litellm_module)
sys.modules.setdefault("litellm.exceptions", _exc_module)
```
`app/adapters.py:17` then resolves `import litellm.exceptions as llm_exc` to those stubs. So `test_llm.py:62-82` proves the `except` clauses catch classes **the test itself defined**.

If litellm renamed or moved `ServiceUnavailableError`, `_llm_exceptions()` (`app/adapters.py:15-22`) would raise `AttributeError` in production while the suite stayed green. The real library **is** installed in `backend/.venv` and currently exposes all four names (verified: `AuthenticationError`, `RateLimitError`, `ServiceUnavailableError`, `APIConnectionError` → all `True`), so the stub buys nothing and only hides the contract.

Related stale scaffolding around this:
- `conftest.py:1-9` docstring claims litellm is "not installed until Wave 2 adds pyproject.toml" — it is, `backend/pyproject.toml:8`.
- `tests/helpers/simulator.py:1-8` claims the file "will raise an ImportError at import time — that is expected and handled in test_llm.py via pytest.skip()". `app/backend_api.py` exists; it does not.
- `test_llm.py:190, 204, 216` — three `try: … except ImportError: pytest.skip("app.backend_api not yet available (Wave 2)")` guards are dead code.

### P1-8. Global env mutation leaks across the whole test session

`app/adapters.py:26-28`:
```python
def __init__(self, model: str, api_key: str) -> None:
    self._model = model
    os.environ["OPENAI_API_KEY"] = api_key
```
`test_llm.py:64` and `test_llm.py:76` construct `LiteLLMAdapter(model="openrouter/test/model", api_key="key")`, **permanently overwriting the process's `OPENAI_API_KEY`** for every subsequent test and anything reading it later. No `monkeypatch`, no restore. (A design smell in the adapter as well as a test-hygiene defect.)

### P1-9. No per-test DB isolation; two different strategies, one of them broken

`backend/tests/test_database.py:15-22` uses a proper isolated fixture:
```python
@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    yield db_path
    if os.path.exists(db_path): os.unlink(db_path)
```
This is correct and is why the 24 `test_database.py` tests are the healthiest in the repo.

Every **route** test instead open-codes a three-line ritual, copy-pasted **21 times**:
```python
monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
from app.config import get_settings; get_settings.cache_clear()
from app.database import init_db; import asyncio; await asyncio.to_thread(init_db, str(tmp_path / "test.db"))
```
Locations: `test_routes_chat.py:8-10, 18-20, 33-35, 56-58` · `test_routes_resumes.py:9-11, 21-27, 79-90, 108-110, 117-122` · `test_routes_rules.py:6-8, 18-20, 32-34, 43-45` · `test_routes_master_resume.py:7-12, 19-24, 35-40, 48-53, 65-70` · `test_routes_system_prompt.py:6-8, 16-18`.

Why it exists: the `client` fixture (`conftest.py:71-77`) overrides only `get_backend` and never touches the DB, and `httpx.ASGITransport` **does not run FastAPI lifespan events** — so `app/main.py:20-27`'s `init_db` never executes under test. Each test must therefore hand-roll initialization, and one of them (P0-1) forgot.

This is a real per-test DB (a fresh file under `tmp_path`), which is good — but there is no autouse fixture, no teardown, and no PDFS_DIR default (only `test_routes_resumes.py:22, 48, 80` set `PDFS_DIR`).

### P1-10. E2E fragile text selectors — exact list

| file:line | Selector | Fragility |
|---|---|---|
| `test/e2e/01-fresh-start.spec.ts:18` | `page.getByText("Download Sample YAML")` | Full UI copy string; source at `EmptyState.tsx:105` |
| `test/e2e/02-master-resume.spec.ts:16` | `page.getByText("Start from Sample")` | Full copy string; `EmptyState.tsx:98` |
| `test/e2e/02-master-resume.spec.ts:46` | `page.getByText("Preview")` | Matches the `SegmentedControl` label at `MasterResumePanel.tsx:77`. One additional "Preview" string anywhere on the page → Playwright strict-mode violation. Note `PdfPreview.tsx:23,33` renders "Preview failed…" and `:60` has `title="Resume PDF Preview"`. |
| `test/e2e/06-resume-list-sort.spec.ts:20` | `page.getByText("Resumes")` | **So fragile that production code was reshaped around it.** `frontend/src/components/MasterResumePanel.tsx:62-63` carries the comment: `/* Caption must not start with "s": "Resume"+"s…" would collide with getByText("Resumes") used by the e2e nav tests. */` A test selector is now a constraint on UI copy. |
| `test/e2e/07-evaluation.spec.ts:22` | `page.getByText("evaluate", { exact: false })` | Case-insensitive **substring** match. `EvaluationPanel.tsx` alone contains "Evaluate" (:79), "Job description to evaluate against" (:89), "Evaluate resume" / "Evaluating…" (:108). Survives today only because none of those are mounted at click time. |
| `test/e2e/07-evaluation.spec.ts:24` | `page.locator("textarea[placeholder*='Paste the job description']")` | CSS selector keyed on placeholder prose, with an inline comment admitting it exists to disambiguate from the chat textarea. |

**These are avoidable.** `nav-resumes` and `nav-evaluate` testids already exist — `Sidebar.tsx:77` renders `testId={`nav-${item.view}`}` for every entry in `NAV` (`Sidebar.tsx:15-16`: `resumes`, `evaluate`), and specs 04 and 08 already use `[data-testid=nav-generate]` correctly (`04:18`, `08:18`, `08:39`). Specs 06 and 07 simply don't use the ids that are already there.

Positives: **no hardcoded waits anywhere** in the e2e suite (`grep waitForTimeout|sleep|setTimeout test/e2e/` → none). All waits are `expect(...).toBeVisible({ timeout })`, which is the correct auto-retrying form.

### P1-11. `PdfPreview` and `lib/sse.ts` have zero tests and are the most failure-prone frontend modules

`frontend/src/lib/sse.ts:29-48` is hand-written SSE framing:
- `\n`-splitting with manual buffer carryover across network chunks (lines 33-34)
- `currentEvent` state machine with a reset after each `data:` (lines 36-45)
- `JSON.parse` with a silent raw-string fallback (lines 40-44)

There is not a single test. A multi-byte UTF-8 character split across two TCP reads, or `\r\n` framing, or a `data:` line exceeding one chunk, would silently corrupt tokens. Both `ChatPanel.test.tsx:8` (`jest.mock("@/lib/sse")`) and the e2e suite bypass it entirely — the module is exercised by nothing.

`PdfPreview.tsx` (64 LOC) is mocked out in both component tests that would otherwise render it (`MasterResumePanel.test.tsx:15-18`, `ResumeListPanel.test.tsx:7-10`) and is untestable end-to-end because of P1-5.

---

## P2

### P2-12. Coverage gaps by module

#### Backend

| Module | LOC | Covered | Untested paths that matter |
|---|---|---|---|
| `app/yaml_utils.py` | 521 | `normalize_to_rendercv` happy paths + 15 repair cases across `test_yaml_utils.py` (8) and `test_rendercv_validation.py` (15), including a **real rendercv schema round-trip** at `test_rendercv_validation.py:178-215`. The best-tested code in the repo. | Malformed/unparseable YAML input (`yaml.YAMLError` path into `normalize_to_rendercv:409`); `_prune_path` (:339) and `_validate_and_repair` (:368) failure-to-converge / infinite-loop guard; `_split_duration` (:186), `_normalize_projects` (:244), `_normalize_skills` (:315), `_normalize_url` (:105), `_date_sort_key` (:114) have **zero direct tests** |
| `app/adapters.py` | 130 | 2 of 4 litellm error mappings (auth, rate-limit); rendercv non-zero exit → `RenderError`; `--design` flag + embedded-locale arg shape; `PyMuPDFAdapter` oversized guard | `LiteLLMAdapter.stream` — **entirely untested**: error mapping (:56-59) and chunk iteration with `delta` filtering (:60-63); `ServiceUnavailableError` and `APIConnectionError` mappings never exercised; `RenderCVAdapter` **success** path (:106 `pdf_path.read_bytes()`); `rendercv` binary missing → `FileNotFoundError` is **unmapped** and escapes as a generic 500 `GENERATION_FAILED`; **no timeout on `proc.communicate()` (:97)** — a hung rendercv hangs the request forever, untested; `PyMuPDFAdapter._MAX_PAGES` branch (:123-127) and corrupt-PDF branch (:121-122) |
| `app/routes/resumes.py` | 203 | SSE `done` + `complete_call_count == 2` (a genuinely good assertion, `test_routes_resumes.py:42`); `LLM_AUTH_ERROR`; rules injection into the system prompt (`:101-103`, good); `GET /{id}` 404; `DELETE /{id}` | `NO_MASTER_RESUME` branch (:63); `RENDER_FAILED`, `PDF_EXTRACT_FAILED`, `GENERATION_FAILED` branches (:138-143); `json.loads(gen_response)` on non-JSON LLM output (:94); `AUDIT_END` split vs. no-marker fallback (:106-109); `GET /{id}/pdf` — **all three paths** (:168-177: no row, no `pdf_path`, file missing on disk); `PATCH /{id}` (:157-165) incl. its 404; `POST /{id}/render` (:180-192) incl. its 404; PDF write `OSError` (:127); **client disconnect mid-SSE leaves a DB row with `pdf_path=NULL`** — no test, no cleanup |
| `app/routes/chat.py` | 79 | history-empty; `token` + `done` event types; `LLM_UNAVAILABLE`; `DELETE` → 204 | `LLM_AUTH_ERROR` and `CHAT_FAILED` branches (:66-71); **`LLM_HISTORY_LIMIT = 30` truncation (:19, :53) never exercised**; `sp_row is None` fallback prompt (:49); partial-stream failure leaving the user message persisted with no assistant message (:44 vs :63); the streamed text content is never asserted — only event *types* are checked (`test_routes_chat.py:26-28`) |
| `app/routes/evaluate.py` | 73 | `done` with `match_score`; `LLM_AUTH_ERROR` | `LLM_UNAVAILABLE` and `EVALUATION_FAILED` branches (:67-70); `json.loads` on malformed LLM JSON (:63); the `progress` event (:55) |
| `app/routes/master_resume.py` | 158 | GET 404; PUT create; DELETE; preview ×2; import (weakly, see P1-4) | non-PDF `content_type` → 400 (:132-133); `RenderError` → 422 (:121-122); DELETE-when-absent → 404 (:106); oversized upload — `await file.read()` (:134) loads the **whole** body into memory *before* the 10 MB check in `PyMuPDFAdapter` (:114) |
| `app/database.py` | 327 | Strong breadth (24 tests): schema creation, default-rule seeding, default-prompt seeding, idempotency, master-resume CRUD, history save + pruning to 10, generated-resume CRUD, pagination, sort-by-jd, chat, rules, system prompt | `list_resumes` interpolates `sort_col`/`order_dir` into the SQL string (:133-136) — the ternaries at :124-125 make it safe today, but **no test asserts an unknown `sort` value falls back** rather than injecting. **Concurrency: zero tests.** Every function opens its own `sqlite3.connect(db_path)` with no `timeout=`, no WAL pragma, no `check_same_thread` configuration, and all of them are invoked through `asyncio.to_thread` (genuinely concurrent under uvicorn). No test for `database is locked`. `upsert_master_resume` (:67-102) performs read → insert-history → prune → update as **four statements with no explicit BEGIN**; two concurrent upserts can interleave and lose history. `update_resume` (:173) likewise |
| `app/main.py` | 70 | — | The four `@app.exception_handler`s (:35-52) are **never tested** — and may be dead code, since every route catches these exceptions itself and converts them to SSE events. Lifespan (:20-27) is never run under test (ASGITransport skips it). Static mount (:68-70) untested. |
| `app/config.py` | 23 | — | No tests. `env_file=".env"` (:15) is resolved **relative to CWD** — a stray `backend/.env` would silently give the test run a live API key and `LLM_MOCK` setting. No test-mode guard. |
| `app/deps.py` | 17 | — | No tests. `_backend()` is `@lru_cache(maxsize=1)` (:7), so `LLM_MOCK` is read exactly once per process — flipping it at runtime silently does nothing. Untested. |
| `app/prompts.py` | 203 | `rules_block` indirectly via `test_routes_resumes.py:101-103` | `rules_block` (:193) with an empty list, duplicate keys, or unknown sections |
| `app/simulator.py` | 114 | Stream/render/extract smoke (`test_llm.py:157-178`) + the tautological constant test | The `complete` dispatch ladder (:76-95) — the `ResumeAuditor` `find("cv:")` branch (:88-89) and the `"evaluation" in system.lower()` branch (:90-91) are never directly tested |
| `app/backend_api.py`, `app/ports.py` | 34 + 46 | Exception hierarchy; pass-through via `ConfigurableBackendAPI` | `create_real_backend()` (:26-34) never constructed in tests |

#### Frontend — 1729 LOC of source, 97 LOC of tests

**Components/modules with zero tests:**
`WorkstationShell.tsx` (92 — the state root and view router) · `GenerationPanel.tsx` (182 — **the core feature**) · `EvaluationPanel.tsx` (175) · `EmptyState.tsx` (153) · `Sidebar.tsx` (93) · `ChatDrawer.tsx` (48) · `PdfPreview.tsx` (64) · `lib/sse.ts` (49) · `lib/api.ts` (83) · `app/layout.tsx`, `app/page.tsx` · all six `ui/` primitives (`Badge`, `Button`, `ConfirmButton`, `SegmentedControl`, `Spinner`).

**Tested (3 files, 6 tests):** `ChatPanel` (2, one hollow — P1-4), `MasterResumePanel` (2, one hollow), `ResumeListPanel` (2 — the strongest pair; `:27` asserts `api.listResumes` was called with `("jd", "desc")`, a real behavioral check).

Specific untested hazards:
- `lib/api.ts:18` — `getMasterResume: () => request(...).catch(() => null)` swallows **every** error into `null`. A 500 is indistinguishable from "no master resume yet", and the app renders the empty state — which the user can then destroy by importing over it. Untested.
- `lib/api.ts:6-13` — `request()`'s error unwrapping (`body.error ?? res.statusText`) is never exercised: all three component tests `jest.mock("@/lib/api")` wholesale.
- `ChatPanel.tsx:43-50` — the assistant-message coalescing logic keyed on `last.id < 0` is subtle and untested.
- `PdfPreview.tsx:35-38` — the `URL.revokeObjectURL` cleanup / `cancelled` guard (a classic leak/race site) is untested.

### P2-13. Missing test types, entirely absent

- **Contract tests (frontend types ↔ backend schemas)** — `frontend/src/lib/types.ts` (66 LOC of interfaces) is maintained **by hand** against FastAPI's Pydantic models and raw `sqlite3.Row` dicts. Nothing checks them. `test/fixtures/mock-constants.ts:1-2` states the problem outright:
  > `// These values must match backend/app/simulator.py MOCK_* constants exactly.`
  > `// If a test fails because values don't match, update these to match the simulator.`

  The documented remedy for a contract break is *to edit the test*. There is no OpenAPI snapshot, no generated types, no round-trip check.
- **Migration tests** — `app/database.py:30-36` applies `backend/db/schema.sql` via `conn.executescript()`, and every statement is `CREATE TABLE IF NOT EXISTS`. **There is no migration mechanism at all.** Adding a column to a deployed database is a silent no-op, and `resumedb-data` is a persistent Docker volume that survives image upgrades (`docker-compose.yml:9,23`). `test_init_db_is_idempotent` (`test_database.py:59-64`) only runs `init_db` twice on a **fresh** DB — it never simulates an old-schema database meeting new code.
- **Load / concurrency tests** — none. See the SQLite analysis in P2-12 (`app/database.py`): no `timeout`, no WAL, multi-statement writes without transactions, all under `asyncio.to_thread`.
- **Security tests** — none:
  - No auth exists at all (everything is `user_id = 'default'`, `app/database.py:4`), and no test documents that as intentional.
  - Upload size: `master_resume.py:134` does `await file.read()` with no cap before the 10 MB check at `adapters.py:114`. No test.
  - Path traversal: `resumes.py:173` builds `Path(_pdfs_dir()) / row["pdf_path"]` from a DB column. Written only by the app today, but untested.
  - `yaml.safe_load` is used throughout `yaml_utils.py` (correct), but no test pins it against a future `yaml.load` regression.
  - No CORS test; no test for the `StaticFiles(html=True)` mount at `main.py:70` shadowing API routes.
- **Accessibility** — none. No `jest-axe`, no `@axe-core/playwright`. `SegmentedControl.tsx:24-31` declares `role="tablist"` / `role="tab"` / `aria-selected` but has **no `tabpanel`** and no arrow-key handling — an incomplete ARIA pattern nothing tests.
- **Visual regression** — none, despite the 2026-07 dark + gold redesign. `playwright.config.ts:11` `screenshot: "only-on-failure"` captures diagnostics, not baselines. No `toHaveScreenshot`.
- **Golden-file tests** — none for rendered PDFs or for `normalize_to_rendercv` output. `test_rendercv_validation.py:178-215` is the closest (asserts the rendercv pydantic model *builds* from normalized output) but never pins the YAML text and never touches PDF bytes.

### P2-14. Determinism, flakiness, and speed

- **Backend: 89 tests in 15.7 s.** Slow for pure unit tests. Cost drivers: the real `rendercv` import at `test_rendercv_validation.py:180` (`pytest.importorskip("rendercv")`) and 21 real SQLite file creations under `tmp_path`.
- **Frontend: 6 tests in 7.5 s** — `ts-jest` without SWC; near-zero test volume.
- **No flaky-by-design constructs**: no sleeps, no wall-clock assertions, no network calls in unit tests. The single determinism defect is P0-1's order dependence.
- **`playwright.config.ts:6-7`** sets `fullyParallel: false, workers: 1` with `retries: 1`. Serialization + retries are *masking* the shared-state coupling described in P0-3 rather than fixing it; a retry re-runs against the state the failed attempt left behind.
- **CI-without-Docker feasibility**: backend and frontend suites run today with **no Docker and no API key** — `ConfigurableBackendAPI` / `SimulatedBackendAPI` cover every LLM call, and `conftest.py` stubs litellm. That is genuinely good. **E2E cannot**, per P0-3.
- **LLM mocking strategy**: two tiers, and the design is sound:
  - Tier 1 `app/simulator.py` `SimulatedBackendAPI` — deterministic whole-backend mock, activated by `LLM_MOCK=true` (`deps.py:10-12`), used by e2e.
  - Tier 2 `tests/helpers/simulator.py` `ConfigurableBackendAPI` — per-port simulators with `set_*_response`/`set_*_error`, call counters (`complete_call_count`, `stream_call_count`), and last-call capture (`last_complete_messages`). Injected via `app.dependency_overrides[get_backend]` (`conftest.py:72-77`).

  **The Tier-2 simulator is used and is a good seam** — `test_routes_resumes.py:42` asserts `complete_call_count == 2` (proving the two-pass generate→audit flow), and `:101-103` inspects `last_complete_messages` to verify rules injection. These are the two best backend tests. The seam is simply under-exploited: 11 uncovered `except` branches across the routes are each a 4-line test using `set_*_error`.

### P2-15. Dead code, stale scaffolding, unused imports

A linter would catch all of these; there is none (P0-2).

- `conftest.py:1-9` — stale "Wave 2" docstring (litellm is installed).
- `tests/helpers/simulator.py:1-8` — stale "will raise ImportError" docstring.
- `test_llm.py:181-221` — the three `try/except ImportError → pytest.skip` guards (lines 190, 204, 216) are dead; `app/backend_api.py` exists.
- `test_llm.py:56` — `import pytest` re-imported (already at line 10).
- `test_llm.py:8` — `import asyncio`, unused.
- `test_routes_resumes.py:3` — `MOCK_GENERATION_PROGRESS` imported, unused.
- `test_routes_master_resume.py:2` — `MOCK_IMPORT_YAML` imported, unused.
- `app/simulator.py:61-65` — `MOCK_GENERATION_PROGRESS` is defined but the real progress strings are hardcoded separately in `routes/resumes.py:66, 96, 112`; the constant is never used by production code and can drift.
- `docker-compose.test.yml:2` — `version: "3.9"` is obsolete in Compose v2 (and correctly absent from `docker-compose.yml`).
- `backend/tests/__pycache__/` contains committed-adjacent `.pyc` files from **two different pytest versions** (8.4.2 and 9.1.1), indicating the suite is run under inconsistent toolchains. `.gitignore:3` does exclude them.

---

## Target test strategy

### The pyramid this project should have

Current shape is 89 / 6 / 8 with an **inverted trust profile**: the 8 e2e specs carry the only end-to-end confidence and, per P1-5 and P1-6, cannot meaningfully fail; the 6 frontend tests cover 5% of the frontend.

```
          e2e (Playwright)        8 → 10      hermetic, <90 s, merge gate
      integration (route + DB)   ~45          real SQLite, Tier-2 sim, real normalize_to_rendercv
   component (RTL) + contract    ~40          one per panel + schema parity
              unit              ~120          yaml_utils, sse.ts, adapters, database
```

Targets: backend line coverage 80% (excluding `simulator.py`, `prompts.py`); frontend 60%; e2e stays at ~10 specs covering only the flows that cross the process boundary.

### Directory layout

```
backend/tests/
  conftest.py                    # settings_reset (autouse), db, client, sim, anyio_backend
  unit/
    test_yaml_utils_dates.py
    test_yaml_utils_sections.py
    test_yaml_utils_socials.py
    test_yaml_utils_malformed.py       # NEW — YAMLError, non-converging repair
    test_adapters_litellm.py           # against REAL litellm.exceptions
    test_adapters_rendercv.py          # incl. success path, missing binary, timeout
    test_adapters_pymupdf.py
    test_prompts.py
    test_database_crud.py
    test_database_concurrency.py       # NEW — parallel upserts, locked-DB
  integration/
    test_routes_health.py
    test_routes_master_resume.py
    test_routes_resumes.py
    test_routes_chat.py
    test_routes_evaluate.py
    test_routes_rules.py
    test_routes_system_prompt.py
    test_error_handlers.py             # NEW — main.py:35-52
    test_migrations.py                 # NEW — old-schema DB meets new init_db
  contract/
    test_openapi_snapshot.py           # golden OpenAPI JSON, diffed
  fixtures/
    resumes/{minimal,full,nasty}.yaml
    pdfs/real-1page.pdf                # REPLACES the blank mock.pdf
    golden/{normalized_full.yaml,...}
  helpers/simulator.py                 # keep as-is; it is the right seam

frontend/src/
  lib/__tests__/sse.test.ts            # NEW — chunk boundaries, multi-byte, \r\n, bad JSON
  lib/__tests__/api.test.ts            # NEW — error unwrapping, the .catch(()=>null) trap
  components/__tests__/<Component>.test.tsx     # colocate; retire src/__tests__/
  __tests__/contract/types.test.ts     # generated-types diff vs backend OpenAPI

test/
  e2e/<nn>-<scenario>.spec.ts
  support/
    fixtures.ts                        # worker-scoped ephemeral app + BASE_URL
    reset.ts                           # one reset helper, replaces ad-hoc DELETEs
    selectors.ts                       # named testid constants, single source of truth
  fixtures/{sample-resume.yaml,sample-jd.txt,mock-constants.ts}
```

### Naming conventions

- pytest: `test_<unit>_<condition>_<expected>` — e.g. `test_generate_stream_render_error_emits_render_failed_event`. Directory (`unit/` vs `integration/`) carries the tier; drop tier words from names.
- jest: `describe("<Component>") > it("<does X> when <Y>")`.
- Playwright: `<nn>-<scenario>.spec.ts` — but once P0-3 is fixed the specs are order-independent, so the `nn-` prefixes should be dropped rather than implying a sequence.
- All e2e locators come from `support/selectors.ts`; no bare string literals in specs.

### Fixture strategy — backend

Replace all 21 copy-pasted blocks with:

```python
# conftest.py
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def settings_reset(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH",  str(tmp_path / "test.db"))
    monkeypatch.setenv("PDFS_DIR", str(tmp_path / "pdfs"))
    monkeypatch.setenv("LLM_MOCK", "true")
    get_settings.cache_clear()
    _backend.cache_clear()
    yield
    get_settings.cache_clear()     # ← the missing half; this is what fixes P0-1
    _backend.cache_clear()

@pytest.fixture
def db(settings_reset):
    path = get_settings().DB_PATH
    init_db(path)
    return path
```

Teardown on **both** sides of the `yield` is the fix for P0-1: no test can then inherit another's settings, and `pytest-randomly` becomes safe to enable. Delete the `sys.modules` litellm stub from `conftest.py:20-58` so `test_llm.py` imports the real `litellm.exceptions` and the contract is genuinely pinned (P1-7). Keep `ConfigurableBackendAPI` unchanged — it is well-designed.

### Fixture strategy — frontend

- Stop `jest.mock("@/lib/api")` wholesale. Use MSW (or a thin `fetch` stub) so `lib/api.ts`'s own error handling is exercised, and assert on request shape rather than on a mocked module's call log.
- One shared `renderPanel()` helper providing the `WorkstationShell` context.
- Keep `jest.mock("@uiw/react-codemirror")` (`MasterResumePanel.test.tsx:7-12`) — mocking a heavy third-party editor is legitimate — but **stop mocking `PdfPreview`**; test it directly with a stubbed `fetch` + `URL.createObjectURL`.

### Making e2e hermetic — three changes

1. **Dynamic port.** Remove the `ports:` mapping from `docker-compose.test.yml:8-9` entirely — the `playwright` service already reaches the app over the compose network at `http://app:8000` (`docker-compose.test.yml:35`). For host-side runs, use `ports: ["0:8000"]` and resolve it:
   ```bash
   BASE_URL="http://localhost:$(docker compose -f docker-compose.test.yml port app 8000 | cut -d: -f2)"
   ```
   This permanently removes the collision with `docker-compose.yml:7` and `scripts/start_mac.sh:7`, and makes it impossible for the suite to hit the production container. Also drop the hardcoded fallback in `playwright.config.ts:10` — fail loudly if `BASE_URL` is unset rather than defaulting to 8000.

2. **Ephemeral state.** Replace the named volumes at `docker-compose.test.yml:11-12, 37-39` with `tmpfs` mounts so the DB and PDFs vanish with the container. Add either a worker-scoped Playwright fixture that resets all five resources before each spec, or — better — a test-only `POST /api/_test/reset` endpoint registered **only when `settings.LLM_MOCK` is true**, which re-runs `init_db` against a truncated DB. Then delete every ad-hoc `request.delete(...).catch(() => {})` from the specs (`01:7-8`, `02:10`, `03:6`, `05:11`, `08:12`) and fix `06:12-14` to await generation and assert it succeeded rather than swallowing the error.

3. **Deterministic stub that produces a real PDF.** Run `rendercv render` once over `test/fixtures/sample-resume.yaml` and commit the result as `backend/tests/fixtures/mock.pdf`, replacing the blank 313-byte file (P1-6). Then:
   - Give `PdfPreview.tsx` **distinct** testids per state — `${testId}-loading`, `${testId}-error`, `${testId}-frame` (lines 42, 49, 57) — and point every e2e assertion at `-frame` only. This alone converts three currently-vacuous assertions (P1-5) into real ones.
   - Add one content assertion: fetch the PDF blob in-page, parse with `pdf-parse`, `expect(text).toContain("Mock Corp")`. Neither P1-5 nor P1-6 can then recur silently.
   - Extend `SimulatedBackendAPI.complete` (`app/simulator.py:76-95`) to echo enough of the input that rule changes are observable, so `08-rules.spec.ts:30-45` can assert something real.

Additionally: replace the six `getByText` selectors (P1-10) with the `nav-*` / `data-testid` locators that already exist, then **delete the copy constraint at `MasterResumePanel.tsx:62-63`** — production UI text should not be shaped by a test selector.

### CI gate sequence

One workflow, `.github/workflows/ci.yml`, fail-fast in this order (cheapest and most-likely-to-fail first):

```
1. lint        ruff check backend/ ; ruff format --check backend/
               npm --prefix frontend run lint ; prettier --check                   ~10 s
2. typecheck   mypy backend/app/ (start: --ignore-missing-imports, ratchet up)
               npx --prefix frontend tsc --noEmit                                  ~30 s
3. unit        cd backend && pytest -q -p randomly --cov=app --cov-fail-under=75
               npm --prefix frontend test -- --coverage --ci                       ~30 s
4. build       docker build -t resumetailor:ci .                                   ~3 min (layer-cached)
5. e2e         docker compose -f docker-compose.test.yml up
                 --abort-on-container-exit --exit-code-from playwright             ~2 min
6. artifacts   upload test/playwright-report/, coverage HTML, traces — on failure only
```

Step 3 **must** run randomized (`-p randomly`), or P0-1 regresses the moment someone adds another cache-clearing test.

Dependencies to add:

```toml
# backend/pyproject.toml — [dependency-groups].dev
"ruff>=0.6", "mypy>=1.11", "pytest-cov>=5.0", "pytest-randomly>=3.15"
```
```jsonc
// frontend/package.json — devDependencies
"eslint", "eslint-config-next", "prettier", "jest-axe", "msw"
// scripts
"lint": "next lint", "typecheck": "tsc --noEmit",
"test": "jest --ci"          // drop --passWithNoTests
```

Coverage floors: start at `--cov-fail-under=75` (backend) and 50% (frontend), ratchet up each quarter. Exempt `app/simulator.py` and `app/prompts.py` via `[tool.coverage.report] omit`.

### Highest-value work, in priority order

1. **`conftest.py` autouse fixture with teardown** (P0-1, P1-9) — deletes 63 lines of copy-paste, fixes the isolation bug, unblocks randomized CI. Half a day.
2. **`.github/workflows/ci.yml` + ruff + eslint + tsc** (P0-2) — the suites already pass and already run without Docker or an API key; only the gate is missing. Half a day.
3. **Distinct `PdfPreview` testids + a real mock PDF** (P1-5, P1-6) — makes the e2e generation path meaningful for the first time. Two hours.
4. **E2E hermeticity: dynamic port + tmpfs + reset helper** (P0-3) — removes the production-data-destruction hazard. One day.
5. **`lib/sse.ts` unit tests** (P1-11) — 49 lines of untested hand-rolled stream framing, on the critical path of all three streaming features. Half a day.
6. **Route error-branch tests via `sim.set_*_error`** (P2-12) — the seam already exists and is proven; 11 uncovered `except` branches are each a ~4-line test. One day.
7. **OpenAPI golden snapshot + generated TS types** (P2-13) — kills the hand-maintained `types.ts` / `mock-constants.ts` drift that the fixture file itself documents. One day.
8. **Migration mechanism + tests** (P2-13) — `CREATE TABLE IF NOT EXISTS` against a persistent volume is a latent data-loss bug, not just a test gap.
