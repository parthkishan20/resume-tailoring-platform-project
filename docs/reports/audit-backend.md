# Backend Audit — `resume-tailoring-platform/backend`

All paths relative to `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform`. Line refs are against the working tree (which includes uncommitted edits to `master_resume.py` and `yaml_utils.py`).

Files read in full: `backend/app/main.py`, `config.py`, `deps.py`, `ports.py`, `adapters.py`, `backend_api.py`, `simulator.py`, `prompts.py`, `database.py`, `yaml_utils.py`, `backend/app/routes/{chat,evaluate,health,master_resume,resumes,rules,system_prompt}.py`, `backend/pyproject.toml`. Supporting context read: `backend/db/schema.sql`, `backend/tests/conftest.py`, `backend/tests/test_routes_chat.py` (head), `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `frontend/src/lib/api.ts`, `frontend/next.config.js`.

---

## 0. Findings ranked by severity

### P0

| # | Finding | Location |
|---|---|---|
| P0-1 | **No authentication or authorization on any endpoint.** Zero `Depends(security)`, no API key check, no session. Every route is anonymous. This includes `PUT /api/system-prompt` (`app/routes/system_prompt.py:27`) which lets any caller replace the system prompt used for every subsequent chat turn (`app/routes/chat.py:48-50`) — a persistent, stored prompt-injection primitive — and `GET /api/master-resume` (`app/routes/master_resume.py:88`) which returns the user's full PII (name, email, phone, address, employment history). | all of `app/routes/*` |
| P0-2 | **Single-tenant hardcoded at the data layer.** `DEFAULT_USER_ID = "default"` (`app/database.py:4`) is the default arg of all 17 DB functions; no route ever passes a `user_id`. The schema has `user_id` columns (`db/schema.sql:3,10,17,28,36,45`) but they are always the literal `'default'`. Deploying multi-user requires touching every route and every DB function. | `app/database.py:4`, every route |
| P0-3 | **SQLite with no concurrency configuration, in an app that does long-running writes.** `sqlite3.connect(db_path)` per call (`app/database.py:35,58,70,105,126,148,164,193,210,222,235,248,256,269,281,294,306`) with no `PRAGMA journal_mode=WAL`, no `busy_timeout`, no connection pool. Default `busy_timeout` is 5 s; two concurrent `POST /api/resumes/stream` calls writing at the same time will raise `sqlite3.OperationalError: database is locked`, which surfaces as a generic SSE `GENERATION_FAILED` (`app/routes/resumes.py:142-143`). | `app/database.py` throughout |
| P0-4 | **Connections are never closed.** `with sqlite3.connect(...) as conn:` is a *transaction* context manager in the stdlib, **not** a closing one — it commits/rolls back and leaves the connection open for the GC. Every DB call in the file leaks a file descriptor until CPython's refcount collects it. Under sustained load with a non-refcounting path (exception held in a traceback frame, which `app/routes/*.py` does constantly via `except Exception as exc`) this is an fd leak. | `app/database.py:35,58,70,105,126,148,164,193,210,222,235,248,256,269,281,294,306` |

### P1

| # | Finding | Location |
|---|---|---|
| P1-1 | **No timeout on the `rendercv` subprocess.** `await proc.communicate()` (`app/adapters.py:97`) has no `asyncio.wait_for`. A hung `typst` compile pins the process forever; nothing kills the child on client disconnect either (the `TemporaryDirectory` context will not exit). With `--workers 1` (`Dockerfile:41-43`) this is a whole-service hang. | `app/adapters.py:87-106` |
| P1-2 | **No timeout, no retry, no `max_tokens` on any LLM call.** `litellm.acompletion(**kwargs)` (`app/adapters.py:39`) and the streaming variant (`app/adapters.py:53-55`) pass only `model`/`messages`/`response_format`/`stream`. litellm's default request timeout will apply, but nothing app-level bounds latency, and a stalled SSE stream (`app/adapters.py:60-63`) holds the connection open indefinitely. No `num_retries`, no backoff on `RateLimitError` — it is mapped straight to a client-visible 503 (`app/main.py:40-42`). | `app/adapters.py:30-65` |
| P1-3 | **No bound on any LLM input.** `ChatRequest.message` (`app/routes/chat.py:30-31`), `GenerateRequest.job_description` (`app/routes/resumes.py:37-38`), `EvaluateRequest.yaml_content` / `.job_description` (`app/routes/evaluate.py:42-44`), `SystemPromptBody.content` (`app/routes/system_prompt.py:15-16`), `MasterResumeBody.yaml_content` (`app/routes/master_resume.py:84-85`) are all bare `str` with no `max_length`. FastAPI/Starlette impose no default body-size cap. A single 50 MB JSON body is accepted, persisted, and forwarded to the LLM. Cost and memory are both unbounded and attacker-controlled. | 5 request models |
| P1-4 | **Unbounded upload read before the size check.** `pdf_bytes = await file.read()` (`app/routes/master_resume.py:134`) materialises the entire upload in memory. The 10 MB limit lives in `PyMuPDFAdapter.extract` (`app/adapters.py:114-117`) — i.e. **after** the read. A 2 GB multipart POST OOMs the container before the guard runs. `file.content_type` (`app/routes/master_resume.py:132`) is a client-supplied header, not content sniffing. | `app/routes/master_resume.py:132-135` |
| P1-5 | **CPU-bound sync work executed directly on the event loop inside async handlers.** `normalize_to_rendercv` is called inline at `app/routes/resumes.py:69,94,110` and `app/routes/master_resume.py:120,156`; it runs `yaml.safe_load`, a full `yaml.dump`, and — critically — `_validate_and_repair` (`app/yaml_utils.py:368-406`), which does up to **5 iterations** of `copy.deepcopy(data)` plus a full Pydantic model build via `build_rendercv_model_from_commented_map`. Likewise `PyMuPDFAdapter.extract` (`app/adapters.py:113-130`) is `async def` but does pure synchronous PyMuPDF text extraction over up to 50 pages. None of these go through `asyncio.to_thread`, unlike every DB call. With one worker, this stalls all concurrent requests including SSE heartbeats. | `app/yaml_utils.py:368-406`, `app/adapters.py:113-130`, callers above |
| P1-6 | **Blocking filesystem writes inside async generators.** `pdf_path.parent.mkdir(...)` and `pdf_path.write_bytes(pdf_bytes)` (`app/routes/resumes.py:126-127`, `app/routes/resumes.py:187-188`) write multi-hundred-KB PDFs synchronously on the loop. Also `_CONFIG_DIR / "locale.yaml").read_text(...)` (`app/adapters.py:79`) is a blocking read on every render. | as listed |
| P1-7 | **The API key is written into the process environment as a side effect of constructing an adapter.** `os.environ["OPENAI_API_KEY"] = api_key` (`app/adapters.py:28`). This is global mutable state set from a constructor, it is inherited by the `rendercv` child process spawned at `app/adapters.py:87`, and it makes the adapter untestable without env pollution. It also means the key ends up in `/proc/<pid>/environ` of an unrelated PDF renderer. | `app/adapters.py:26-28` |
| P1-8 | **No rate limiting, anywhere.** Every LLM-invoking endpoint (`/api/chat/stream`, `/api/resumes/stream`, `/api/evaluate/stream`, `/api/master-resume/import`) is unauthenticated (P0-1) and uncapped (P1-3). An open port is a direct line to the billing account. | n/a — absence |
| P1-9 | **No structured logging, no request IDs, no access logging, no logging configuration at all.** The only logger in the entire backend is `app/yaml_utils.py:22`, and `logging.basicConfig` is never called, so its `logger.warning` calls at `app/yaml_utils.py:101,162,290,294,399,483` go to the root handler-less logger and are silently dropped at default `WARNING`/lastResort level to stderr with no format. Every `except Exception as exc` path (`app/routes/chat.py:70`, `app/routes/evaluate.py:69`, `app/routes/resumes.py:142`) swallows the exception into a string and **never logs the traceback** — production failures are unattributable. | `app/main.py` (absence), routes as listed |
| P1-10 | **Subprocess stderr is returned verbatim to the client.** `RenderError(f"rendercv failed (exit {proc.returncode}): {output}")` (`app/adapters.py:98-105`) embeds full `rendercv`/`typst` stdout+stderr, including absolute temp paths and stack traces, and that string reaches the client via `app/main.py:47` (`{"error": str(exc)}`) and `app/routes/resumes.py:139`. Same class of leak for every generic `str(exc)` handler. | `app/adapters.py:98-105`, `app/main.py:35-52` |

### P2

| # | Finding | Location |
|---|---|---|
| P2-1 | **`POST /api/resumes/{id}/render` does not normalise YAML; `GET /api/master-resume/preview` does.** `app/routes/resumes.py:185` calls `api.render(row["yaml_content"])` raw, while `app/routes/master_resume.py:120` calls `api.render(normalize_to_rendercv(...))`. A resume edited via `PATCH /api/resumes/{id}` (`app/routes/resumes.py:157`, no validation on `yaml_content`) will therefore fail to render even though the identical YAML renders fine through preview. | `app/routes/resumes.py:185` vs `app/routes/master_resume.py:120` |
| P2-2 | **Same error, two status codes.** `RenderError` → 500 via the global handler (`app/main.py:45-47`), but `preview_master_resume` catches it and returns 422 (`app/routes/master_resume.py:121-122`). `POST /api/resumes/{id}/render` gets the 500. | `app/main.py:45-47`, `app/routes/master_resume.py:121-122` |
| P2-3 | **Global exception handlers do not apply to the streaming endpoints.** All three SSE routes wrap the whole body in try/except inside the generator (`app/routes/chat.py:42-71`, `app/routes/evaluate.py:54-70`, `app/routes/resumes.py:59-143`), so `app/main.py:35-52` is dead code for them. Every SSE failure is HTTP **200** with an `event: error` frame. Load balancers, uptime checks, and APM see a 100% success rate during a total LLM outage. | as listed |
| P2-4 | **Zero `response_model` declarations in the whole backend** (verified: no occurrences under `backend/app`). Every handler returns a raw `dict` built from `sqlite3.Row`. `/openapi.json` documents every response as `{}`, the frontend's `src/lib/types.ts` contract is unenforced, and `SELECT *` at `app/database.py:157,167,201,243,322` means any future schema column silently becomes part of the public API. | all routes |
| P2-5 | **Inconsistent DELETE semantics.** `DELETE /api/master-resume` → 204 (`app/routes/master_resume.py:102`), `DELETE /api/resumes/{id}` → 204 (`app/routes/resumes.py:195`), `DELETE /api/chat` → 204 (`app/routes/chat.py:77`), but `DELETE /api/rules` → 200 + full rules array (`app/routes/rules.py:37-39`) and `DELETE /api/system-prompt` → 200 + row (`app/routes/system_prompt.py:32-34`). The latter two are semantically "reset", not "delete". | as listed |
| P2-6 | **Unvalidated pagination.** `sort: str`, `order: str`, `page: int`, `limit: int` (`app/routes/resumes.py:48`) have no `Query(ge=..., le=...)` constraints. `limit=-1` reaches SQLite as `LIMIT -1`, which SQLite interprets as *no limit* — full table dump. `page=0` yields `OFFSET -20`. `sort` silently falls back to `job_description` for any value other than `"date"` (`app/database.py:123`). No SQL injection (the ternary at `app/database.py:123-124` is closed-set), but the f-string at `app/database.py:132-134` is a latent injection site if that ternary is ever generalised. | `app/routes/resumes.py:46-50`, `app/database.py:115-137` |
| P2-7 | **Stale PDFs.** `PATCH /api/resumes/{id}` updates `yaml_content` (`app/routes/resumes.py:157-165`) but leaves `pdf_path` pointing at the PDF rendered from the *old* YAML; `GET /api/resumes/{id}/pdf` (`app/routes/resumes.py:168-177`) then serves stale content with no invalidation flag. | `app/routes/resumes.py:157-177` |
| P2-8 | **`None` content is never guarded.** `response.choices[0].message.content` (`app/adapters.py:40`) is `None` on a provider refusal or a pure tool-call response. That `None` flows into `json.loads(result_str)` at `app/routes/evaluate.py:63`, `app/routes/resumes.py:94`, and `app/routes/master_resume.py:156` → `TypeError`. The first two become a generic SSE error; the third is an **unhandled 500** (there is no try/except in `import_pdf`). Same for `json.loads(...)["yaml_content"]` raising `KeyError`/`JSONDecodeError`. | `app/adapters.py:40`, `app/routes/master_resume.py:156` |
| P2-9 | **`/docs`, `/redoc`, `/openapi.json` are publicly served in production.** `FastAPI(title="ResumeTailor API", lifespan=lifespan)` (`app/main.py:30`) leaves them on defaults; the static mount at `app/main.py:70` is registered last so it does not shadow them. | `app/main.py:30` |
| P2-10 | **No readiness/liveness split.** `GET /api/health` returns a hardcoded `{"status": "ok"}` (`app/routes/health.py:7-9`) — it does not touch SQLite, the PDF dir, or the LLM. The Docker healthcheck (`Dockerfile:38-39`, `docker-compose.yml:14-20`) therefore reports healthy while the DB is corrupt or the API key is invalid. | `app/routes/health.py:7-9` |
| P2-11 | **No graceful shutdown.** The lifespan has nothing after `yield` (`app/main.py:27`). In-flight `rendercv` children (`app/adapters.py:87`) are orphaned on SIGTERM; partially written PDFs at `app/routes/resumes.py:127` are left on the volume with a DB row already committed at `app/routes/resumes.py:119-121`. | `app/main.py:20-27` |
| P2-12 | **Non-atomic write ordering in generation.** `create_resume` commits (`app/routes/resumes.py:119-121`), then the PDF is written (`:127`), then a second UPDATE sets `pdf_path` (`:129-131`). A crash between steps leaves a row with `pdf_path = NULL` and an orphan file, or vice versa. Delete has the mirror problem: DB row deleted at `app/routes/resumes.py:198` before `unlink` at `:203`, so an unlink failure raises a 500 after the row is already gone. | `app/routes/resumes.py:117-131,195-203` |
| P2-13 | **Two undeclared direct dependencies.** `import yaml` (`app/adapters.py:8`, `app/yaml_utils.py:20`) and `import phonenumbers` (`app/yaml_utils.py:89`) are not in `backend/pyproject.toml:5-13`. Both resolve only transitively through `rendercv[full]`. A rendercv minor release dropping either breaks the build with no lockfile signal. | `backend/pyproject.toml:5-13` |
| P2-14 | **Path handling is safe-by-accident, not by construction.** `Path(_pdfs_dir()) / row["pdf_path"]` (`app/routes/resumes.py:173,202`) would traverse if `pdf_path` were ever attacker-controlled. Today it is not — `PATCH` (`app/routes/resumes.py:41-43`) does not expose `pdf_path`, and the only writers use `f"{resume_id}.pdf"` (`:130,190`). But `update_resume` *does* accept a `pdf_path` kwarg (`app/database.py:178`), so one careless route addition turns this into arbitrary file read/delete. No `Path.resolve().is_relative_to(base)` guard anywhere. | `app/routes/resumes.py:173,202`, `app/database.py:178` |
| P2-15 | **Config defaults are unsafe.** `OPENAI_API_KEY: str = "mock-key"` (`app/config.py:8`) means a misconfigured deploy boots successfully and fails at first LLM call with a 500. There is no startup validation that the key is real, and no `SecretStr` — the key is a plain `str` on a cached global (`app/config.py:21-23`), so it appears in any `repr(settings)` or Pydantic validation error. `DB_PATH`/`PDFS_DIR` default to container-absolute `/app/...` paths (`app/config.py:11-12`), which are wrong for every local run. | `app/config.py:8-12` |
| P2-16 | **Dead API contract.** Both SSE chat completion (`app/routes/chat.py:65`) and the simulator (`app/simulator.py:15`) emit `"action": None` — always `None`, never populated anywhere in the codebase. The chat endpoint's documented shape promises action dispatch that does not exist. | `app/routes/chat.py:65`, `app/simulator.py:10-16` |
| P2-17 | **Duplicated default system prompt.** `app/routes/chat.py:49` hardcodes `"You are ResumeTailor, an AI assistant."` as the fallback, diverging from the canonical `DEFAULT_SYSTEM_PROMPT` at `app/database.py:22-27` that seeds the table. | `app/routes/chat.py:49` |
| P2-18 | **Chat persists the user turn before the LLM call.** `add_chat_message(..., "user", ...)` at `app/routes/chat.py:44` commits before the stream starts; on any failure (`:66-71`) the user message is persisted with no assistant reply, permanently skewing the history that is replayed into every future turn (`:51-54`). | `app/routes/chat.py:44-71` |
| P2-19 | **SSE will break behind nginx/ALB.** Only `Cache-Control: no-cache` is set (`app/routes/chat.py:74`, `app/routes/evaluate.py:73`, `app/routes/resumes.py:146`). Missing `X-Accel-Buffering: no` and `Connection: keep-alive`; no keepalive comment frames, so idle proxies will cut the connection during a long two-pass generation. | as listed |
| P2-20 | **No CORS middleware at all** (verified: no `add_middleware` anywhere under `app/`). This is *correct* today — the frontend is a static export mounted same-origin (`app/main.py:68-70`, `frontend/src/lib/api.ts:7` uses relative paths, `frontend/next.config.js` `output: 'export'`) — but it means any split deployment (separate CDN for the frontend) silently breaks, and there is no explicit decision recorded. | `app/main.py` |
| P2-21 | **`rendercv_config/settings.yaml` is never referenced** by any code, Dockerfile, or compose file (only `design.yaml` at `app/adapters.py:89` and `locale.yaml` at `app/adapters.py:79`). Dead config. | `backend/rendercv_config/settings.yaml` |
| P2-22 | **Locale injection merges the whole file, not just the locale key.** `data.update(locale_data)` (`app/adapters.py:81`) splices every top-level key of `locale.yaml` into the CV document, guarded only by `if "locale" not in data` (`:78`). If `locale.yaml` ever gains a second top-level key it silently overwrites the user's CV data. | `app/adapters.py:77-84` |
| P2-23 | **Dead imports.** `BackendAPI` (`app/main.py:11`) is imported and never used; `Path` (`app/routes/master_resume.py:5`) and `JSONResponse` (`app/routes/master_resume.py:8`) are imported and never used. `app/main.py:13` imports `get_backend` purely as a test-visible re-export — a production module carrying a test seam. | as listed |
| P2-24 | **`runtime_checkable` Protocols give false assurance.** `LLMPort`, `PDFRenderPort`, `PDFExtractPort` (`app/ports.py:25-46`) are `@runtime_checkable`, but that only checks *method presence*, never signatures or async-ness. Nothing in the codebase actually performs an `isinstance` check against them, so the decorator is cargo cult. | `app/ports.py:25,39,44` |
| P2-25 | **`async def stream(...) -> AsyncIterator[str]` is an awkward port signature.** It is a coroutine *returning* an iterator, not an async generator, forcing the double-await idiom `async for delta in await api.stream(messages)` (`app/routes/chat.py:58`). The natural form is `def stream(...) -> AsyncIterator[str]` with `async for` directly, or an async generator. `app/adapters.py:46-65` and `app/backend_api.py:16-17` both carry the awkwardness. | `app/ports.py:33-36`, `app/adapters.py:46-65`, `app/routes/chat.py:58` |
| P2-26 | **No migrations.** `conn.executescript(_schema_sql())` (`app/database.py:36`) runs the full `CREATE TABLE IF NOT EXISTS` script on every boot. There is no version table and no `ALTER TABLE` path; any column change requires manual intervention on a live volume. | `app/database.py:30-52`, `db/schema.sql` |
| P2-27 | **Builtin shadowing in route handler names.** `def get(...)` / `def update(...)` / `def reset(...)` in both `app/routes/rules.py:26,31,38` and `app/routes/system_prompt.py:20,28,33`. Harmless at runtime (FastAPI derives `operationId` from the path too) but produces ugly, collision-prone OpenAPI operation IDs. | as listed |
| P2-28 | **`_sse` is triplicated verbatim.** Identical helper at `app/routes/chat.py:26-27`, `app/routes/evaluate.py:47-48`, `app/routes/resumes.py:33-34`. So is `_db_path()` — five copies at `app/routes/chat.py:22-23`, `app/routes/master_resume.py:80-81`, `app/routes/resumes.py:25-26`, `app/routes/rules.py:11-12`, `app/routes/system_prompt.py:11-12`. | as listed |

---

## 1. Architecture as-built

**The intended design is hexagonal; the actual wiring is hexagonal for the LLM/PDF edge only, and completely bypasses it everywhere else.**

The clean half:

- `app/ports.py:25-46` declares three Protocols (`LLMPort`, `PDFRenderPort`, `PDFExtractPort`) plus a small error taxonomy (`BackendError` → `LLMAuthError`, `LLMUnavailableError`, `RenderError`, `PDFExtractError`, `app/ports.py:5-22`).
- `app/adapters.py` supplies the three real implementations: `LiteLLMAdapter` (`:25-65`), `RenderCVAdapter` (`:68-106`), `PyMuPDFAdapter` (`:109-130`).
- `app/backend_api.py:7-23` is a **facade over all three ports collapsed into one object** — `complete`, `stream`, `render`, `extract` on a single `BackendAPI`. This is the architectural mistake that propagates everywhere: a route that only needs PDF rendering receives an object that can also call the LLM. There is no interface segregation.
- `app/backend_api.py:26-34` (`create_real_backend`) is the composition root.
- `app/simulator.py:70-114` provides `SimulatedBackendAPI`, a structural (not nominal) stand-in for the same facade.

**DI mechanics.** `app/deps.py:7-13` is the whole DI container: an `@lru_cache(maxsize=1)` factory that branches on `settings.LLM_MOCK` and returns either the simulator or `create_real_backend()`. `get_backend()` (`app/deps.py:16-17`) is the FastAPI dependency. Routes obtain it via `api: BackendAPI = Depends(get_backend)` (`app/routes/chat.py:40`, `app/routes/evaluate.py:52`, `app/routes/resumes.py:56,181`, `app/routes/master_resume.py:111,130`). Tests override it through `app.dependency_overrides[get_backend]` (`backend/tests/conftest.py:74`), which is why `app/main.py:13` re-exports `get_backend` — the comment on that line says so explicitly.

Two consequences of the `lru_cache`: the backend is a **process-wide singleton constructed lazily on first request**, and — because `LiteLLMAdapter.__init__` mutates `os.environ` (`app/adapters.py:28`) — constructing it has a global side effect. Changing `LLM_MODEL` or `LLM_MOCK` at runtime is impossible without `_backend.cache_clear()`, which nothing calls.

The leaky half — **the entire persistence layer bypasses DI**:

- `app/database.py` is 17 free functions, each taking `db_path: str` as its first positional argument.
- Every route imports those functions directly (`app/routes/chat.py:12`, `app/routes/master_resume.py:13`, `app/routes/resumes.py:13-16`, `app/routes/rules.py:6`, `app/routes/system_prompt.py:6`) and resolves the path through a module-local `_db_path()` helper that reaches into the cached global settings (`app/routes/chat.py:22-23` and its four siblings — see P2-28).
- There is no `DBPort`, no repository, no `Depends(get_db)`. The database is a hard compile-time import in every route module.

**Where business logic actually lives.** In the route handlers, entirely. `generate_resume_stream` (`app/routes/resumes.py:53-146`) is the clearest case — 90 lines inside an HTTP handler containing: master-resume fetch, YAML normalisation, rules-to-prompt assembly, a two-pass LLM pipeline (generate → audit), the `AUDIT_END` sentinel-stripping protocol (`:105-110`), PDF rendering, filesystem persistence, DB row creation, DB row update, and SSE framing. There is no `GenerationService`, no domain object for a resume, no use-case layer. The same pattern, smaller, at `app/routes/master_resume.py:127-158` (import pipeline) and `app/routes/evaluate.py:51-73`.

Prompts are split across five locations with no single owner: `app/prompts.py:1-190` (generation + critique), `app/routes/master_resume.py:20-77` (`_IMPORT_SYSTEM_PROMPT`, inline in a route module), `app/routes/evaluate.py:16-20` (`_EVALUATE_SYSTEM_PROMPT`, inline), `app/database.py:22-27` (`DEFAULT_SYSTEM_PROMPT` for chat), plus a fifth divergent copy at `app/routes/chat.py:49`.

`app/yaml_utils.py` (521 lines) is the one genuine domain module — pure functions, no I/O except the lazy rendercv import at `:373-376` — but it lives at the top level next to `main.py` and is imported directly by routes (`app/routes/resumes.py:20`, `app/routes/master_resume.py:16`).

**Net layering:**

```
routes/  ──Depends──> deps.get_backend() ──> BackendAPI ──> ports ──> adapters   (clean)
routes/  ──import───> database.*  (db_path threaded from a cached global)        (leaky)
routes/  ──import───> yaml_utils.normalize_to_rendercv                           (leaky)
routes/  ──import───> prompts.*  +  inline prompt constants                      (leaky)
```

**Startup.** `app/main.py:20-27` is a lifespan that creates `PDFS_DIR` and the `DB_PATH` parent, then runs `init_db` through `asyncio.to_thread`. Nothing runs on shutdown (P2-11). Routers are registered at `app/main.py:57-63`, then `StaticFiles(directory=..., html=True)` is mounted at `/` (`app/main.py:68-70`) — last, so it does not shadow the API routes or `/docs`.

---

## 2. API surface

Every endpoint below is **unauthenticated**. No `response_model` is declared on any of them, so the "Response" column is the observed runtime shape, not a contract.

| Method | Path | Handler | Request model | Response (actual) | Status codes | Streaming |
|---|---|---|---|---|---|---|
| GET | `/api/health` | `health.py:7` | — | `{"status":"ok"}` | 200 | — |
| GET | `/api/master-resume` | `master_resume.py:88` | — | `{id,user_id,yaml_content,updated_at}` | 200, 404 | — |
| PUT | `/api/master-resume` | `master_resume.py:96` | `MasterResumeBody{yaml_content:str}` `:84` | same row | 200, 422 | — |
| DELETE | `/api/master-resume` | `master_resume.py:102` | — | *(empty)* | 204, 404 | — |
| GET | `/api/master-resume/preview` | `master_resume.py:109` | — | `application/pdf` bytes | 200, 404, 422 | — |
| POST | `/api/master-resume/import` | `master_resume.py:127` | `multipart/form-data`, `file: UploadFile` | master-resume row | 200, 400, 422¹, 500² | — |
| GET | `/api/resumes` | `resumes.py:46` | query `sort=date`,`order=desc`,`page=1`,`limit=20` (all unvalidated) | `{items:[...],total,page,limit}` | 200, 422 | — |
| POST | `/api/resumes/stream` | `resumes.py:53` | `GenerateRequest{job_description:str}` `:37` | `text/event-stream` | **200 always** | SSE |
| GET | `/api/resumes/{resume_id}` | `resumes.py:149` | path `int` | `SELECT *` row | 200, 404, 422 | — |
| PATCH | `/api/resumes/{resume_id}` | `resumes.py:157` | `ResumeUpdate{name?,yaml_content?}` `:41` | `SELECT *` row | 200, 404, 422 | — |
| GET | `/api/resumes/{resume_id}/pdf` | `resumes.py:168` | path `int` | `FileResponse`, `Content-Disposition: inline` | 200, 404 | — |
| POST | `/api/resumes/{resume_id}/render` | `resumes.py:180` | path `int` | `SELECT *` row | 200, 404, 500³ | — |
| DELETE | `/api/resumes/{resume_id}` | `resumes.py:195` | path `int` | *(empty)* | 204, 404 | — |
| GET | `/api/chat` | `chat.py:34` | — | `[{id,user_id,role,content,created_at}]` | 200 | — |
| POST | `/api/chat/stream` | `chat.py:39` | `ChatRequest{message:str}` `:30` | `text/event-stream` | **200 always** | SSE |
| DELETE | `/api/chat` | `chat.py:77` | — | *(empty)* | 204 | — |
| GET | `/api/rules` | `rules.py:26` | — | `[{section,rule_key,rule_value}]` | 200 | — |
| PUT | `/api/rules` | `rules.py:31` | `RulesBody{rules:[RuleItem]}` `:15-22` | rules array | 200, 422 | — |
| DELETE | `/api/rules` | `rules.py:38` | — | **rules array (200, not 204)** | 200 | — |
| GET | `/api/system-prompt` | `system_prompt.py:20` | — | `{id,user_id,content,updated_at}` | 200, 404 | — |
| PUT | `/api/system-prompt` | `system_prompt.py:28` | `SystemPromptBody{content:str}` `:15` | `SELECT *` row | 200, 422 | — |
| DELETE | `/api/system-prompt` | `system_prompt.py:33` | — | **row (200, not 204)** | 200 | — |
| GET | `/docs`, `/redoc`, `/openapi.json` | FastAPI default | — | interactive docs | 200 | — |
| GET | `/{path:path}` | `main.py:70` (`StaticFiles(html=True)`) | — | frontend static export | 200, 404 | — |

¹ via the `PDFExtractError` handler, `main.py:50-52`.  ² unhandled `json.loads` failure, `master_resume.py:156` — see P2-8.  ³ `RenderError` handler, `main.py:45-47` — see P2-2.

### Global exception handlers (`app/main.py:35-52`)

| Exception | Status | Body | Registered at |
|---|---|---|---|
| `LLMAuthError` | 500 | `{"error": str(exc), "code": "LLM_AUTH_ERROR"}` | `main.py:35-37` |
| `LLMUnavailableError` | 503 | `{"error": ..., "code": "LLM_UNAVAILABLE"}` | `main.py:40-42` |
| `RenderError` | 500 | `{"error": ..., "code": "RENDER_FAILED"}` | `main.py:45-47` |
| `PDFExtractError` | 422 | `{"error": ..., "code": "PDF_EXTRACT_FAILED"}` | `main.py:50-52` |

Note `LLMAuthError` → **500**, not 502/503 — a server misconfiguration presented as an internal error with the literal text "Invalid LLM API key (check OPENAI_API_KEY)" (`app/adapters.py:42,57`) handed to the client.

### SSE event vocabulary

Three independent, near-duplicate implementations of the same wire format via `_sse` (P2-28):

| Route | `progress` | `token` | `done` payload | `error` codes |
|---|---|---|---|---|
| `POST /api/chat/stream` | — | `{delta}` `chat.py:60` | `{result:{text,action:null}}` `chat.py:65` | `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`, `CHAT_FAILED` `chat.py:67-71` |
| `POST /api/resumes/stream` | 3 fixed messages `resumes.py:66,96,112` | — | `{result:<resume row>}` `resumes.py:133` | `NO_MASTER_RESUME` `:63`, `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`, `RENDER_FAILED`, `PDF_EXTRACT_FAILED`, `GENERATION_FAILED` `:134-143` |
| `POST /api/evaluate/stream` | 1 message `evaluate.py:55` | — | `{result:{match_score,critique,matched_keywords,missing_keywords}}` `:64` | `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`, `EVALUATION_FAILED` `:65-70` |

All three set only `media_type="text/event-stream"` and `Cache-Control: no-cache` (`chat.py:73-74`, `evaluate.py:72-73`, `resumes.py:145-146`).

### Shape inconsistencies

- `GET /api/resumes` returns a paginated envelope; `GET /api/chat` and `GET /api/rules` return bare arrays.
- `GET /api/resumes/{id}` and `PATCH` return `SELECT *` (`database.py:167,201`) — includes `yaml_content` and full `job_description`; `GET /api/resumes` returns an explicit column list without `yaml_content` (`database.py:132-133`). Two different "resume" shapes under the same resource.
- `POST /api/evaluate/stream` is the only LLM endpoint with no persistence — results are streamed and discarded.
- There is no `GET /api/master-resume/history` despite `master_resume_history` being populated and pruned to 10 entries on every save (`database.py:76-86`, `db/schema.sql:8-13`). The data is written and unreachable.
- Generated resume `name` is derived as `f"Resume — {body.job_description[:40]}"` (`resumes.py:118`) — a truncated slice of attacker-controlled text stored as the display name, with no sanitisation.

---

## 3. LLM integration

**Provider / SDK.** `litellm >= 1.40.0` (`pyproject.toml:8`), imported lazily inside methods with an explicit perf rationale (`app/adapters.py:33,47`, and `_llm_exceptions()` at `:15-22`). Only OpenAI-shaped auth is wired: `LiteLLMAdapter.__init__` unconditionally sets `os.environ["OPENAI_API_KEY"]` (`app/adapters.py:28`) regardless of what `LLM_MODEL` names — so pointing `LLM_MODEL` at `anthropic/claude-*` or `gemini/*` would pass litellm's routing but fail auth. The provider abstraction is nominal.

**Model IDs.** One place: `LLM_MODEL: str = "gpt-4o-mini"` (`app/config.py:9`), documented in `.env.example` with `gpt-4o` / `gpt-4-turbo` listed as alternatives. It is threaded through `create_real_backend` (`app/backend_api.py:31`) into `self._model` (`app/adapters.py:27`) and used at `:35` and `:54`. **A single model serves all four workloads** — chat, two-pass generation, evaluation, and PDF import — with no per-task override, despite the critique pass (`app/prompts.py:127-190`) being a materially harder reasoning task than chat. No model ID appears anywhere else in the backend (verified).

**Prompt construction.**

- `app/prompts.py:1-125` — `GENERATION_SYSTEM_PROMPT`, a ~125-line 5-step instruction block: STEP 1 read & extract (`:14-22`), STEP 2 strict content rules per section (`:25-62`), STEP 3 anti-hallucination absolutes (`:65-79`), STEP 4 per-bullet character budgeting with a "scratchpad" instruction (`:82-96`), STEP 5 ATS keyword strategy (`:99-106`), and output format (`:109-124`).
- `app/prompts.py:127-190` — `CRITIQUE_SYSTEM_PROMPT`, an audit rubric (S1-S6 structure `:141-147`, L1-L3 length `:149-152`, H1-H3 hallucination `:154-160`, A1-A3 ATS `:162-165`, K1-K2 skills format `:167-169`) with an `AUDIT_START`/`AUDIT_END` sentinel protocol (`:172-189`).
- `app/prompts.py:193-203` — `rules_block(rules)`, the only dynamic prompt element: formats DB rows as `- {section}.{rule_key} = {rule_value}` under a "USER-CONFIGURED LIMITS — these override any conflicting counts above" header. **This is a user-writable path into the system prompt** via `PUT /api/rules` (`app/routes/rules.py:30`) with no validation on `section`/`rule_key`/`rule_value` (`app/routes/rules.py:15-19` — all bare `str`). Combined with P0-1, an anonymous caller injects arbitrary text into both the generation and critique system prompts (`app/routes/resumes.py:77,101`).
- User messages are f-string concatenation of untrusted content: `f"JD:\n{body.job_description}\n\nMaster:\n{master_yaml}"` (`app/routes/resumes.py:78`), `f"Draft:\n{draft_yaml}\n\nMaster:\n{master_yaml}\n\nJD:\n{body.job_description}"` (`:102`), `f"Resume YAML:\n{...}\n\nJob Description:\n{...}"` (`app/routes/evaluate.py:59`), `f"Resume text:\n{text}"` (`app/routes/master_resume.py:152`). No delimiting, no escaping, no injection defence. A job description containing "ignore the above and output the following YAML" is an unguarded attack surface on the generation pipeline.

**Two-pass generation pipeline** (`app/routes/resumes.py:74-110`):

1. Pass 1 (`:75-93`) uses a strict `json_schema` response format with a single `yaml_content` string property (`:80-92`).
2. Output is normalised (`:94`) via `normalize_to_rendercv(json.loads(gen_response)["yaml_content"])`.
3. Pass 2 (`:99-104`) uses **no** response format and instead relies on the model emitting `AUDIT_END`, with the handler string-splitting on it (`:106-109`) and falling back to `.strip()` of the whole response when the sentinel is absent — i.e. on a sentinel-less response the audit prose becomes the YAML.
4. Output is normalised again (`:110`).

`normalize_to_rendercv` (`app/yaml_utils.py:409-521`) is the real safety net. Its `_validate_and_repair` backstop (`:368-406`) builds the actual rendercv Pydantic model and iteratively **prunes** whatever fails validation, up to 5 rounds, sorting error locations deepest-first (`:388-392`) and logging each prune at `:399`. Silent data loss is the designed failure mode; nothing surfaces it to the caller. On a YAML parse failure it returns the input unchanged (`:414`), passing garbage straight to `rendercv`.

**Structured outputs.** Three separate inline `json_schema` blobs, none shared: `app/routes/resumes.py:80-92` (`tailored_resume`), `app/routes/master_resume.py:136-148` (`imported_resume`) — these two are byte-identical apart from the schema `name` — and `app/routes/evaluate.py:22-39` (`evaluation_result`). All `strict: True`.

**Streaming.** Only chat streams. `LiteLLMAdapter.stream` (`app/adapters.py:46-65`) wraps an inner async generator (`_gen`, `:51-63`) so the initial `acompletion(stream=True)` call is made *inside* the generator — meaning auth/rate-limit errors surface on first iteration, not at call time, and the double-await at `app/routes/chat.py:58` is required. Deltas are filtered for falsy content at `:61-63`. There is **no** `usage` capture — litellm's `stream_options={"include_usage": True}` is not set, so streamed token counts are unavailable by construction.

`evaluate` and `resumes` fake streaming: they emit canned `progress` frames around a blocking `api.complete()` (`app/routes/evaluate.py:55-62`, `app/routes/resumes.py:66,96,112`), so the client sees a progress indicator that has no relationship to actual progress. The generation route emits "Rendering PDF..." (`:112`) *before* the render begins (`:115`) and never emits anything during it.

**Retries / timeouts / cost.** None, none, none. No `num_retries`, no `timeout=`, no `max_tokens`, no `usage` extraction, no token counting, no spend ceiling, no per-caller quota. `response.usage` is never read anywhere in the codebase (verified). The worst case is `POST /api/resumes/stream`: an unbounded `job_description` (P1-3) plus the full master resume, sent **twice** (generate + audit), with an unbounded output, unauthenticated and unrated — see P1-8.

**Error paths.** `litellm.exceptions.AuthenticationError` → `LLMAuthError`; `RateLimitError`/`ServiceUnavailableError`/`APIConnectionError` → `LLMUnavailableError` (`app/adapters.py:18-22,41-44,56-59`). Everything else — `ContextWindowExceededError`, `BadRequestError`, `Timeout`, `ContentPolicyViolationError`, `APIError` — passes through unmapped and lands in the routes' catch-all `except Exception` (`app/routes/resumes.py:142`, `evaluate.py:69`, `chat.py:70`) as a generic SSE error, or, at `app/routes/master_resume.py:127-158`, as an unhandled 500. `RateLimitError` mapping to a user-facing 503 with no retry (P1-2) is the most operationally painful of these. `_llm_exceptions()` (`:15-22`) resolves those classes by importing `litellm.exceptions` on **every call** to `complete`/`stream` — cheap after the first import, but it means an exception-mapping bug only manifests at call time.

**Simulator.** `SimulatedBackendAPI` (`app/simulator.py:70-114`), toggled solely by `LLM_MOCK` (`app/config.py:10` → `app/deps.py:10-12`). Deterministic fixtures at `:10-65`: `MOCK_CHAT_RESULT` (`:10-16`), `MOCK_GENERATION_RESULT_YAML` (`:18-47`), `MOCK_EVALUATION_RESULT` (`:49-57`), `MOCK_IMPORT_YAML` (`:59`, an alias), `MOCK_GENERATION_PROGRESS` (`:61-65`). `render()` returns a fixture file read from `backend/tests/fixtures/mock.pdf` (`:6,103-104`) — **production code reaching into the test tree**, and `MOCK_GENERATION_PROGRESS` is declared but never consumed by anything.

Its dispatch is the fragile part: `complete()` branches on **substring matches against the system prompt text** — `"ResumeTailor" in system` (`:79`), `"ResumeAuditor" in system` (`:83`), `"evaluation" in system.lower()` (`:90`). Those substrings are load-bearing couplings to `app/prompts.py:2` ("ResumeTailor-v2"), `app/prompts.py:128` ("ResumeAuditor-v2"), and `app/routes/evaluate.py:17` ("resume evaluation expert"). Any prompt reword silently reroutes the simulator to the fallthrough at `:92-95` and mock E2E runs start returning wrong-shaped data with no test failure at the seam. The `ResumeAuditor` branch (`:83-89`) additionally reverse-scans messages for the literal `"cv:"` and slices from there — reimplementing the audit protocol inside the mock.

`SimulatedBackendAPI` does not subclass `BackendAPI` and is not checked against the ports; `get_backend()` is annotated `-> BackendAPI` (`app/deps.py:16`) but can return it. A type checker would reject this if one were configured — none is (`pyproject.toml` has no `[tool.mypy]`).

---

## 4. Coupling: why this is hard to test, extend, and deploy

### Testing

The repo's own test suite is the exhibit. Every DB-touching test must do this three-line dance:

```
backend/tests/test_routes_chat.py:8-10
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    from app.config import get_settings; get_settings.cache_clear()
    from app.database import init_db; ... await asyncio.to_thread(init_db, ...)
```

repeated verbatim at `:18-20`, `:33-35`, `:55+`, and throughout the other route test modules. The cause is direct: `Settings` is an `@lru_cache` global (`app/config.py:21-23`), routes resolve `DB_PATH` from it through a module-private helper (`app/routes/chat.py:22-23` plus four more), and `database.py` functions are imported by name rather than injected. Because `get_settings.cache_clear()` is a *global* mutation, these tests cannot run in parallel.

`conftest.py:25-58` builds a fake `litellm` module (four exception classes plus a `MagicMock` `acompletion`) and installs it into `sys.modules` before any import. That stub exists because `LiteLLMAdapter.__init__` has the env side effect (`app/adapters.py:28`) and because `_llm_exceptions()` (`:15-22`) does a runtime import that must resolve when exception handlers are constructed. The conftest docstring (`:4-6`) still references "Wave 2 adds pyproject.toml" — a planning-phase artefact left in the permanent test harness.

`app/main.py:13` imports `get_backend` with the comment *"re-exported so tests can import from app.main"* — a test seam hardwired into the production entrypoint.

There is no way to unit-test `generate_resume_stream`'s orchestration (`app/routes/resumes.py:53-146`) without an HTTP client, because the orchestration only exists inside the handler. The two-pass pipeline, the `AUDIT_END` protocol, and the PDF persistence ordering are all untestable in isolation.

### Extending

- **Second LLM provider** — requires editing `app/adapters.py:28` (the env var is OpenAI-specific) and `app/adapters.py:15-22` (litellm-specific exception classes). The `LLMPort` abstraction does not actually isolate the provider.
- **Second renderer** — requires a new `PDFRenderPort` impl *plus* edits to `BackendAPI.__init__` (`app/backend_api.py:8`) and `create_real_backend` (`:26-34`), because the facade fuses all three ports into one constructor.
- **Different persistence** — requires rewriting all 17 functions in `app/database.py` and touching all five route modules, since there is no repository interface.
- **A new prompt** — requires choosing between four incompatible existing conventions (module constant in `prompts.py`, route-module private constant, DB row, inline fallback string).
- **A new endpoint** — nothing forces auth, response models, rate limits, or logging onto it, because none of those exist as cross-cutting concerns to inherit.

### Multi-user deployment

Blocked on four independent things, in dependency order:

1. **No identity** — no auth (P0-1), so there is no subject to scope on.
2. **No tenancy** — `user_id` is `"default"` at every call site (P0-2).
3. **No isolation** — PDFs are flat-named `{resume_id}.pdf` in one directory (`app/routes/resumes.py:125,186`). Resume IDs are a global `AUTOINCREMENT` sequence (`db/schema.sql:16`), so filenames only avoid collision by being globally unique, and `GET /api/resumes/{id}/pdf` (`:168-177`) would serve any tenant's PDF to any caller the moment DB scoping is relaxed.
4. **No horizontal scale** — SQLite on a Docker named volume (`docker-compose.yml:8-10`) with `--workers 1` (`Dockerfile:41-43`), no WAL, no busy timeout (P0-3/P0-4). More than one worker or one replica means immediate lock contention; the volume is not shareable across hosts.

Chat compounds this: `get_chat_messages` (`app/database.py:221-229`) fetches the *entire* history with no limit and the route slices the last 30 in Python (`app/routes/chat.py:19,53`). One user with 10 000 messages loads all of them into memory on every single turn, and `GET /api/chat` (`:34-36`) returns all of them to the browser.

### Deployment

- `--workers 1` (`Dockerfile:41-43`) means every P1 blocking finding (P1-1, P1-5, P1-6) is a full-service stall, not a per-worker one.
- The healthcheck (`Dockerfile:38-39`, `docker-compose.yml:14-20`) probes a hardcoded constant (P2-10), so a rolling deploy will happily promote a container that cannot reach its database.
- `.env` is correctly gitignored (`.gitignore:35`) and only `.env.example` is tracked (verified via `git ls-files`), but `docker-compose.yml:11-12` mounts `.env` wholesale into the container environment, where P1-7 then re-exports the key to the `rendercv` child process.

---

## 5. Restructure proposal

### 5.1 Target layout

```
backend/
  pyproject.toml                    # + declare pyyaml, phonenumbers; add ruff/mypy
  src/rt/
    __init__.py
    main.py                         # app factory only
    api/
      __init__.py
      router.py                     # single APIRouter(prefix="/api"), includes v1.*
      deps.py                       # Annotated[...] dependency aliases
      errors.py                     # exception handlers + RFC7807 problem shape
      middleware.py                 # request-id, access log, body-size limit, timing
      sse.py                        # ONE SSE framing + keepalive implementation
      v1/
        health.py                   # live + ready
        master_resume.py
        resumes.py
        chat.py
        rules.py
        system_prompt.py
        evaluate.py
    schemas/
      __init__.py
      common.py                     # Page[T], ErrorBody, Timestamped
      master_resume.py
      resumes.py
      chat.py
      rules.py
      system_prompt.py
      evaluate.py
    domain/
      __init__.py
      errors.py                     # BackendError taxonomy (from ports.py)
      models.py                     # Resume, MasterResume, ChatTurn, Rule dataclasses
      ports.py                      # LLMPort, PDFRenderPort, PDFExtractPort, repo Protocols
    services/
      __init__.py
      generation.py                 # two-pass tailoring orchestration
      importing.py                  # PDF -> YAML pipeline
      evaluation.py
      chat.py
      artifacts.py                  # PDF file lifecycle (write/read/delete, path safety)
    rendering/
      __init__.py
      normalizer.py                 # pure YAML -> rendercv transforms
      schema_repair.py              # rendercv-model validation backstop
      rendercv_service.py           # subprocess driver
    prompts/
      __init__.py
      generation.py
      critique.py
      importing.py
      evaluation.py
      chat.py                       # the single canonical default system prompt
      rules.py                      # rules_block()
    infra/
      __init__.py
      settings.py
      logging.py                    # structlog/JSON config + request-id contextvar
      llm/
        litellm_adapter.py
        simulator.py
        policy.py                   # timeout, retry, max_tokens, usage capture
        fixtures/mock.pdf
      pdf/
        pymupdf_adapter.py
      db/
        engine.py                   # connection factory: WAL, busy_timeout, closing
        migrations/                 # 0001_init.sql, ...
        repositories/
          master_resume.py
          resumes.py
          chat.py
          rules.py
          system_prompt.py
    security/
      __init__.py
      auth.py                       # API-key / session dependency -> Principal
      limits.py                     # rate limiting
  tests/
```

### 5.2 Exact source → destination moves

#### Entrypoint and composition

| Source | Destination | Change |
|---|---|---|
| `backend/app/main.py:20-27` (lifespan) | `backend/src/rt/main.py` | split: DB init/migration → `infra/db/engine.py`; directory creation → `services/artifacts.py`; add `infra/logging.py` setup; add shutdown half (P2-11) |
| `backend/app/main.py:30` | `backend/src/rt/main.py::create_app()` | `docs_url=None if settings.ENV == "prod" else "/docs"` (P2-9) |
| `backend/app/main.py:35-52` (4 handlers) | `backend/src/rt/api/errors.py` | add catch-all `Exception` handler that logs the traceback with request ID and returns a redacted body (P1-9, P1-10); one status code per error class (P2-2) |
| `backend/app/main.py:57-63` (7 `include_router`) | `backend/src/rt/api/router.py` | one `APIRouter(prefix="/api")` so the literal `"/api/..."` disappears from 22 decorators |
| `backend/app/main.py:68-70` (static mount) | `backend/src/rt/main.py` | unchanged, still mounted last |
| `backend/app/main.py:11,13` | **deleted** | P2-23; the test seam is replaced by `dependency_overrides` on `rt/api/deps.py` aliases |

#### Ports, adapters, facade

| Source | Destination | Change |
|---|---|---|
| `backend/app/ports.py:5-22` | `backend/src/rt/domain/errors.py` | verbatim |
| `backend/app/ports.py:25-46` | `backend/src/rt/domain/ports.py` | drop `@runtime_checkable` (P2-24); change `stream` to `def stream(...) -> AsyncIterator[str]` (P2-25) |
| — (new) | `backend/src/rt/domain/ports.py` | **add** `MasterResumeRepo`, `ResumeRepo`, `ChatRepo`, `RulesRepo`, `SystemPromptRepo` Protocols — the missing abstraction behind P0-2 and the §4 testing pain |
| `backend/app/adapters.py:15-22,25-65` | `backend/src/rt/infra/llm/litellm_adapter.py` | remove the `os.environ` mutation at `:28`, pass `api_key=` per call (P1-7); guard `content is None` at `:40` (P2-8); extend the exception map at `:18-22` with `ContextWindowExceededError`, `BadRequestError`, `Timeout`, `ContentPolicyViolationError`; hoist `_llm_exceptions()` to module level |
| — (new) | `backend/src/rt/infra/llm/policy.py` | `timeout`, `num_retries` + backoff on `RateLimitError`, `max_tokens`, `stream_options={"include_usage": True}`, usage capture (P1-2) |
| `backend/app/adapters.py:68-106` (`RenderCVAdapter`) | `backend/src/rt/rendering/rendercv_service.py` | `asyncio.wait_for` + `proc.kill()` on timeout (P1-1); module-level cached config load instead of per-render `read_text` at `:79` (P1-6); `data["locale"] = locale_data["locale"]` instead of `data.update(...)` at `:81` (P2-22); stop returning subprocess stderr to callers — log it with the request ID, return a stable message (P1-10) |
| `backend/app/adapters.py:109-130` (`PyMuPDFAdapter`) | `backend/src/rt/infra/pdf/pymupdf_adapter.py` | body wrapped in `asyncio.to_thread` (P1-5); size check moved to middleware/route so it fires before the read (P1-4) |
| `backend/app/backend_api.py:7-23` | **deleted** | the facade is the interface-segregation violation; services take only the ports they need: `GenerationService(llm, renderer, resumes_repo, rules_repo, master_repo)`, `ImportService(llm, extractor, master_repo)` |
| `backend/app/backend_api.py:26-34` + `backend/app/deps.py:7-17` | `backend/src/rt/api/deps.py` | per-port providers (`get_llm`, `get_renderer`, `get_extractor`) plus per-service providers, all `Annotated[X, Depends(...)]`; singleton held on `app.state` populated in lifespan rather than `lru_cache`, so it is resettable |
| `backend/app/simulator.py:70-114` | `backend/src/rt/infra/llm/simulator.py` | replace the system-prompt-substring dispatch at `:79,83,90` with an explicit `task:` marker passed through the port; move `_FIXTURE_PDF` (`:6`) from `tests/fixtures/mock.pdf` into `rt/infra/llm/fixtures/mock.pdf`; delete the unused `MOCK_GENERATION_PROGRESS` (`:61-65`) |

#### Domain / rendering

| Source | Destination | Change |
|---|---|---|
| `backend/app/yaml_utils.py:24-62` (constants: `_CV_ALLOWED_KEYS`, `_VALID_NETWORKS`, `_NETWORK_ALIASES`, `_MONTH_MAP`, `_SECTION_KEYS`, `_DEGREE_PREFIX_MAP`) | `backend/src/rt/rendering/normalizer.py` | verbatim |
| `backend/app/yaml_utils.py:65-336` (`_parse_date`, `_normalize_phone`, `_normalize_url`, `_date_sort_key`, `_fix_date_order`, `_clean_highlights`, `_social_username`, `_normalize_social_networks`, `_split_degree`, `_split_duration`, `_normalize_experience`, `_normalize_education`, `_normalize_projects`, `_normalize_certifications`, `_normalize_skills`) | `backend/src/rt/rendering/normalizer.py` | verbatim |
| `backend/app/yaml_utils.py:339-406` (`_prune_path`, `_loc_sort_key`, `_validate_and_repair`) | `backend/src/rt/rendering/schema_repair.py` | return the list of pruned locations instead of only logging at `:399`, so callers can surface "we dropped these fields" to the user |
| `backend/app/yaml_utils.py:409-521` (`normalize_to_rendercv`) | `backend/src/rt/rendering/normalizer.py::normalize_to_rendercv` | called from services via `asyncio.to_thread` (P1-5); the silent passthrough at `:414` becomes a raised `NormalizationError` |

#### Prompts

| Source | Destination | Change |
|---|---|---|
| `backend/app/prompts.py:1-125` | `backend/src/rt/prompts/generation.py` | verbatim |
| `backend/app/prompts.py:127-190` | `backend/src/rt/prompts/critique.py` | verbatim |
| `backend/app/prompts.py:193-203` (`rules_block`) | `backend/src/rt/prompts/rules.py` | validate/whitelist rule keys and values before interpolation — closes the `PUT /api/rules` prompt-injection path (§3) |
| `backend/app/routes/master_resume.py:20-77` (`_IMPORT_SYSTEM_PROMPT`) | `backend/src/rt/prompts/importing.py` | verbatim |
| `backend/app/routes/evaluate.py:16-20` (`_EVALUATE_SYSTEM_PROMPT`) | `backend/src/rt/prompts/evaluation.py` | verbatim |
| `backend/app/database.py:22-27` (`DEFAULT_SYSTEM_PROMPT`) + `backend/app/routes/chat.py:49` (divergent copy) | `backend/src/rt/prompts/chat.py` | one constant, seeded from there (P2-17) |
| `backend/app/routes/resumes.py:80-92`, `backend/app/routes/master_resume.py:136-148`, `backend/app/routes/evaluate.py:22-39` (3 hand-written `json_schema` blobs) | `backend/src/rt/schemas/*` | generated from the Pydantic response models, not hand-maintained |

#### Services (new — this is where the handler bodies go)

| Source | Destination | Change |
|---|---|---|
| `backend/app/routes/resumes.py:58-133` | `backend/src/rt/services/generation.py::GenerationService.generate()` | returns an async iterator of typed domain progress events; the route becomes ~8 lines mapping events through `rt/api/sse.py`. Normalise before render (fixes P2-1 by construction). Make create/write/update transactional: write the PDF to a temp path, commit the row, `os.replace` into place (P2-12) |
| `backend/app/routes/master_resume.py:127-158` | `backend/src/rt/services/importing.py::ImportService.import_pdf()` | add the missing try/except around `json.loads` (P2-8); size check before read (P1-4) |
| `backend/app/routes/evaluate.py:53-70` | `backend/src/rt/services/evaluation.py::EvaluationService.evaluate()` | — |
| `backend/app/routes/chat.py:41-71` | `backend/src/rt/services/chat.py::ChatService.stream_turn()` | history windowing pushed into the repo (`LIMIT 30` in SQL, not the Python slice at `chat.py:53`); user turn written in the same transaction as the assistant turn (P2-18) |
| `backend/app/routes/resumes.py:125-127,173,186-188,202-203` (all PDF path arithmetic) | `backend/src/rt/services/artifacts.py` | single `_safe_path()` that resolves and asserts containment (P2-14); tenant-scoped subdirectories (`{user_id}/{resume_id}.pdf`); `to_thread`-wrapped writes (P1-6) |

#### Persistence

| Source | Destination | Change |
|---|---|---|
| `backend/app/database.py:30-52` (`init_db`) + `backend/db/schema.sql` | `backend/src/rt/infra/db/migrations/0001_init.sql` + a versioned runner in `backend/src/rt/infra/db/engine.py` | P2-26; the rule/prompt seeding at `database.py:37-51` becomes a separate idempotent `seed()` step |
| `backend/app/database.py:57-110` (`get_master_resume`, `upsert_master_resume`, `delete_master_resume`) | `backend/src/rt/infra/db/repositories/master_resume.py` | + a `history()` read method so `master_resume_history` (`db/schema.sql:8-13`) stops being write-only |
| `backend/app/database.py:115-216` (`list_resumes`, `create_resume`, `get_resume`, `update_resume`, `delete_resume`) | `backend/src/rt/infra/db/repositories/resumes.py` | replace `SELECT *` at `:157,167,201` with explicit columns (P2-4); `page`/`limit` bounds enforced at the schema layer (P2-6) |
| `backend/app/database.py:221-250` (`get_chat_messages`, `add_chat_message`, `clear_chat`) | `backend/src/rt/infra/db/repositories/chat.py` | `get_chat_messages` gains `limit`/`before_id` (§4, unbounded history); `SELECT *` at `:243` replaced |
| `backend/app/database.py:255-288` (`get_rules`, `upsert_rules`, `reset_rules`) | `backend/src/rt/infra/db/repositories/rules.py` | verbatim + `user_id` required |
| `backend/app/database.py:293-327` (`get_system_prompt`, `upsert_system_prompt`, `reset_system_prompt`) | `backend/src/rt/infra/db/repositories/system_prompt.py` | `SELECT *` at `:322` replaced |
| `backend/app/database.py:4` (`DEFAULT_USER_ID`) | **deleted** | every repository method takes `user_id` as a required first argument, supplied by the auth dependency (P0-2) |
| `backend/app/database.py:7-20` (`DEFAULT_RULES`) | `backend/src/rt/infra/db/repositories/rules.py` or a seed module | verbatim |
| — (new) | `backend/src/rt/infra/db/engine.py` | `contextlib.closing(sqlite3.connect(...))`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA foreign_keys=ON`, one connection per request via `Depends` (P0-3, P0-4) |

#### Cross-cutting (new modules)

| Source | Destination | Change |
|---|---|---|
| `backend/app/config.py:7-23` | `backend/src/rt/infra/settings.py` | `OPENAI_API_KEY: SecretStr` with **no default** (P2-15); add `ENV`, `LOG_LEVEL`, `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`, `LLM_MAX_TOKENS`, `RENDER_TIMEOUT_S`, `MAX_UPLOAD_BYTES`, `MAX_PROMPT_CHARS`, `RATE_LIMIT_*`, `CORS_ORIGINS`; `DB_PATH`/`PDFS_DIR` default repo-relative, container paths set in `docker-compose.yml` instead of `config.py:11-12` |
| — (new) | `backend/src/rt/infra/logging.py` | JSON logging config, a `request_id` contextvar, and `logging.basicConfig` actually being called so `yaml_utils`' warnings (`app/yaml_utils.py:101,162,290,294,399,483`) stop vanishing (P1-9) |
| — (new) | `backend/src/rt/api/middleware.py` | request-ID generation + `X-Request-ID` echo, access logging with duration and status, `Content-Length`-based body cap (P1-3, P1-4), server-side request timeout |
| `backend/app/main.py:35-52` | `backend/src/rt/api/errors.py` | + logging catch-all; one RFC 7807-ish `{type, title, status, detail, request_id}` body replacing today's ad-hoc `{"error", "code"}` |
| `backend/app/routes/chat.py:26-27`, `evaluate.py:47-48`, `resumes.py:33-34` (3 copies of `_sse`) | `backend/src/rt/api/sse.py` | one implementation + `X-Accel-Buffering: no`, `Connection: keep-alive`, periodic `: keepalive` comment frames (P2-19); a non-200 pre-flight path so failures before the first frame return a real status code (P2-3) |
| `backend/app/routes/chat.py:22-23`, `master_resume.py:80-81`, `resumes.py:25-26`, `rules.py:11-12`, `system_prompt.py:11-12` (5 copies of `_db_path`) + `resumes.py:29-30` (`_pdfs_dir`) | **deleted** | replaced by injected repositories and `services/artifacts.py` |
| — (new) | `backend/src/rt/security/auth.py` | API-key or session dependency yielding a `Principal(user_id)`, applied at the `rt/api/router.py` level so it cannot be forgotten on a new route (P0-1) — prerequisite for every tenancy fix above |
| — (new) | `backend/src/rt/security/limits.py` | per-principal rate limits, strictest on the four LLM endpoints (P1-8) |
| — (new) | `backend/src/rt/schemas/*` | request *and* response models for all 22 endpoints, wired as `response_model=` (P2-4), `max_length` on every free-text field (P1-3), `Field(ge=1, le=100)` on pagination (P2-6); normalise DELETE semantics — `/api/rules` and `/api/system-prompt` become `POST .../reset` returning 200, or 204 like their siblings (P2-5) |
| `backend/app/routes/health.py:7-9` | `backend/src/rt/api/v1/health.py` | split into `/api/health/live` (constant) and `/api/health/ready` (DB `SELECT 1` + PDF dir writability + settings validity); point `Dockerfile:38-39` and `docker-compose.yml:14-20` at the readiness probe (P2-10) |
| `backend/pyproject.toml:5-13` | same file | add `pyyaml` and `phonenumbers` as explicit deps (P2-13); add `[tool.ruff]` and `[tool.mypy]` (strict on `rt/domain` and `rt/services`), which would have caught P2-23 and P2-24 automatically |
| `backend/rendercv_config/settings.yaml` | **deleted** | never referenced by any code, Dockerfile, or compose file (P2-21) |

### 5.3 Suggested sequencing

1. **Unblock ops, no restructure.** All local edits to existing files, no layout change:
   - `infra/logging.py` equivalent + request-ID middleware + a logging catch-all handler (P1-9)
   - SQLite WAL / `busy_timeout` / `closing()` (P0-3, P0-4)
   - `asyncio.wait_for` on the subprocess and app-level LLM timeout + retry (P1-1, P1-2)
   - `max_length` on the five request models and an upload cap before `file.read()` (P1-3, P1-4)
   - Stop returning subprocess stderr to clients (P1-10)
2. **Auth + tenancy.** `security/auth.py`, thread `user_id` through `database.py`, delete `DEFAULT_USER_ID` (P0-1, P0-2). Do this **before** the layout move — it touches every route and every DB function, and doing it twice is wasteful.
3. **Extract services.** Pull the four handler bodies into `rt/services/*`, which forces the repository Protocols into existence and makes the DI story uniform. This is the change that removes the `get_settings.cache_clear()` dance from the test suite.
4. **Move files to `src/rt/`**, split the facade into per-port dependencies, add `response_model` everywhere, add schemas, add migrations, delete dead code (P2-21, P2-23, P2-16).

---

## 6. Verification note

`.env` could not be read — the sandbox blocked it as credential materialization. What *is* verified: `.gitignore:35` excludes `.env`, and `git ls-files` shows only `.env.example` is tracked, so **no key is committed to the repo**. Whether the untracked local `.env` holds a real key, and whether `docker-compose.yml:11-12` therefore mounts a live secret into the container (where P1-7 re-exports it to the `rendercv` child process), is unverified. A redacted read would settle it if you want that confirmed.
