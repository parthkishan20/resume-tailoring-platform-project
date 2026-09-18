# PLAN.md — ResumeTailor Production Restructure

> The single source of truth for what is being built and in what order.
> Every agent updates this file as part of the same change as its code. See [`AGENTS.md`](./AGENTS.md) §6.
>
> **Status:** Audits complete (6 of 6). 63 defects registered. Wave 0 ready to execute.
> Blocked on Decision D1 (visual direction) for all UI tasks, and on blockers B-03 and B-04.
> **Last updated:** 2026-09-18

---

## 1. What this is

ResumeTailor is a single-user AI workstation for tailoring resumes. A user keeps one master resume in
RenderCV YAML, pastes a job description, and gets a tailored, ATS-oriented PDF. It works today. It is
not production ready, and this plan is the path from one to the other.

**What "production ready" means here** (the bar every wave is measured against):

1. No data-loss path. Schema changes apply to existing databases; user data is backed up and restorable.
2. No unbounded resource use. Every subprocess, request, and upload has a limit and a timeout.
3. Failures are legible. Errors reach the user with a cause, and reach the operator with a request ID.
4. Anything that can be verified automatically is verified in CI, on every push.
5. A new contributor can go from clone to running app to first merged change using only the docs.
6. The UI is coherent, accessible, and works in both themes.

**Explicit non-goals for this effort:** multi-tenancy beyond the existing single-user model, a hosted
offering, a mobile app, or a change to the RenderCV rendering engine.

---

## 2. Current state

Six parallel audits covered the backend, the data and rendering layer, the frontend, infrastructure,
the test suite, and the product spec against the implementation. Full reports land in
`docs/reports/audit-*.md`.

**Shape of the codebase:** ~3,300 lines of Python, ~1,800 lines of TypeScript, ~9,000 lines of planning
documents. Small enough that a real restructure is affordable and large enough that the current
structure already hurts.

**What is genuinely good and is being kept:**

- The ports-and-adapters boundary (`ports.py`, `adapters.py`, `backend_api.py`) is real, not decorative.
  It makes the LLM, the renderer, and the PDF extractor swappable, and it is why a deterministic test
  mode exists at all.
- `normalize_to_rendercv` plus the validation backstop is hard-won, well-tested logic. It moves, it does
  not get rewritten.
- The split editor-and-preview posture is the right working model for this product.
- SSE for streaming generation, with typed event names, is the right transport.
- `prefers-reduced-motion` and visible focus rings are already handled correctly.

### 2.1 Defect register

Severity is about production risk, not effort. P0 items can lose or expose user data.

> **Every file:line below predates task 1.1.** The register and all six reports in `docs/reports/`
> were written against `backend/app/`, which task 1.1 moved to `backend/src/resumetailor/` and
> reorganised into `api/routers/`, `core/`, `db/`, `rendering/`, `resume_schema/`, `llm/` and `pdf/`.
> The findings are still real and the evidence is still checkable; the paths are not current. Use the
> old-to-new mapping in `docs/ARCHITECTURE.md` §2 to locate anything. These citations are deliberately
> **not** being rewritten: they are the evidence as gathered, and silently updating them would make the
> audit unreproducible against the commit it was taken from (`e943dfb`).

| # | Sev | Area | Defect | Evidence |
|---|---|---|---|---|
| D-01 | **P0** | Data | Real PII (name, email, phone, home address, credential URLs with tokens) sat untracked and un-ignored. One `git add -A` would have published it. | `planning/master-resume.yaml` — **fixed 2026-09-18**, added to `.gitignore:82` |
| D-02 | **P0** | Data | No migration path. `init_db` runs `CREATE TABLE IF NOT EXISTS` on every boot, so any schema change is a silent no-op on an existing volume, and the next query raises `no such column`. | `database.py:34-52`, `schema.sql` |
| D-03 | **P0** | Data | No backups. The only durable copy of every resume is a Docker named volume. `docker compose down -v` destroys it with no recovery. | `config.py:11`, `docker-compose.yml:9` |
| D-04 | **P0** | API | `PUT /api/master-resume` stores arbitrary unvalidated text as the canonical source document. Failure surfaces much later, at render time. | `master_resume.py:96-99` |
| D-05 | **P1** | Perf | `normalize_to_rendercv` runs CPU-bound RenderCV validation on the event loop. Measured 4.94s cold, 0.13s warm, on a single-worker server. The first render after boot freezes everything, health checks included. | `yaml_utils.py:368-406`; call sites `master_resume.py:120`, `resumes.py:69,94,110` |
| D-06 | **P1** | Data | `master_resume` and `system_prompt` lack `UNIQUE(user_id)`, and their upserts are read-then-write. Concurrent writes insert duplicate rows; reads then return an arbitrary one, so edits appear to revert at random. | `schema.sql:1-6,43-48`, `database.py:70-101,303-323` |
| D-07 | **P1** | Rendering | The `rendercv` subprocess has no timeout and no concurrency cap. A hung render holds the SSE connection and its temp dir forever; N concurrent generations spawn N typst processes. | `adapters.py:87-97` |
| D-08 | **P1** | UX | The validation backstop silently deletes user data. An invalid email is dropped and the user gets a PDF with no email address, never told. `normalize_to_rendercv` returns a bare `str`, so there is no channel for diagnostics. | `yaml_utils.py:395-400`, `:101`, `:162` |
| D-09 | **P1** | Data | Timestamps are stored UTC-naive and space-separated; the browser parses them as local time, so every displayed time is wrong by the host offset. | `schema.sql:5,12,22,23,31,47`; `MasterResumePanel.tsx:67`, `ResumeListPanel.tsx:101` |
| D-10 | **P1** | API | `limit` and `page` reach SQL unbounded. `limit=-1` returns every row. | `resumes.py:47-50`, `database.py:115-137` |
| D-11 | **P1** | UI | Dark mode is hardcoded despite the spec requiring a toggle; `next-themes` is installed and unused. | `layout.tsx:20` |
| D-12 | **P1** | UI | Generate and Evaluate each re-implement the same 420px job-description column, with diverging error styling. | `GenerationPanel.tsx:79`, `EvaluationPanel.tsx:86` |
| D-13 | **P2** | Data | `sqlite3.connect` used as a context manager never closes the connection; `__exit__` only commits. Leaks fds and WAL handles under load. | all 17 functions in `database.py` |
| D-14 | **P2** | Data | No WAL, no `foreign_keys` pragma, no indexes, no foreign keys. History rows orphan on delete; `list_resumes` full-scans and sorts. | `schema.sql` |
| D-15 | **P2** | Rendering | `settings.yaml` is dead configuration, never read, and hardcodes a specific person's name into repo config. RenderCV 2.8 does expose `--settings`. | `backend/rendercv_config/settings.yaml`, `adapters.py:12` |
| D-16 | **P2** | Rendering | The locale-embedding workaround rests on a misdiagnosis: the real flag is `--locale-catalog`, which does take a path. The workaround mutates top-level user keys, and a stray `locale:` key from the LLM silently disables the project locale. A test freezes the misdiagnosis in place. | `adapters.py:75-84`, `test_llm.py:120` |
| D-17 | **P2** | Rendering | The backstop imports RenderCV private internals inside a bare `except Exception: return`. A RenderCV reorganization turns it into a permanent silent no-op, and the guarding test would merely skip. | `yaml_utils.py:373-377`; `pyproject.toml:9` pins `>=2.8` with no upper bound |
| D-18 | **P2** | Rendering | The backstop validates against theme `classic` while the renderer uses `engineeringresumes`. | `yaml_utils.py:382` vs `design.yaml:2` |
| D-19 | **P2** | Deps | `phonenumbers` is imported directly but declared nowhere; it arrives transitively through RenderCV. | `yaml_utils.py:89`, `pyproject.toml:5-13` |
| D-20 | **P2** | Data | Partial-failure orphans. A crash between row creation and PDF write leaves `pdf_path=NULL`; a crash after leaves an unreferenced PDF. No reaper. | `resumes.py:119-131,195-203` |
| D-21 | **P2** | Perf | Chat loads the entire message history on every turn, then slices to 30 in Python. `GET /api/chat` returns every message ever. | `chat.py:35,47,53` |
| D-22 | **P2** | Schema | The master-resume schema contract exists in five drifting places with no single source of truth, and they already contradict each other. | `master_resume.py:20-77`, `prompts.py:1-125`, `yaml_utils.py:1-13,26-54` |
| D-23 | **P2** | Schema | `DEFAULT_RULES` names sections that do not exist in the YAML (`extracurricular` vs `extra_curricular_activities`), so those rules are emitted into the prompt against a nonexistent section. | `database.py:11,19` vs `yaml_utils.py:53` |
| D-24 | **P2** | Schema | `work_experience` is hoisted into `cv.sections` but no normalizer dispatches on it, so it reaches RenderCV untyped. | `yaml_utils.py:53` vs `:497-506` |
| D-25 | **P2** | Security | Latent path traversal: `pdf_path` is joined to `PDFS_DIR` without resolution. Unreachable today only because the update schema omits the field. | `resumes.py:173,202`, `database.py:178` |
| D-26 | **P2** | UI | Icon-rail labels render at 10px, below the readable floor. | `Sidebar.tsx:56` |
| D-27 | **P2** | Test | Product copy is written around a fragile text selector; a source comment instructs authors not to start a caption with "s". | `MasterResumePanel.tsx:63-65` |
| D-28 | **P0** | Security | **No authentication or authorization on any endpoint.** Anyone who can reach the port can read the owner's full PII, overwrite the master resume, rewrite the system prompt used for every future chat turn (a stored prompt-injection primitive), and spend the owner's LLM credits without limit. Compose binds `0.0.0.0`. | all of `app/routes/*`; `main.py:57-70` registers no middleware of any kind |
| D-29 | **P0** | Test | **Running the e2e suite can destroy real user data.** `playwright.config.ts:10` defaults to port 8000; both compose files and both start scripts bind host 8000, and the dev container has `restart: unless-stopped`. Following the README's own instructions while the dev container is up points Playwright at the production stack, where every spec's `beforeEach` issues `DELETE /api/master-resume`, `DELETE /api/chat`, or `DELETE /api/rules` against real data, with a live API key. Several of those calls swallow errors, hiding that they succeeded against the wrong target. | `test/playwright.config.ts:10`, `docker-compose.yml:7`, `docker-compose.test.yml:9`, `scripts/start_mac.sh:7`, e2e specs 01, 02, 03, 05, 08 |
| D-30 | **P0** | Frontend | **Unsaved editor edits are silently destroyed by navigation.** The YAML buffer lives in local state and the panel is conditionally rendered, so clicking any nav item unmounts it and discards the buffer. No dirty guard, no `beforeunload`, no draft persistence. The header shows "edited" right up to the moment the work is thrown away. | `MasterResumePanel.tsx:23`, `WorkstationShell.tsx:64-70` |
| D-31 | **P0** | Frontend | **Every `DELETE` call throws on success.** The API client calls `res.json()` unconditionally, but three endpoints return 204 with an empty body. Deleting the master resume succeeds server-side while the UI shows a red "Unexpected end of JSON input" bar and still displays the deleted resume; clearing chat leaves the transcript on screen. | `api.ts:6-13`; 204 at `master_resume.py:102`, `resumes.py:195`, `chat.py:77` |
| D-32 | **P0** | Frontend | **Any backend failure on load is rendered as "you have no resume."** `getMasterResume` has a blanket `.catch(() => null)`, so a 500, a 503, or a network drop is indistinguishable from a genuine 404. The user is shown onboarding, where "Start from Sample" immediately `PUT`s sample YAML over their real data. | `api.ts:17-18`, `WorkstationShell.tsx:51-53`, `:26-30` |
| D-33 | **P0** | Product | **The chat assistant cannot perform any workstation action.** One of the three stated core principles. The route is a plain streaming completion; the `done` event hardcodes `"action": None`. No tool calling, no action parsing, no database writes. Both the README and the in-app copy tell the user "changes apply directly." | `chat.py:39-74`, `:65`; advertised at `ChatPanel.tsx:76-79`, `README.md:45-46` |
| D-34 | **P0** | Build | **No `.dockerignore`.** The build context is the whole repository, roughly 850 MB, streamed to the daemon on every build. That context includes `.env` with a live API key. Not baked into the image today, but one careless `COPY . .` away from it. | absent |
| D-35 | **P0** | Build | `COPY frontend/ ./` runs *after* `npm ci` and overwrites the freshly installed Linux tree with the host's macOS `node_modules` (`@next/swc-darwin-arm64` confirmed present). The image builds the frontend against darwin binaries inside a Linux image. | `Dockerfile:9` |
| D-36 | **P0** | Build | `COPY backend/ ./backend/` bakes the host's 345 MB conda/darwin Python 3.13 virtualenv into a Python 3.12 Linux image, permanently in the layer history. The image is roughly 1.2 GB where 400 MB is achievable. | `Dockerfile:22` |
| D-37 | **P0** | Test | Order-dependent test that fails in isolation. `get_settings` is `lru_cache`d; 21 tests call `cache_clear()` on entry and none on exit, leaking a stale `Settings` pointing at a deleted `tmp_path` into whatever runs next. Any `-k` filter, shard, or IDE single-test run breaks it. | `test_routes_master_resume.py:76`; leaking call sites across five test modules |
| D-38 | **P0** | CI | No CI of any kind. Nothing lints, formats, type-checks, or runs the 89 backend, 6 frontend, or 8 e2e tests on any push. `frontend/package.json:9` is `jest --passWithNoTests`, so deleting every frontend test still exits 0. No ruff, mypy, coverage, eslint, prettier, or pre-commit is configured. | absent |
| D-39 | **P0** | A11y | Keyboard users cannot import a PDF. The drop zone is a bare `<div onClick>` with no role, no `tabIndex`, and no key handler, wrapping a `display: none` file input that is out of the tab order. There is no keyboard path to the primary onboarding action. | `EmptyState.tsx:109-122` |
| D-40 | **P1** | Frontend | No `AbortController` exists anywhere in the codebase, though the SSE helper accepts a signal. Closing the chat drawer or navigating mid-generation orphans the HTTP connection and the server-side job, and leaves an unmounted component calling `setState`. | `sse.ts:9-13`; call sites `ChatPanel.tsx:40`, `GenerationPanel.tsx:38`, `EvaluationPanel.tsx:59` |
| D-41 | **P1** | Frontend | Generate and Evaluate silently use the last *saved* resume, not what is on screen. Evaluate sends the shell's copy; Generate discards its prop entirely and the backend re-reads the database. Combined with D-30, edits are both ignored and then destroyed. | `EvaluationPanel.tsx:59-62`, `GenerationPanel.tsx:18`, `resumes.py:61` |
| D-42 | **P1** | Frontend | Backend error messages never reach the user. Only the four custom handlers emit `{error, code}`; every `HTTPException` emits `{detail}`, which the client ignores, so the user sees a bare "Not Found" or "Unprocessable Entity". The `code` field is parsed nowhere, so the UI cannot distinguish "configure your API key" from "the renderer crashed". `PdfPreview.tsx:23` reads `detail` correctly, which makes the inconsistency provable. | `api.ts:8-11` vs `PdfPreview.tsx:23` |
| D-43 | **P1** | Frontend | Zero responsive handling. Three fixed columns total 876px of chrome before any content, and not one Tailwind breakpoint prefix appears in any component. The layout breaks outright below about 900px, against a spec that requires "responsive down to tablet". The editor split is also not draggable. | `WorkstationShell.tsx:56`; widths at `Sidebar.tsx:62`, `GenerationPanel.tsx:79`, `ChatDrawer.tsx:28` |
| D-44 | **P1** | A11y | Tabs use `role="tab"` without the required parent and keyboard contract; the streaming chat is silent to screen readers; not one `role="alert"` exists on any error; resume list items are not operable by keyboard; the chat drawer is neither a dialog nor focus-managed; several pairs fail contrast against the app's own palette. | frontend audit §5 |
| D-45 | **P1** | Product | Nine implemented backend capabilities have zero frontend callers, so the product is materially smaller than both the spec and the README describe: edit a generated resume, re-render after edits, rename a resume, evaluate a *generated* resume, view or edit the system prompt, reset rules, choose sort order, and page past the first 20 resumes. | `api.ts:35-44,58,61-69` (no callers); `ResumeListPanel.tsx:20` |
| D-46 | **P1** | LLM | No timeout, no retry, no backoff, and no `max_tokens` on any LLM call. A stalled stream holds the connection indefinitely; a rate limit becomes an immediate client-visible 503. | `adapters.py:30-65` |
| D-47 | **P1** | Security | No length bound on any LLM-bound input. Five request models take a bare `str`, and Starlette imposes no default body cap, so a 50 MB body is accepted, persisted, and forwarded to the provider. Cost and memory are both attacker-controlled, and there is no rate limiting. | `chat.py:30`, `resumes.py:37`, `evaluate.py:42-44`, `system_prompt.py:15`, `master_resume.py:84` |
| D-48 | **P1** | Security | Unbounded upload read: `await file.read()` materializes the whole body before the 10 MB guard, which lives downstream in the extractor. A 2 GB POST OOMs the container. The content-type check reads a client-supplied header. | `master_resume.py:132-135`, guard at `adapters.py:114-117` |
| D-49 | **P1** | Security | The API key is written to process-global `os.environ` from an adapter constructor, and is inherited by the `rendercv` child process, which has no use for it. | `adapters.py:28`, `:87-96` |
| D-50 | **P1** | Security | LLM-authored YAML is handed to a document renderer running as **root**, with the SQLite volume mounted. No `USER` directive, no read-only rootfs, no tmpfs scratch. This is the highest-value exploit chain in the application. | `Dockerfile` (no `USER`), `adapters.py:70-102` |
| D-51 | **P1** | Ops | `uv` is PID 1 and does not reliably forward `SIGTERM`. `docker stop` waits out the grace period then `SIGKILL`s, aborting in-flight SSE streams and mid-write renders. | `Dockerfile:41-43` |
| D-52 | **P1** | Ops | No logging configuration at all. The one logger in the backend never reaches a handler, so its warnings are dropped. Every `except Exception` swallows the exception into a string and never logs the traceback, making production failures unattributable. | `main.py` (absence); `chat.py:70`, `evaluate.py:69`, `resumes.py:142` |
| D-53 | **P1** | Security | Full subprocess stdout and stderr, including absolute paths and tracebacks, is returned verbatim to the client in error bodies. Same for raw provider exception text. | `adapters.py:98-105` reaching `main.py:45-47` and `:40-42` |
| D-54 | **P1** | API | Zero `response_model` declarations in the entire backend. Every handler returns a raw dict built from a `sqlite3.Row`, several via `SELECT *`. The OpenAPI spec documents every response as `{}`, the frontend's hand-written types are unenforced, and any future column silently joins the public API. | all routes; `database.py:157,167,201,243,322` |
| D-55 | **P1** | Ops | All three SSE routes wrap their body in a try/except inside the generator, so every failure is HTTP 200 with an error frame. Load balancers and uptime checks see 100% success during a total outage, and the global exception handlers are dead code for these routes. | `chat.py:42-71`, `evaluate.py:54-70`, `resumes.py:59-143` |
| D-56 | **P1** | Data | SQLite runs with no WAL and no `busy_timeout` tuning in an application that performs long writes. Two concurrent generations raise `database is locked`, which surfaces as a generic `GENERATION_FAILED`. | `database.py` throughout |
| D-57 | **P2** | API | `POST /api/resumes/{id}/render` does not normalize YAML while `GET /api/master-resume/preview` does, so identical YAML renders through one path and fails through the other. `PATCH` also leaves `pdf_path` pointing at a PDF rendered from the old YAML. | `resumes.py:185` vs `master_resume.py:120`; `resumes.py:157-177` |
| D-58 | **P2** | API | Inconsistent DELETE semantics: three routes return 204, two return 200 with a body because they are really "reset". `/docs` and `/openapi.json` are publicly served. Health is a static literal that touches nothing, so a container with a corrupt database reports itself healthy. | `rules.py:37-39`, `system_prompt.py:32-34`, `main.py:30`, `health.py:7-9` |
| D-59 | **P2** | Robustness | Provider `content` can be `None` on a refusal or a tool-call response, and it flows straight into `json.loads`. Two paths become a generic SSE error; `import_pdf` becomes an unhandled 500. | `adapters.py:40`; `master_resume.py:156`, `evaluate.py:63`, `resumes.py:94` |
| D-60 | **P2** | Frontend | Nine unchecked casts of `unknown` in SSE handling, zero runtime validation of any API response, and hand-maintained types against an untyped API. `tsconfig` sets `strict: true` but there is no linter at all, so nothing enforces the rest. 1.1 MB of uncompressed JS loads eagerly on a single route. | frontend audit §3, §6 |
| D-61 | **P2** | Docs | All eight screenshots predate the redesign and show a materially different application, so the README misrepresents the product to anyone evaluating it. | `docs/screenshots/`, `README.md` |
| D-62 | **P2** | Repo | `frontend/tsconfig.tsbuildinfo` is committed. `.superpowers/sdd/*.md` is tracked while `.superpowers/` is unignored. `.git` has 534 loose objects and no packs. Stale directories on disk: `.playwright-mcp/`, `.pytest_cache/`, `frontend/.next` (92 MB, stale given `distDir: 'out'`). | as listed |
| D-63 | **P2** | Ops | No dependency vulnerability scanning of any kind across 80 Python packages, including `pymupdf` (which parses untrusted uploads) and `litellm`, plus the npm tree. Not a specific CVE: there is no mechanism by which one would ever be noticed. | absent |
| D-64 | **P1** | Test | **The e2e stack cannot generate a resume.** `SimulatedBackendAPI.render` reads its fixture from `backend/tests/fixtures/mock.pdf`, but `.dockerignore:86` excludes `backend/tests/` from the image, and `docker-compose.test.yml` runs with `LLM_MOCK=true`. The first generation in the e2e stack raises `FileNotFoundError`. Latent until now only because tasks 0.4 and 0.5 both ran without a Docker daemon, so neither could execute what they built. The fixture must move out of the test tree and into the package. | `simulator.py` `_FIXTURE_PDF`, `.dockerignore:86`, `docker-compose.test.yml` |
| D-65 | **P2** | Build | The package is importable but not installed. `uv.lock` declares `source = { virtual = "." }`, so `src/` is reached through `pythonpath` in `pyproject.toml` and `PYTHONPATH` in the `Dockerfile`. A real distribution needs a `[build-system]`, a lockfile regeneration, and a Dockerfile layer reorder. Works today; will not survive packaging or a `pip install`. | `backend/pyproject.toml`, `backend/uv.lock`, `Dockerfile` |

**One result came back clean.** Every revision in the repository was scanned for key-shaped strings,
and `.env` was never committed at any point in its history. The one class of problem that would have
been expensive to fix is not present. A `gitleaks` gate in CI keeps it that way.

**A correction to an assumption in the audit brief:** `frontend/out` and `backend/static` are *not*
committed. Both are gitignored and `git ls-files` returns nothing for either. They exist only as stale
local build artifacts.

Full reports, with every finding and its evidence: `docs/reports/audit-*.md`.

### 2.2 What is missing entirely

Not "weak" but absent, so there is nothing to improve and something to build: CI; linting, formatting,
and type checking for either language; structured logging, request IDs, metrics, and error tracking;
authentication, authorization, rate limiting, and request size limits; a `.dockerignore`; a backup or
restore procedure; a migration mechanism; dependency vulnerability scanning; and any contract at all
between the frontend's hand-written types and the backend's actual responses.

### 2.3 The gap between the product and its description

The README and the original spec describe a product meaningfully larger than the one that exists. Nine
implemented backend capabilities have no UI that calls them, and the headline capability of the chat
assistant does not exist at all (D-33, D-45). Two things follow. First, wave 3 carries real feature
work, not just hardening. Second, the documentation is corrected to match reality *before* that work
lands, rather than after, so nobody evaluates the app against a description it does not meet.

---

## 3. Target architecture

### 3.1 Principles

1. **One source of truth per concept.** The resume schema is defined once, in code, and the LLM prompt
   text is generated from it. Constants are not hand-copied between modules.
2. **Routes are thin.** A route parses, delegates to a service, and serializes. Business logic lives in
   `domain/`, not in a handler.
3. **The boundary is typed.** Pydantic in, Pydantic out. No bare `dict` crosses a route boundary, and
   the frontend validates responses rather than trusting them.
4. **Errors are domain objects.** Handlers raise domain exceptions; one middleware translates them to
   HTTP. No `except Exception` that swallows.
5. **Nothing blocking on the event loop.** CPU-bound and blocking I/O goes through `to_thread`, and
   every subprocess has a timeout and a concurrency bound.
6. **Tokens, not hex.** No color literal appears in a component. No magic number appears twice.

### 3.2 Target structure

```
resume-tailoring-platform/
├── AGENTS.md                      # agent contract
├── PLAN.md                        # this file
├── README.md                      # what it is, how to run it, in that order
├── CONTRIBUTING.md
├── Makefile                       # make check | test | dev | build | migrate | backup
├── .dockerignore
├── .pre-commit-config.yaml
│
├── .github/workflows/
│   ├── ci.yml                     # lint, typecheck, unit, contract, secrets — every push
│   ├── e2e.yml                    # hermetic Playwright — every PR
│   └── release.yml                # build, scan, publish image on tag
│
├── deploy/
│   ├── Dockerfile                 # multi-stage, non-root, healthcheck, tini
│   ├── compose.yml                # base
│   ├── compose.dev.yml            # bind mounts, reload, dynamic port
│   ├── compose.test.yml           # LLM stub, ephemeral volumes, dynamic port
│   └── scripts/{backup.sh,restore.sh,entrypoint.sh}
│
├── backend/
│   ├── pyproject.toml             # + ruff, mypy, coverage config
│   ├── migrations/
│   │   ├── 0001_initial.sql       # reproduces today's schema exactly
│   │   ├── 0002_unique_user.sql   # UNIQUE(user_id), dedupe-then-rebuild
│   │   ├── 0003_indexes_fks.sql   # indexes, FKs with ON DELETE CASCADE
│   │   └── 0004_iso_timestamps.sql
│   ├── src/resumetailor/
│   │   ├── main.py                # app factory, lifespan, router registration
│   │   ├── core/
│   │   │   ├── config.py          # Settings, all env, validated at startup
│   │   │   ├── logging.py         # structured JSON logs, request-id contextvar
│   │   │   ├── errors.py          # domain exception hierarchy + HTTP mapping
│   │   │   ├── middleware.py      # request id, timing, body limits, error envelope
│   │   │   └── security.py        # auth, rate limiting, CORS
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   ├── openapi.py         # spec export for the contract gate
│   │   │   ├── schemas/           # request and response models, one module per resource
│   │   │   └── routers/           # health, master_resume, resumes, chat, rules, system_prompt, evaluate
│   │   ├── domain/
│   │   │   ├── tailoring.py       # the two-pass generate-then-audit pipeline
│   │   │   ├── evaluation.py
│   │   │   └── rules.py
│   │   ├── resume_schema/         # THE source of truth for the resume contract
│   │   │   ├── models.py          # Pydantic, derived from RenderCV's public model
│   │   │   ├── normalize.py       # returns NormalizeResult(yaml, dropped[]) — closes D-08
│   │   │   ├── sections.py        # per-section normalizers
│   │   │   ├── repair.py          # the backstop, imported once at startup — closes D-17
│   │   │   ├── validate.py        # used by every write path — closes D-04
│   │   │   └── prompt.py          # LLM schema text GENERATED from models — closes D-22
│   │   ├── rendering/
│   │   │   ├── runner.py          # timeout + semaphore + --settings + --locale-catalog
│   │   │   ├── config.py          # RenderProfile, env-overridable — closes D-15
│   │   │   └── errors.py          # parse rendercv stderr into located issues
│   │   ├── llm/
│   │   │   ├── port.py
│   │   │   ├── litellm_adapter.py # + timeout, retry with backoff, token accounting
│   │   │   └── stub.py            # deterministic, used by tests and LLM_MOCK
│   │   ├── pdf/extract.py
│   │   └── db/
│   │       ├── engine.py          # WAL, busy_timeout, foreign_keys, closes connections
│   │       ├── migrate.py         # schema_version + ordered apply — closes D-02
│   │       ├── models.py
│   │       ├── seed.py
│   │       └── repositories/      # master_resume, resumes, chat, rules, system_prompt
│   └── tests/
│       ├── unit/ integration/ db/ resume_schema/ api/
│       └── conftest.py            # ephemeral DB per test, stub LLM, no network
│
├── frontend/
│   └── src/
│       ├── app/                   # layout, providers, onboarding + workspace routes
│       ├── design-system/         # tokens, primitives, theme — see DESIGN-SYSTEM.md §4
│       ├── features/
│       │   ├── workspace/         # shell: nav, document region, inspector
│       │   ├── onboarding/
│       │   ├── document/          # editor, preview, DocumentFrame
│       │   ├── tailor/ evaluate/ assistant/ library/
│       │   └── settings/          # rules, assistant prompt, appearance
│       └── lib/
│           ├── api/               # generated types, zod validation, typed client, SSE
│           └── hooks/
│
├── tests/e2e/                     # hermetic Playwright, data-testid only
│
└── docs/
    ├── ARCHITECTURE.md  API.md  DEPLOYMENT.md  TROUBLESHOOTING.md
    ├── design/DESIGN-SYSTEM.md
    ├── adr/NNNN-*.md
    ├── reports/                   # agent audit and wave reports
    └── archive/planning/          # the 2026-07 planning tree, preserved not deleted
```

### 3.3 Notable moves

| From | To | Why |
|---|---|---|
| `backend/app/` | `backend/src/resumetailor/` | src-layout; the package stops shadowing and becomes installable and importable by its real name |
| `backend/app/database.py` (327 lines) | `db/engine.py` + `db/repositories/*` + `db/models.py` + `db/seed.py` | one file currently holds connection handling, five resources, defaults, and schema bootstrapping |
| `backend/app/yaml_utils.py` (521 lines) | `resume_schema/{normalize,sections,repair,validate,models,prompt}.py` | same file holds the normalizer, the backstop, and the implicit schema definition |
| `backend/app/adapters.py` | `llm/litellm_adapter.py` + `rendering/runner.py` + `pdf/extract.py` | three unrelated adapters in one module |
| `backend/db/schema.sql` | `backend/migrations/0001_initial.sql` | schema becomes versioned rather than re-asserted |
| route handler bodies in `resumes.py`, `evaluate.py` | `domain/tailoring.py`, `domain/evaluation.py` | the generation pipeline is currently a 90-line SSE generator inside a route |
| `frontend/src/components/*.tsx` | `frontend/src/features/*/` | flat component folder with no feature boundary |
| `frontend/src/components/ui/` | `frontend/src/design-system/` | see DESIGN-SYSTEM.md §4.1 for the full component map |
| `test/` | `tests/e2e/` | matches the backend's `tests/` and stops colliding with the singular `test` script name |
| `planning/`, `docs/superpowers/` | `docs/archive/planning/` | preserved as history; they describe a build that has since diverged |

---

## 4. Waves

Wave definitions, roles, and the task contract live in [`AGENTS.md`](./AGENTS.md) §3-4. This section
tracks status. Check a box only when the definition of done in `AGENTS.md` §7 is fully met.

### Wave 0 — Stop the bleeding, then build the gates

Wave 0 grew after the audits. Seven of the P0 findings are both *actively harmful* and *cheap to fix*,
and it is not defensible to spend a week on architecture while a `DELETE` silently corrupts the UI's
view of the database and running the documented test command can wipe the user's real resume. These
land first, as small isolated changes, before any restructuring begins.

**0.A — Emergency P0 triage** (`platform`, `frontend-shell`, `qa-e2e`; one worktree, merged as a unit)

- [x] **0.0** Gitignore `planning/master-resume.yaml` (D-01). *Done 2026-09-18, ahead of the wave, because it was a live exposure.*
- [x] **0.1** Return early on 204 and empty bodies in the API client (D-31). One condition; unblocks three broken delete flows. *Done 2026-09-18. Also fixed D-42's client half in the same three lines: `detail` and `error` are both read and `code` is preserved on a new exported `ApiError`.*
- [x] **0.2** Narrow `getMasterResume`'s blanket catch to 404 only, and add a real error state to the shell (D-32). Stops a backend hiccup from offering the user a button that overwrites their resume. *Done 2026-09-18.*
- [ ] **0.12** Catch the now-rejecting `api.getMasterResume()` at `ChatPanel.tsx:57` (follow-on from 0.2). The call has no `.catch`; before 0.2 the blanket catch hid every failure, so a backend error after a `master_resume_updated` action is now an unhandled rejection. Owned by whoever holds `ChatPanel.tsx`; one line.
- [ ] **0.3** Dirty-state guard on the editor: warn before unmount, and a `beforeunload` handler (D-30). Full draft persistence lands in wave 3; this stops the silent loss now.
- [x] **0.4** Make the e2e stack unable to touch the dev stack (D-29): dedicated compose project name, dynamic host port, `BASE_URL` required rather than defaulted, and ephemeral volumes. *Done 2026-09-18. Deviation: host port is a fixed non-8000 default (`E2E_HOST_PORT`, 18173) rather than a random ephemeral port, so a host-side `npx playwright test` still has a knowable address; `playwright.config.ts` additionally rejects any loopback `BASE_URL` on port 8000. Not verified against a live Docker daemon (unavailable in the execution environment).*
- [x] **0.5** Add `.dockerignore`; fix the two `COPY` orderings so the image stops shipping a darwin `node_modules` and a 345 MB foreign virtualenv (D-34, D-35, D-36). *Done 2026-09-18. Both stages now name their source paths individually rather than copying `frontend/` and `backend/` wholesale, so the fix does not depend on `.dockerignore` alone. Build context 868 MB → ~0.9 MB; estimated image ~1.1–1.3 GB → ~430 MB (not ~400 MB: the ~30 MB `uv` binary stays in the runtime image while `CMD` is still `uv run`, which is task 3.4). `uv` pinned to `0.11.11` by digest. Unverified: no Docker daemon in the agent environment, so nothing was built.*
- [ ] **0.6** Keyboard path to PDF import: real button semantics, focusable input, key handler (D-39).

**0.B — Gates**

- [x] **0.7** `platform` — Purge stale generated directories; untrack `tsconfig.tsbuildinfo`; settle the `.superpowers` policy; `git gc` (D-62). *Done 2026-09-18. Deviation: nothing was deleted from disk. The stale directories (`.playwright-mcp/`, both `.pytest_cache/`, `frontend/.next/`, stray `.DS_Store`) are all ignored now, and task 0.5's `.dockerignore` already excludes every one of them from the build context, so deleting regenerable caches while other agents are running tests against them buys nothing.*
- [x] **0.8** `platform` — ruff, mypy, eslint, prettier, pre-commit, `Makefile` with a `check` target (D-38). *Done 2026-09-18. `make check` runs ruff check, ruff format --check, eslint, prettier --check, mypy, tsc --noEmit, pytest (coverage floor 79%) and jest, and is green. Every gate is configured at the level the existing code passes today; each relaxation is itemised in the config file with a finding count and the task that removes it. Three follow-ups registered below as 0.13, 0.14 and 0.15. Also closes B-05: `pytest-randomly==5.0.0` is in the dev group and the suite passes five consecutive randomised runs.*
- [x] **0.9** `platform` — CI skeleton: lint, typecheck, unit tests, gitleaks on every push (D-38). *Done 2026-09-18. `.github/workflows/ci.yml`: three parallel jobs (backend, frontend, gitleaks) plus one aggregate `ci` check to point branch protection at. No Docker, no LLM call, no API key — `LLM_MOCK=1` is set for the whole workflow. gitleaks runs as the pinned v8.30.1 release binary rather than `gitleaks-action`, which needs a licence key on organization accounts; it scans both the working tree and the full history. Verified locally: history is clean across all 52 commits, and a `git archive` of `HEAD` (what CI actually checks out) is clean.*
- [x] **0.10** `qa-unit` — Fix the settings-cache leak so tests pass in isolation and in any order (D-37). *Done 2026-09-18. 89/89 pass in file order, in reverse order, under five `pytest-randomly` seeds, and each test passes run alone. No test turned out to be genuinely broken once the leak was closed. Deviation: `pytest-randomly` was verified from a scratch install rather than added to `backend/pyproject.toml`, which task 0.8 owns — see the note in §6.*
- [x] **0.11** `orchestrator` — Fold all six audit reports into §2.1; publish them to `docs/reports/`
- [ ] **0.13** `platform` — Clear the backend lint and format debt that task 0.8 had to exempt. Run `make fmt` (`ruff format` + `ruff check --fix`) across `backend/`, then delete the `[tool.ruff.format] exclude` list (20 files) and the `[tool.ruff.lint.per-file-ignores]` `"app/**"` block (26 codes, 153 findings) and the legacy half of the `"tests/**"` block (12 codes, 153 findings). Roughly half the findings are mechanically auto-fixable; the rest are one-line edits. **Do this before wave 1 starts**, not after: every one of these files is rewritten in wave 1.1, and a formatting pass tangled up with a restructure is a diff nobody can review. No other wave-0 agent owns backend Python, so it can start immediately.
- [ ] **0.14** `platform` — Clear the mypy `--strict` debt that task 0.8 had to exempt: 88 errors in `backend/app/`, of which 84 are annotation debt in three codes (`type-arg` 39, `no-untyped-def` 33, `no-untyped-call` 12). The remaining four are real and each is already a registered defect — see the itemised overrides in `backend/pyproject.toml`. Lower value than 0.13 and it overlaps heavily with wave 1.1's rewrite, so it is reasonable to fold this into 1.1 rather than run it separately; the decision is the orchestrator's.
- [ ] **0.15** `platform` + `frontend-shell` — Clear the frontend lint and format debt that task 0.8 had to exempt. Run `npm run format` across `frontend/`, then delete the legacy block from `frontend/.prettierignore` (20 files) and the `src/{components,lib,app}/**` override from `frontend/.eslintrc.js` (7 rules). Three of the seven rules close with wave 2.2 (D-40, D-60) and should stay exempt until then, but `no-unused-vars` is one dead import in `ResumeListPanel.tsx` and should come back now. ~~`src/__tests__/WorkstationShell.test.tsx` and `src/__tests__/api.test.ts`~~ **done 2026-09-18 by `orchestrator`**: both were new code exempted only so 0.8's gate could go green in the commit that introduced it. Formatted and removed from the ignore list immediately, because new code being born exempt is how a legacy block grows. The remaining 18 entries are genuine pre-existing debt and stay until this task runs.

### Wave 1 — Foundations (6 parallel)

- [x] **1.1** `backend-core` — src-layout restructure; settings with `SecretStr` and startup validation; structured logging with request IDs; error envelope; middleware (D-52). *Done 2026-09-18. Deviations: (a) `backend/tests/` keeps its flat layout — §3.2's `tests/{unit,integration,db,resume_schema,api}/` split is not claimed by any task and is not a src-layout prerequisite; folding it into 1.5 is the orchestrator's call. (b) The package is importable but **not installed**: `uv.lock` declares this project `virtual`, so `src/` is reached through `pythonpath` in `pyproject.toml` and `PYTHONPATH` in the `Dockerfile`. Making it a real distribution means regenerating `uv.lock` and reordering the Dockerfile's dependency layer, which belongs to task 3.4. (c) `api/routers/{master_resume,system_prompt}.py` were reformatted, not only moved: the longer absolute import lines crossed `line-length = 88` and neither file was on task 0.8's format-exemption list.*
- [ ] **1.2** `data` — Migrations (D-02), repositories, `UNIQUE` constraints (D-06), indexes and FKs (D-14), WAL and busy_timeout (D-56), connection lifecycle (D-13), ISO timestamps (D-09), backup and restore scripts (D-03)
- [x] **1.3** `rendering` — Move the simulator's fixture PDF out of `backend/tests/` and into the package so the e2e stack can actually render (D-64, and note task 1.1 left `_FIXTURE_PDF` deliberately pointing at the test tree with a comment saying so); render service isolation, subprocess timeout and semaphore (D-07), `--settings` and `--locale-catalog` (D-15, D-16), `NormalizeResult` carrying diagnostics (D-08), canonical schema as the single source (D-22), startup-fail backstop (D-17), theme parity (D-18), `work_experience` normalizer (D-24), declare `phonenumbers` and `pyyaml` (D-19). *Done 2026-09-18. Deviations: (a) `backend/uv.lock` was regenerated — a declared dependency without its lockfile fails `uv sync --locked` in CI, and the file is not on 1.3's ownership list. (b) `pyproject.toml`'s ruff and mypy exemptions still name `adapters`, `simulator` and `yaml_utils`, which no longer exist; mypy prints `unused section(s)` as a note and still exits 0, and ruff ignores non-matching globs, so both gates are green, but tasks 0.13/0.14 should clear the dead entries. (c) `prompts.py` was left alone: it carries the generation and audit prompts, which are guidance rather than schema, and it is not on 1.3's ownership list — only the schema block moved. (d) `docs/ARCHITECTURE.md` still cites the old fixture path and the old module layout; `docs/` is task 1.6's.*
- [x] **1.4** `design-system` — Tokens, Geist, Phosphor, primitives, both themes, a real type scale with a middle register, one extracted `EmptyState` (D-11, D-26). *Done 2026-09-18. Built alongside the shipped UI, not in place of it: the Letterpress tokens are namespaced `--lp-*` and every legacy token stays defined, so `make check` and the ten components under `src/components/` are untouched. Deviation: **Tailwind stays on v3** and decision D6 moves to task 2.3 — see D6 for the evidence. Deviation: `--lp-ink-tertiary` ships darker than the spec value in both themes; the spec's own value fails the AA that its section 7 requires of placeholders and helper text. Findings reported to the orchestrator; `docs/` is out of scope for this task.*
- [ ] **1.5** `qa-unit` — Hermetic harness: ephemeral DB per test, deterministic LLM stub, dynamic ports, no network and no API key required
- [x] **1.6** `docs` — `ARCHITECTURE.md`, `API.md`, `DEPLOYMENT.md`, `TROUBLESHOOTING.md`, `CONTRIBUTING.md`, ADRs 0001-0005; archive the planning tree. *Done 2026-09-18. Screenshots and the README rewrite stay with task 4.5 (D-61), which runs against the shipped UI.*

**Wave 1 is not actually six-way parallel. Resequenced 2026-09-18, before launch.**

The original plan called all six independent. They are not, and running them together would have
produced three agents restructuring the same backend tree from three directions:

- 1.1 moves `backend/app/` to `backend/src/resumetailor/`. 1.2 splits `database.py` and 1.3 splits
  `yaml_utils.py` and `adapters.py` — *files that 1.1 is moving*. Built in parallel worktrees, 1.2 and
  1.3 would each be written against a layout that no longer exists by the time they merge.
- 1.5 owns `backend/tests/`, which 1.1 also relocates.
- 1.1 needs `backend/pyproject.toml` and 1.4 needs `frontend/package.json`, both of which task 0.8
  still holds.

Actual order, by real dependency rather than by wish:

| Batch | Tasks | Gate |
|---|---|---|
| 1-a | **1.6** docs | none, starts immediately |
| 1-b | **1.1** backend-core, **1.4** design-system | task 0.8 merged (releases the two manifests) |
| 1-c | **1.2** data, **1.3** rendering, **1.5** qa-unit | 1.1 merged (the new layout exists to build into) |

**Reconciliation checklist for batch 1-c, recorded 2026-09-18 as 1.5 landed first.**
Task 1.5 built the hermetic test harness against the post-1.1, pre-1.2/1.3 tree in its own worktree,
with no visibility into what 1.2 and 1.3 are doing concurrently in theirs. It flagged its own
re-pointing needs precisely rather than assuming its work merges cleanly. This is the checklist for
whoever performs the merge (orchestrator):

- `conftest.py:isolated_settings` → repoint to `core.config.get_settings`, `deps._backend` (or
  wherever 1.3/2.2 relocate `deps`; a comment in the pre-1.3 `deps.py` already says 2.2 moves it to
  `api/deps.py`, so this may need to move twice).
- `conftest.py:db_path` → **rewrite, not repoint.** 1.2 replaces `database.init_db` with a migration
  runner; the fixture must apply migrations against the fresh `tmp_path` file, not call a function that
  will no longer exist.
- `conftest.py:client` / `clean_dependency_overrides` → repoint to wherever 1.3 lands `app`,
  `get_backend`, `lifespan`.
- **Two LLM stub tables must become one.** `backend/tests/helpers/llm_stub.py` (1.5) and 1.3's
  `llm/stub.py` are byte-identical today (copied verbatim, including the en-dashes that need
  `# noqa: RUF001`). Keep one as the source, have the other import it. If 1.3 changes a canned response
  without this merge, the unit suite and the `LLM_MOCK=true` e2e stack silently disagree.
- `tests/helpers/simulator.py`'s `mock_pdf_bytes` fixture points at `backend/tests/fixtures/mock.pdf`,
  which 1.3 is moving into the package as part of closing D-64. Repoint together.
- `ConfigurableBackendAPI` is now duck-typed rather than subclassing `BackendAPI`, deliberately, so it
  survives 1.3's port-boundary move. Revisit only if 1.3 makes the facade something FastAPI or a router
  actually type-checks at runtime, which nothing does today.

**Deviation, recorded 2026-09-18:** batch 1-b ran in the **shared tree**, not the dedicated worktrees
this table and `AGENTS.md` §5 specify. That was an orchestrator decision, and it held because 1.1 owns
`backend/**` and 1.4 owns `frontend/**` — genuinely disjoint, so there was nothing to collide over. It
had one real cost: task 1.6 was writing documentation against `backend/app/` when 1.1 moved it, and a
large part of that draft had to be rewritten mid-task. Batch 1-c has three agents inside `backend/`
at once and does **not** get the same treatment; worktrees there are not optional.

Peak parallelism is three, not six. On a codebase this size that is the honest ceiling: the backend is
3,300 lines and most of it moves in 1.1, so widening the fan-out buys contention, not speed.

**Integration point I1.** After 1-c. Runs full `make check`. Blocks wave 2 on green.

### Wave 2 — Product surfaces (5 parallel)

- [ ] **2.1** `llm` — Provider abstraction; timeout, retry with backoff, `max_tokens` (D-46); streaming lifecycle; `None`-content guard (D-59); token accounting
- [ ] **2.2** `api-contract` — `response_model` on every route (D-54); OpenAPI export; generated TS types; zod validation; typed client with `AbortController` (D-40); consistent error envelope so `detail` and `code` both reach the UI (D-42); bounded pagination (D-10); SSE error status semantics (D-55)
- [ ] **2.3** `frontend-shell` — Nav, document region, inspector IA; theme toggle; TanStack Query; responsive down to tablet with real breakpoints and a draggable split (D-43)
- [ ] **2.4** `security` — Publish on loopback only as the interim answer to D-28 (see D4, and note the in-container bind stays `0.0.0.0`); rate limiting; input length and body limits (D-47); streaming upload cap (D-48); scrubbed subprocess env (D-49); non-root container and tmpfs render scratch (D-50); opaque client errors with detail logged server-side (D-53); path-traversal guard (D-25); CORS decision recorded
- [ ] **2.5** `backend-domain` — Tailoring and evaluation extracted into services; validate on every write path (D-04); normalize on the render path too (D-57)

**Integration point I2.**

### Wave 3 — Features and hardening (5 parallel)

- [ ] **3.1** `frontend-features` — Tailor and Evaluate on shared JD state (D-12); evaluate the *generated* resume, not only the master (D-45); operate on the editor buffer rather than the last save (D-41)
- [ ] **3.2** `frontend-features` — Library with rename, edit, re-render, sort order, and pagination (D-45); Assistant tab; chat pagination (D-21)
- [ ] **3.3** `backend-domain` — **Assistant tool calling** so the chat can actually perform workstation actions (D-33). This is the single largest product gap and a stated core principle. Until it ships, the README and the in-app copy get corrected to describe what exists.
- [ ] **3.4** `platform` — Real package install with a `[build-system]`, dropping the `PYTHONPATH` workaround (D-65); multi-stage Docker with non-root and `tini` (D-51), compose profiles, backup and restore, release workflow, dependency scanning (D-63)
- [ ] **3.5** `backend-core` — Metrics, health and readiness split (D-58), graceful shutdown, orphan reaper (D-20)
- [ ] **3.6** `qa-unit` — Coverage to target across everything touched in waves 1-2

**Integration point I3.**

### Wave 4 — Verification (4 parallel, no feature work)

- [ ] **4.1** `qa-e2e` — Rebuild the e2e suite, hermetic, `data-testid` only, no reliance on residue from previous runs (D-27, D-29)
- [ ] **4.2** `qa-e2e` — Accessibility (axe) and visual regression baselines (D-44)
- [ ] **4.3** `security` — Full security review of the diff since `main`
- [ ] **4.4** `reviewer` — Adversarial review of every wave
- [ ] **4.5** `docs` — Retake all screenshots against the shipped UI; rewrite the README to match the product (D-61)

---

## 5. Decisions

| # | Decision | Status | Recommendation |
|---|---|---|---|
| **D1** | Replace the dark + gold "tailor's thread" UI with the light-first "Letterpress" direction, or keep and repair it | **DECIDED 2026-09-18: replace.** | Letterpress it is. `docs/design/DESIGN-SYSTEM.md` is now binding, not proposed. Unblocks 1.4, 2.3, 3.1, 3.2. |
| **D2** | Light as the default mode, with system preference and a manual toggle | **DECIDED** (follows D1) | Light default, `prefers-color-scheme` respected, manual toggle in Appearance settings |
| **D3** | Migration mechanism: Alembic vs. numbered `.sql` files plus a `schema_version` table | Open | Numbered SQL. Alembic is heavy for raw sqlite3, and the repository boundary makes a later swap mechanical. ADR 0002. |
| **D4** | Auth model for a single-user app | **DEFERRED 2026-09-18** | Deployment target not yet decided. Interim: publish the container port on the loopback interface only, `"127.0.0.1:8000:8000"` in `docker-compose.yml:7`, and likewise in both start scripts. **Uvicorn must keep binding `0.0.0.0` inside the container** or the Docker bridge cannot reach it: the host-side publish is what currently exposes the app, not the in-container bind. That makes the absence of auth *correct* rather than dangerous. Full auth is designed but not built until the target is known. Tracked as B-03. |
| **D5** | Radix primitives with owned components vs. a full component library | Open | Radix plus owned code. The app is small enough that a full library is more constraint than leverage. |
| **D6** | Tailwind v3 → v4 | **DEFERRED 2026-09-18 to task 2.3** | Not done in 1.4. v4 changes the meaning of utilities the ten un-migrated components use: 15 bare `rounded` (v4 remaps it to today's `rounded-sm`), 3 `outline-none` (renamed `outline-hidden`; in v4 `outline-none` means something else and the JD textareas rely on it for their focus treatment), 2 `ring`/`ring-1` (v3 3px accent, v4 1px currentColor), 2 bare `border` (v4's default border colour is `currentColor`), 2 bare `shadow`. Migrating would visibly change components task 1.4 is forbidden to touch, for no gain the token layer does not already provide. The `lp-*` block in `tailwind.config.ts` holds no value of its own, only `var(--lp-*)` references, so the v4 lift is a mechanical move of that block into `@theme` once 2.3 has deleted the legacy utilities. |
| **D7** | Keep `litellm` as the provider abstraction | Open | Keep. It already gives provider portability, and the port boundary isolates it. |
| **D8** | Scope of assistant tool calling | **DECIDED 2026-09-18: fixed action set.** | Four tools only, matching the action types already declared in `types.ts`: edit the master resume, generate a tailored resume, evaluate, update rules. No general API exposure, and no delete tool. Predictable, testable, and honest about what the assistant can do. ADR 0005. |

---

## 6. Open blockers

| # | Task | Blocker | Needed from |
|---|---|---|---|
| ~~B-01~~ | 1.4, 2.3, 3.1, 3.2 | **Cleared 2026-09-18.** D1 decided: Letterpress. UI work is unblocked. | — |
| B-02 | 1.3 | `planning/master-resume.yaml` does not conform to the schema its own import prompt specifies: all nine certifications use `company`/`position` keys, producing 18 warnings per render that blame the LLM for the document's own shape. Needs a decision: fix the document, or widen the normalizer. | User |
| B-03 | 2.4 | **Still open.** The deployment target is undecided, so the auth model cannot be. Mitigated rather than solved: task 2.4 first restricts the host-side port publish to loopback, which removes the exposure without guessing at the wrong auth design. Revisit before any deploy beyond this machine. | User: where does this actually run? |
| ~~B-04~~ | 3.3 | **Cleared 2026-09-18.** Scope decided: fixed four-tool action set. See D8. | — |
| ~~B-05~~ | 0.8 | **Cleared 2026-09-18.** `pytest-randomly==5.0.0` is in `backend/pyproject.toml`'s dev group, so every local and CI run shuffles test order and prints its seed. Five consecutive randomised runs: 89 passed, coverage 79.68% each time. | — |

---

## 7. Change log

| Date | Task | Role | Change |
|---|---|---|---|
| 2026-09-18 | 1.3 | `rendering` | The RenderCV pipeline is isolated and the resume schema has one source of truth. `adapters.py`, `yaml_utils.py`, `ports.py` and `simulator.py` are gone, split into `rendering/{runner,config,errors,port}.py`, `resume_schema/{models,sections,normalize,repair,validate,prompt}.py`, `llm/{litellm_adapter,stub,port}.py` and `pdf/{extract,port}.py`. **Rendering:** the subprocess runs under `asyncio.wait_for` with an `asyncio.Semaphore` bound, and a timeout now *kills and reaps* the child instead of cancelling the future and orphaning it (D-07); `RenderProfile` holds the three overlay paths plus the timeout and concurrency cap, all overridable by `RENDER_*` env (D-15) — it is its own `BaseSettings` rather than a `core/config.py` edit, because `core/` is not 1.3's. `settings.yaml` is wired in via the real `--settings` flag and no longer carries a person's name (`pdf_title: NAME - Resume`); its `render_command.design`/`locale` keys were removed because RenderCV resolves them relative to the *input* file, which is a per-render temp dir, so naming them there fails validation before anything renders. The locale misdiagnosis is gone: `--locale` does not exist, `--locale-catalog PATH` does, and the YAML-merging workaround that mutated the user's top-level keys is deleted (D-16). **Schema:** `_CV_ALLOWED_KEYS`, `_VALID_NETWORKS` and `_SECTION_KEYS` are now derived from `Cv.model_fields` and RenderCV's `SocialNetworkName` literal, and the import prompt's schema block is generated from the same models — it no longer asks for `design: theme: classic` that the normalizer then strips, and it offers all 17 networks instead of 2 (D-22). `normalize_to_rendercv` returns `NormalizeResult(yaml, dropped)` so a pruned email, phone or network reaches a caller instead of only a log line (D-08; surfacing it in the UI stays with 2.5). The backstop imports RenderCV's internals at module import and fails the boot rather than degrading to a silent no-op at request time (D-17), probes with the theme `design.yaml` actually selects instead of `classic` (D-18), and its prune ordering is unchanged. `work_experience` dispatches to the experience normalizer (D-24). New `validate()` returns `(Document, list[RenderIssue])` for the write paths 2.5 adds; nothing calls it yet, so no endpoint changed. **Also:** the provider key is passed per call instead of being written to `os.environ`, where the rendercv child inherited it (D-49); the stub's fixture PDF moved into the package, so the e2e image can render (D-64); `phonenumbers` and `pyyaml` are declared dependencies (D-19). One correction to the data-pipeline audit: it recommends adding `--dont-generate-typst`, which RenderCV's own help says implicitly disables PDF — it is deliberately not passed. 89 → 118 tests pass, coverage 79.68% → 84.24%, every endpoint keeps its path, status codes and response shape |
| 2026-09-18 | 1.1 | `backend-core` | `backend/app/` is now `backend/src/resumetailor/`, moved with `git mv` so history follows, every import absolute (`resumetailor.*`), `routes/` renamed `api/routers/`. New `core/`: `config.py` (`OPENAI_API_KEY` is a `SecretStr`, the `"mock-key"` default is gone, and `validate_startup_settings` fails the boot rather than the first generation), `logging.py` (JSON lines on stdout, a `request_id` contextvar, and a handler that is actually attached — closes D-52, under which every warning the backend logged was silently dropped), `errors.py` (the exception taxonomy out of `ports.py`, each class carrying its own status and code, replacing four near-identical handlers in `main.py`), `middleware.py` (request id in, request id echoed out, one access line per request, written as raw ASGI so the three SSE routes still stream). `main.py` is an app factory. The eight modules that tasks 1.2, 1.3, 2.2 and 2.5 split were moved unchanged, each carrying a comment naming the task that moves it and where. `db/`, `db/repositories/`, `domain/`, `llm/`, `pdf/`, `rendering/`, `resume_schema/` and `api/schemas/` exist as real packages for those tasks to fill. `Dockerfile` follows the paths and the module target; no other file outside `backend/` changed. Gate configuration was retargeted, not relaxed: the legacy ruff and mypy exemptions now name the pre-restructure modules one by one instead of globbing `app/**`, so `core/`, `main.py`, `ports.py` and everything added from here run under the full rule set and full `--strict`. 89 tests pass, coverage 79.68% → 80.73%, and every endpoint keeps its path, status codes and response shape |
| 2026-09-18 | 0.4 | `qa-e2e` | E2E stack isolated from the dev stack (D-29): compose project `resumetailor-e2e`, image tag `resumetailor-e2e`, host port `${E2E_HOST_PORT:-18173}`, tmpfs storage in place of the persistent `test-db`/`test-pdfs` volumes, `version:` key removed. `BASE_URL` is now required and a loopback `BASE_URL` on port 8000 is refused outright. New `scripts/run_e2e.{sh,ps1}` run the suite and tear the stack down. Spec 06 now clears the list, generates its own two resumes, and awaits the SSE `done` event instead of passing on residue |
| 2026-09-18 | 0.0 | `platform` | `planning/master-resume.yaml` added to `.gitignore` — it held real PII and was one `git add -A` from being published (D-01) |
| 2026-09-18 | 0.1 | `frontend-shell` | API client returns early on 204 and on any empty body, so the three DELETE flows stop failing on success (D-31); error bodies now read `detail` as well as `error` and carry `status` and `code` on a new exported `ApiError` (D-42, client half) |
| 2026-09-18 | 0.2 | `frontend-shell` | `getMasterResume` maps only a 404 to `null`; every other failure reaches `WorkstationShell`, which now renders a retryable error screen instead of the onboarding page whose sample button overwrites the user's resume (D-32). New task 0.12 registered for the uncaught call at `ChatPanel.tsx:57` |
| 2026-09-18 | 0.5 | `platform` | `.dockerignore` added: build context 868 MB → ~0.9 MB and `.env` no longer reaches the daemon (D-34). Both `Dockerfile` stages now copy named source paths after their dependency install instead of copying `frontend/`/`backend/` wholesale, so the darwin `node_modules` (D-35) and the 345 MB conda `.venv` (D-36) cannot enter either stage and the dependency layers cache on manifests alone. Added `PYTHONUNBUFFERED`/`PYTHONDONTWRITEBYTECODE`, pinned `uv` to `0.11.11` by digest, dropped the duplicate `WORKDIR` and the redundant `mkdir`. `rendercv[full]`'s pip-wheel Typst preserved — still no `apt-get` layer |
| 2026-09-18 | 0.11 | `orchestrator` | Six parallel audits completed and published to `docs/reports/`; 63 defects registered in §2.1; wave 0 restructured to front-load seven cheap, actively-harmful P0 fixes ahead of any architectural work |
| 2026-09-18 | — | `orchestrator` | `AGENTS.md`, `PLAN.md`, and `docs/design/DESIGN-SYSTEM.md` created |
| 2026-09-18 | 0.10 | `qa-unit` | Backend suite is order-independent (D-37). A single autouse `isolated_settings` fixture in `backend/tests/conftest.py` now gives every test its own temp `DB_PATH` and `PDFS_DIR` and clears both `get_settings` and `deps._backend` on entry **and** on exit; the 21 per-test `cache_clear()` calls that leaked a `Settings` pointing at a deleted `tmp_path` into the next test are gone. New `db_path`/`pdfs_dir` fixtures replace the hand-rolled `monkeypatch.setenv` + `init_db` preamble in five modules, and `client` now depends on `db_path` because httpx's `ASGITransport` never runs the lifespan that would create the database. No assertion weakened or removed. 89/89 pass in file order, reverse order, five random seeds, and individually |
| 2026-09-18 | 0.7 | `platform` | Repo hygiene (D-62). `frontend/tsconfig.tsbuildinfo` (99 KB build cache) untracked and ignored via `*.tsbuildinfo`. `.superpowers` policy settled: the 19 markdown briefs and reports are preserved under `docs/archive/superpowers-sdd/` with a README recording their provenance, the two that were tracked (`t2-llm-report.md`, `t6-tester-report.md`) are untracked, and `.superpowers/` is ignored as the agent scratch directory it is — the multi-megabyte `review-*.diff`/`.txt` dumps were not archived, being mechanical diffs of commits still in history. `.gitignore` extended to cover `tests/e2e/` Playwright output ahead of the `test/` → `tests/e2e/` move, and to cover `coverage.xml`, `.coverage.*`, `.ruff_cache/` and `.eslintcache` — artefacts task 0.8's tooling began producing mid-wave, none of which were ignored. `git gc`: 534 loose objects / 4.38 MiB → one pack of 528 objects / 2.19 MiB |
| 2026-09-18 | 0.8 | `platform` | Quality gates exist (D-38). `make check` is the single command: ruff check, ruff format --check, eslint, prettier --check, mypy, tsc --noEmit, pytest with a coverage floor, jest — green, with `make` defaulting to `help`. Backend gets ruff (34 rule groups, `line-length = 88`) and mypy `strict = true` in `backend/pyproject.toml`; frontend gets eslint on `recommended-type-checked` plus prettier. Every tool pinned exactly. `--passWithNoTests` removed from the frontend test script, so deleting the frontend tests now fails the build. Coverage floor set at **79%**, the measured level (79.68%, 89 tests, 989 statements) — AGENTS.md §8's 85% is task 3.6's, and a floor the code cannot meet is a broken build, not a gate. `pytest-randomly==5.0.0` added, closing B-05. Pre-commit wires the same tools and versions: fast gates on commit, mypy/eslint/tsc/pytest/jest on push, gitleaks on both, conventional-commit check on the message. **No source file was touched**: every gate is configured at the level the existing code passes today and each relaxation is itemised in the config with a finding count and an owning task — 153 backend lint findings and 20 unformatted backend files (task 0.13), 88 mypy `--strict` errors of which 84 are annotation debt (task 0.14), 7 eslint rules and 20 unformatted frontend files (task 0.15) |
| 2026-09-18 | 0.9 | `platform` | CI exists (D-38). `.github/workflows/ci.yml` on every push, every PR and manual dispatch: `backend` (uv sync --locked, ruff, ruff format, mypy, pytest, coverage artefact), `frontend` (npm ci, eslint, prettier, tsc, jest, next build), `secrets` (gitleaks on the working tree and on all history), and one aggregate `ci` job to point branch protection at. Runs the same tools and versions as `make check`, so local green means CI green. No Docker, no LLM call, no API key: `LLM_MOCK=1` is set workflow-wide. `uv sync --locked` fails if `uv.lock` has drifted from `pyproject.toml`, so a dependency cannot be added without its lockfile. gitleaks is the pinned v8.30.1 release binary rather than `gitleaks-action`, which requires a licence key on organization accounts. Verified locally: history clean across 52 commits, and `git archive HEAD` — what CI checks out — clean |
| 2026-09-18 | 1.6 | `docs` | Contributor documentation exists. New: `docs/ARCHITECTURE.md` (request path, the ports boundary and the four places it leaks, the two-pass generate-then-audit pipeline, the YAML normalize-and-repair chain, the RenderCV/Typst subprocess and why there is no TeX Live, the SSE event vocabulary, the data model, the single-user `user_id='default'` assumption), `docs/API.md` (all 22 endpoints with observed response shapes, both error shapes, the SSE contract, and the three known inconsistencies stated rather than hidden: no `response_model` anywhere, SSE failures at HTTP 200, and DELETE returning 204 on three routes and 200 with a body on two), `docs/DEPLOYMENT.md` (env vars, both compose stacks, volumes, the absent backup story stated as absent with an untested manual procedure, what the healthcheck does not check, and the no-auth loopback rule), `docs/TROUBLESHOOTING.md` (13 real failure modes with symptom, cause and fix), `CONTRIBUTING.md`, and ADRs 0001-0005 with an index. `planning/*.md`, `planning/*.png` and `docs/superpowers/` moved to `docs/archive/planning/` with a README recording the known divergences; `planning/master-resume.yaml` deliberately left in place (PII, gitignored). Every target-versus-today divergence is marked inline. **Deviation:** tasks 1.1 and 1.4 landed in the shared tree mid-task, so the docs were rewritten against the post-1.1 layout (`backend/src/resumetailor/`, `core/` logging, middleware and error handlers, `SecretStr` with startup validation) rather than the pre-restructure one the audits describe; `ARCHITECTURE.md` §2 carries the old-to-new path mapping because all six audit reports still cite the old paths |
| 2026-09-18 | 1.6 | `docs` | Post-1.1 path refresh. `README.md`: the dev-server command was `uvicorn app.main:app`, which no longer starts (now `PYTHONPATH=src ... resumetailor.main:app`, matching the Dockerfile's `CMD` and `PYTHONPATH`), and the normalizer citation now points at `backend/src/resumetailor/yaml_utils.py`. No other README change: the feature copy and screenshots stay with task 4.5. `docs/API.md`, `docs/TROUBLESHOOTING.md`, `docs/DEPLOYMENT.md`, `CONTRIBUTING.md` and the ADRs were already refreshed when 1.1 landed mid-task and needed nothing further. `ARCHITECTURE.md` §2's old-to-new mapping extended to cover the forms the audits actually use beyond file paths: the `app.*` import prefix, the uvicorn target, and the `--cov`/`mypy` arguments, plus an explicit list of what the move did **not** touch (`backend/tests/`, `backend/db/`, `backend/rendercv_config/`, `backend/pyproject.toml`, `test/`, `frontend/`). The remaining `backend/app/` strings in `docs/` are that mapping table itself. `docs/reports/audit-*.md` deliberately untouched: evidence stays reproducible against `e943dfb`. Also corrected the frontend status, since task 1.4 has landed `frontend/src/design-system/` primitives while `frontend/src/components/` is still where every feature component lives |
| 2026-09-18 | 1.4 | `design-system` | Letterpress exists as running code (D-11, D-26). New `frontend/src/design-system/`: a `--lp-*` token layer (colour, type, shape, space, elevation, motion) with light as the base and a full swap on `[data-theme="dark"]`, plus 14 primitives on Radix and Phosphor — Button, IconButton, Input, Textarea, Tabs, Dialog, AlertDialog, Tooltip, Toast, Chip, Skeleton, ProgressRail, EmptyState, ErrorState — each with full state coverage, real keyboard and ARIA behaviour, and jest tests (174 new tests, 202 total). `next-themes` is wired at last (D-11): `data-theme` on `<html>`, `defaultTheme="system"`, no flash. Geist and Geist Mono self-hosted through `next/font/local`. New `/design` route renders every primitive in every state, light and dark side by side. **Nothing legacy was removed**: the old tokens, the old Tailwind keys, `lucide-react`, Inter, Fraunces and `className="dark"` all stay, each with a comment naming task 2.3 as the remover. Contrast verified rather than trusted: 3 of the 7 pairs in DESIGN-SYSTEM.md 2.1 miss their stated ratio and 1 of those (`--ink-tertiary`, claimed 4.6:1 AA, measured 3.44:1) fails outright, so that token was darkened in both themes and a new `--lp-rule-control` added for the 3:1 that WCAG 1.4.11 wants on input borders. The contrast table is now a jest test over `tokens.css`, so section 5's "verified in both themes in CI" is real. Tailwind stayed on v3; D6 moves to 2.3 |
