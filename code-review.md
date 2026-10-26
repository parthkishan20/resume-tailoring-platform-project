# Code Review — ResumeTailor

- **Branch:** `restructure/production-readiness`
- **Reviewed at commit:** `190a002`; gate results re-verified at `1d0b6f9`
- **Date:** 2026-09-22
- **Method:** gates executed locally (ruff, ruff-format, mypy, pytest, eslint, prettier, tsc, jest, `next build`, OpenAPI drift check) + manual read of backend, frontend, infra, CI, E2E and docs

> **Caveat:** another session was committing to this repo throughout the review. Five commits landed mid-pass (`a63f2f6` → `1d0b6f9`). Code findings are pinned to `190a002`; the gate results and the two ✅ items below were re-checked at `1d0b6f9`.
>
> **Fixed while this review was being written:**
> - ✅ **The `openrouter/free` finding is confirmed and fixed** (`1d0b6f9`). The slug genuinely did not exist — OpenRouter answers `404 {"error":{"message":"No endpoints available for openrouter/free"}}`. The default is now `openrouter/openai/gpt-oss-120b`, verified end to end against the live provider. ADR 0008 carries an amendment recording it.
> - ✅ **A local `.env` breaking every render and request** was fixed in `c3aba7c` (`extra="ignore"` on the settings classes).
>
> **Still open at `1d0b6f9`:** every other finding below, including all the lint/format failures — they have now survived three further commits.

---

## Gate results

### Working

- **mypy** — clean: `Success: no issues found in 68 source files`
- **pytest** — 428 passed, 0 failed; coverage 94.90% against a 90% floor
- **eslint** — clean at `--max-warnings=0`
- **tsc --noEmit** — clean
- **jest** — 23 suites, 344 tests, all passing
- **next build** — production build succeeds; 3 static routes emitted, 87.4 kB shared JS
- **OpenAPI contract** — backend-generated spec is **byte-identical** to the committed `frontend/src/lib/api/generated/openapi.json`; zero path or schema drift
- **Shell scripts** — all six `.sh` files pass `bash -n` and all six carry `set -euo pipefail`

### Not working

- **`make check` fails on HEAD, and has for four consecutive commits** (`190a002` → `1d0b6f9`), violating AGENTS.md Rule 3 ("green before done"). Re-verified at `1d0b6f9` with a clean working tree: 7 ruff errors, 1 unformatted Python file, 1 unformatted TypeScript file.
- **ruff check — 5 errors in committed source, 2 in committed tests:**
  - `db/repositories/llm_requests.py:27`, `:42` — E501 line too long (90 > 88)
  - `db/repositories/llm_requests.py:31` — S608 SQL-injection warning (see note below)
  - `llm/litellm_adapter.py:262`, `:366` — E501 line too long (98 > 88, 90 > 88)
  - `tests/test_llm.py:194` — TRY003 + EM101 (string literal passed to `RuntimeError`)
- **ruff format --check fails** — `llm/litellm_adapter.py` would be reformatted
- **prettier --check fails** — `frontend/src/features/assistant/UsageCounter.tsx` is unformatted (lines 27 and 31)
- **CI will fail on this commit** — `.github/workflows/ci.yml` runs `ruff check`, `ruff format --check` and `prettier --check` as blocking steps
- `make check` **cannot be run via the documented path** in this sandbox: `uv` fails to initialise its cache at `~/.cache/uv` ("Operation not permitted"). Gates were run directly from `backend/.venv/bin` instead. Environmental, not a code defect.
- **E2E suite not executed** — Docker daemon unavailable on this machine, so all 10 Playwright specs are **unverified**, not passing.

---

## Backend

### Working

- **Layering is real, not decorative.** `backend_api.py` holds three ports (`LLMPort`, `PDFRenderPort`, `PDFExtractPort`); routes never see LiteLLM, RenderCV or PyMuPDF. The `LLM_MOCK` stub swaps in at `deps.py:16` with no route changes.
- **Connection lifecycle is correct.** `db/engine.py:62-77` — `session()` commits on success, rolls back on `BaseException`, and **closes** in `finally`. Fixes the old `with sqlite3.connect(...)` idiom that leaked a descriptor per call.
- **Pragmas set per connection** (`db/engine.py:49-58`): WAL, `busy_timeout=5000`, `synchronous=NORMAL`, `foreign_keys=ON`.
- **Timestamps computed by SQLite**, not the process clock (`UTC_NOW_SQL`, `db/engine.py:37`) — no timezone leakage.
- **Chat paging is done in SQL.** `db/repositories/chat.py:32-47` — `_RECENT` and `_RECENT_BEFORE` use an inner `ORDER BY id DESC LIMIT ?` re-sorted ascending. Correct newest-N semantics, and `limit` is clamped to 1..100 *in the repository* (`:78`), so no caller can force an unbounded read.
- **Error envelope is disciplined.** `client_message` is a `ClassVar` per error class (`core/errors.py:61`); `str(exc)`/`detail` is operator-only and never reaches the client. SSE error frames read `exc.code` off the exception rather than hard-coding a literal, so a new error subclass propagates correctly.
- **Path containment** — `resolve_within()` (`core/security.py:354-369`) resolves and verifies with `is_relative_to`, correctly rejects an absolute `relative`, and returns `None` → 404 rather than 403 so existence isn't confirmed. Applied at both PDF call sites (`routers/resumes.py:76`, `:120`).
- **Subprocess environment is an allowlist**, not a denylist (`core/security.py:384-437`) — the `rendercv`/Typst child cannot inherit `OPENAI_API_KEY`/`OPENROUTER_API_KEY`. `PYTHONPATH` deliberately excluded.
- **Bounded upload read** — `read_upload_capped()` (`core/security.py:309-348`) reads in 64 KB chunks and aborts one chunk past the cap, instead of materialising the body then checking.
- **Body-size middleware is raw ASGI**, not `BaseHTTPMiddleware` (`core/middleware.py`), which is the correct choice for three long-lived SSE routes. It checks declared `Content-Length` *and* a running total, and the "report disconnect then replace the response" trick at `:236-260` correctly works around FastAPI swallowing exceptions raised inside `receive`.
- **Token-bucket rate limiter is bounded** — `_prune()` (`core/security.py:255-273`) drops fully-refilled buckets and hard-caps tracked clients at 1024, so the limiter store isn't itself a memory-growth vector. Keys on peer address, deliberately **not** `X-Forwarded-For`.
- **Startup validation fails the boot, not the first request** — `validate_startup_settings()` (`core/config.py:146-164`) names the correct env var for the configured provider.
- **Orphan reaper is triple-guarded** (`core/reaper.py:143-208`): snapshot of referenced names, an mtime grace period (`REAPER_DELETE_GRACE_S`, default 300s), **and** a fresh `_currently_linked_to()` DB read as the final word before any `unlink()`.
- **Graceful shutdown actually drains SSE streams** (`main.py:138-154`) rather than letting uvicorn cut them.
- **Secrets are `SecretStr`** and the provider key is passed per-call, never written to `os.environ`.

### Not working

- **✅ FIXED in `1d0b6f9` — the default model `openrouter/free` was not a real OpenRouter model ID.** Was the default in `core/config.py:54`, `.env.example:12`, README, DEPLOYMENT.md and ADR 0008. **Confirmed failure:** the provider answers `404 No endpoints available for openrouter/free`; a fresh install booted green (`validate_startup_settings` only checks the key is non-empty) and then failed every generation, evaluation, chat turn and PDF import. No test caught it — the whole suite runs against the stub, which never resolves a model name. Now `openrouter/openai/gpt-oss-120b`.
- **MEDIUM — the rate-limit *labels* are now wrong for the shipped default.** `LLM_RATE_LIMIT_PER_MINUTE=20` / `_PER_DAY=50` (`core/config.py:81-82`) were OpenRouter's **free-tier** numbers, chosen when the default model was free. The default is now a **paid** slug, and the settings' own comment admits they "label a limit this deployment may not actually be under." **Failure scenario:** the counter next to the assistant turns red at 16 requests/minute and implies a cap that does not exist, or stays green past a real one. The `openrouter/free` fix landed without correcting the numbers it was chosen to match.
- **MEDIUM — nothing validates the model slug at startup.** `validate_startup_settings` (`core/config.py:155-168`) checks only that a key is non-empty. That gap is what let the `openrouter/free` bug reach a booted, healthy-reporting process; it is still open, so the next bad `LLM_MODEL` value fails exactly the same way. A one-call startup probe (or a `--check` mode) would convert a silent runtime failure into a boot failure.
- **MEDIUM — the usage counter undercounts exactly when it matters.** `litellm_adapter.py:187` and `:437` call `_record_request()` **once, before** `_attempt()`, which retries up to `LLM_MAX_ATTEMPTS` (default 3). **Failure scenario:** OpenRouter rate-limits a call, the adapter retries twice, three HTTP requests count against the provider's 20/min quota but the UI counter shows 1. The counter is most wrong precisely when the user needs it to be right.
- **MEDIUM — blocking file I/O on the event loop in `routers/resumes.py:98-100`.** `pdf_path.parent.mkdir(...)` and `pdf_path.write_bytes(pdf_bytes)` run directly in the async handler. Every other blocking call in the codebase goes through `asyncio.to_thread` (the project's own D-05 rule). **Failure scenario:** writing a multi-MB PDF stalls the loop, delaying every concurrent SSE stream. Same issue at `:122` (`pdf_path.unlink`).
- **MEDIUM — `PATCH /api/resumes/{id}` leaves a stale PDF.** Acknowledged in the route's own docstring (`routers/resumes.py:274-276`, D-57's open half): replacing `yaml_content` does not re-render, so `pdf_path` keeps pointing at the previous document. **Failure scenario:** a user edits a resume, sees the save succeed, downloads the PDF, and gets the pre-edit version.
- **MEDIUM — `GET /api/chat` is still unbounded when called with no parameters.** `db/repositories/chat.py:80-81` runs `_ALL` (whole transcript, no limit). The frontend always passes a limit now, but the endpoint is unauthenticated and any caller can force a full-table read. D-21 is only half-closed.
- **LOW — S608 on `llm_requests.py:31` is a lint failure but not an exploitable injection.** The interpolated `_RETENTION` is a module-level constant (`"-2 days"`), not user input. It still fails CI and should be parameterised or `# noqa`'d with a reason.
- **LOW — write amplification in the usage counter.** `record_llm_request()` (`llm_requests.py:28-33`) runs a `DELETE ... WHERE created_at < ...` sweep on **every** insert, i.e. on every provider call. The index makes it cheap, but it's an unnecessary write per call.
- **LOW — log injection possible when `LOG_FORMAT=text`.** `_inbound_request_id()` (`core/middleware.py:316-327`) length-caps and strips the client-supplied `X-Request-Id` but does not remove embedded newlines, and the text formatter interpolates it raw (`core/logging.py:46`). JSON (the default) escapes it, so this only bites a deployment that opts into text logs.
- **LOW — `reaper.py:72` calls `pdf_file.unlink()` without `missing_ok=True`.** If another process removes the file between the check and the unlink, `FileNotFoundError` aborts the whole reap pass, leaving remaining orphans on disk.

---

## Frontend

### Working

- **The API contract is enforced at compile time *and* runtime.** `lib/api/schemas.ts:218` uses an `Exact<LLMUsage, Schemas["LLMUsageResponse"]>` check so a zod schema that drifts from the generated OpenAPI type is a **type error**, not a runtime surprise. Every response also goes through `safeParse` at the boundary (`lib/api/http.ts:65-77`).
- **Every request is cancellable.** `RequestOptions.signal` threads through all of `client.ts`; TanStack Query supplies one to each `queryFn` and aborts on unmount/refetch. `AbortError` is rethrown untouched rather than wrapped.
- **204 responses are handled correctly** — `requestNoContent()` (`http.ts:104-107`) never calls `.json()` on an empty body.
- **SSE readers release the stream on every exit path** — `finally { void reader.cancel() }` (`lib/api/sse.ts:116-120`) covers the last frame, a throw, an abort, and a consumer `break`.
- **SSE frames are schema-validated per event name** (`sse.ts:126-143`), replacing the old `data as {delta: string}` casts; an unknown event name is a hard error rather than an `undefined` appended to the transcript.
- **Query strings use `URLSearchParams`**, not template interpolation (`http.ts:131-137`).
- **Streaming routes' 200-then-error-frame contract is handled** — the readers check `response.ok` for pre-stream failures (413/429/422) *and* surface `error` frames, documented at `sse.ts:84-87`.
- **The new usage-counter feature is fully wired end to end** — migration `0005` → `llm_requests.py` repo → router registered in `main.py:83` → OpenAPI regenerated → zod schema + `Exact<>` guard → `client.ts:54` → `useLlmUsage` hook → `<UsageCounter />` rendered in `AssistantPanel.tsx:52` → 4 unit tests. Nothing half-wired.
- **`UsageCounter` degrades silently** rather than rendering a broken fallback next to a live conversation (`UsageCounter.tsx:23`).

### Not working

- **MEDIUM — the SSE parser does not implement multi-line `data:` frames.** `sse.ts:102-113` yields a frame per `data:` line and resets `currentEvent` to `"message"` immediately after. **Failure scenario:** if a payload is ever split across two `data:` lines (per the SSE spec they concatenate and dispatch on the blank line), the second line is emitted as event `"message"`, and `typedStream` throws `unexpected SSE event "message"` — killing the stream. Not triggered today because the backend serialises with `json.dumps` (`routers/chat.py:38`), which never emits a newline, but the parser is one server-side change away from breaking.
- **LOW — `data:` payloads are `.trim()`ed** (`sse.ts:106`) where the spec strips only one leading space. Harmless for JSON, wrong for any future raw-text frame.
- **LOW — `useLlmUsage` polls every 15s for the entire app lifetime.** `AssistantPanel` is `forceMount`ed in the shell, so the poll runs regardless of which tab is open (`queries.ts:287-306`). `refetchIntervalInBackground` defaults to false so a blurred window pauses it, but a focused idle app still issues ~240 requests/hour for a counter nobody is looking at.
- **LOW — `UsageCounter.tsx` is committed unformatted**, failing `prettier --check` and therefore CI (see Gates).

---

## Infrastructure, CI & tests

### Working

- **Dockerfile is genuinely hardened**: non-root `USER app` (uid 10001), read-only application code, `tini` as PID 1 to forward signals and reap Typst zombies, `/tmp` on tmpfs, `uv` pinned by **version *and* digest**, `--frozen` installs, and `/app/db` + `/app/pdfs` pre-created with the right ownership so volume mounts inherit it.
- **Two-stage build with a correctly cached dependency layer** — `uv sync --no-install-project` before `src/` lands, so editing backend source doesn't re-resolve ~80 packages.
- **Build inputs are copied file-by-file**, not wholesale, so a host's darwin `node_modules` / conda `.venv` can't ride into the linux image (D-35, D-36).
- **Port publish is loopback-only** (`docker-compose.yml:30`, `"127.0.0.1:8000:8000"`) — the documented interim control for an API with no auth, with an explicit comment not to widen it.
- **Healthchecks** defined in both the Dockerfile and compose, with a 60s `start_period`.
- **CI mirrors `make check` and adds `next build`** — the build gate `make check` itself lacks.
- **`pip-audit` is a blocking gate**; `gitleaks` scans both the working tree **and** full git history (`fetch-depth: 0`).
- **A single `ci` aggregate job** exists for branch protection, so adding a job doesn't mean editing protection rules.
- **E2E suite refuses to guess its target.** `playwright.config.ts:15-51` throws if `BASE_URL` is unset **and** explicitly refuses loopback:8000 because that's the real stack holding real resume data and a live API key. This is a genuinely good guard.
- **Known a11y failures are pinned with `test.fail()` and a written rationale** (`09-accessibility.spec.ts:415`, `:447`) rather than deleted or skipped — the test regresses loudly if someone "fixes" it by accident.
- **All six shell scripts** use `set -euo pipefail` and pass `bash -n`.

### Not working

- **HIGH — the E2E suite never runs in CI.** `.github/workflows/ci.yml` defines only `backend`, `frontend`, `audit`, `secrets`, `ci`; `grep -rin "playwright\|e2e" .github/` returns **nothing**. **Failure scenario:** ~1,300 lines across 10 specs — including 467 lines of accessibility tests and 228 lines of visual regression — gate nothing. A PR can break every user-facing flow and still show a green check.
- **HIGH — visual baselines are macOS-only and can't be fixed by just adding a CI job.** Snapshots are committed as `*-chromium-darwin.png` and the config documents them as pinned to "chromium 125 (build v1117) on darwin-arm64". On `ubuntu-latest` every `toHaveScreenshot` assertion fails. Running E2E in CI needs a Linux baseline set first.
- **MEDIUM — the frontend ships with known unpatched advisories.** `next@14.2.35` carries every advisory `npm audit` lists; the fixes were never backported off Next 16. `npm audit` is deliberately non-blocking (`ci.yml:153-156`, documented as D-71), so this is accepted risk rather than an oversight — but it is live.
- **MEDIUM — `docs/API.md` omits three live endpoints:** `GET /api/llm/usage`, `GET /api/health/ready`, `GET /api/metrics`. ADR 0008 explicitly claims "`docs/API.md` … updated to match"; it was not. **Failure scenario:** the API reference is no longer a reliable description of the API.
- **MEDIUM — the two new settings are undocumented everywhere.** `LLM_RATE_LIMIT_PER_MINUTE` and `LLM_RATE_LIMIT_PER_DAY` (`core/config.py:72-73`) appear in **neither** `.env.example`, README, nor `docs/DEPLOYMENT.md`, despite every other `LLM_*` knob being listed in `.env.example` and DEPLOYMENT.md describing them as the configurable labels for the counter.
- **LOW — `env_file: .env` has no `required: false`.** A fresh clone that runs `docker compose up` before copying `.env.example` gets a compose-level failure rather than the app's own `ConfigurationError`.
- **LOW — local/CI Python skew.** The image and CI pin Python 3.12; `requires-python = ">=3.12"` and `ruff target-version = py312`, but this machine's venv is 3.13.5. Local green is therefore not quite the CI-green guarantee the Makefile header claims.
- **LOW — two open a11y defects are pinned but unfixed:** Library rows render `role="button" tabIndex={0}` while nesting real `<button>` children (axe `nested-interactive`, D-76), and `--lp-ink-tertiary` measures 4.49:1 against a 4.5:1 AA requirement.

---

## Top 5, in order

1. **Make HEAD green.** Fix the 7 ruff errors, run `ruff format` and `prettier --write`, then re-commit. CI fails on `1d0b6f9` as it stands, and has failed for four consecutive commits.
2. **Add a startup model probe.** The `openrouter/free` bug is fixed, but the hole that let it ship — a boot that validates the key and never the model — is still open, and the stub-only test suite cannot close it.
3. **Correct the rate-limit labels** (`LLM_RATE_LIMIT_PER_MINUTE`/`_PER_DAY`) to match the now-paid default model, and document both in `.env.example` and `docs/DEPLOYMENT.md`.
4. **Add an E2E job to CI**, and generate Linux visual baselines so it can actually pass. Right now ~1,300 lines of tests gate nothing.
5. **Move `_record_request()` inside the retry loop** in `litellm_adapter.py`, move `write_bytes`/`mkdir`/`unlink` in `routers/resumes.py` onto `asyncio.to_thread`, and document the three missing endpoints in `docs/API.md`.
