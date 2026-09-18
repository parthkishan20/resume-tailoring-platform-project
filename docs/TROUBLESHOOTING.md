# Troubleshooting

Failure modes that actually happen in this codebase, with the symptom you will see, the reason,
and what to do. Every entry links to the defect it comes from in [`PLAN.md`](../PLAN.md) §2.1 so
you can tell "known and scheduled" from "new and worth reporting".

Two general notes before the list:

- **Logs exist, but the streaming routes are still dark.** Task 1.1 added structured JSON
  logging and an `X-Request-ID` on every response, so most failures are now attributable. The
  exception is the three SSE routes: each ends in a bare `except Exception` that turns the
  failure into an error frame **without logging it**. For those, diagnosis still leans on
  symptoms. See [`DEPLOYMENT.md`](./DEPLOYMENT.md) §8.
- **Streaming failures are HTTP 200.** Chat, generation and evaluation all return 200 and then
  send `event: error`. Do not look at the status code; look at the event name and the `code`
  field. See [`API.md`](./API.md) §3.

---

## 1. `database is locked` during generation

**Symptom.** Two generations running at once. One of them ends with an SSE error frame whose
`code` is `GENERATION_FAILED` and whose `error` text contains
`sqlite3.OperationalError: database is locked`. Sometimes the generic message arrives with no
detail at all. The HTTP status is 200.

**Cause.** SQLite runs with **no WAL journal mode and no `busy_timeout` tuning**, in an
application that performs long writes. Readers block writers. The default 5 second busy timeout
expires and the exception escapes into the route's catch-all, which flattens every unrecognised
failure to `GENERATION_FAILED` (D-56).

Two things make it more likely than it sounds. Connections are opened with
`with sqlite3.connect(...)`, which is a *transaction* context manager and **never closes the
connection**, so WAL and shm handles accumulate until the garbage collector runs (D-13). And
generation holds its transaction across a PDF write.

**Fix now.** Serialize your generations: wait for one to finish before starting the next. If you
see it repeatedly with only one generation running, restart the container to drop the leaked
connections.

**Fix properly.** Task 1.2 enables WAL, sets `busy_timeout`, turns on the `foreign_keys` pragma,
and closes connections through a real context manager.

---

## 2. A render hangs forever

**Symptom.** Generation reaches `event: progress {"message": "Rendering PDF..."}` and stops. No
`done`, no `error`, no timeout. The browser tab sits there. Worse, **the whole app stops
responding**, including `/api/health`.

**Cause.** Two compounding defects.

First, the `rendercv` subprocess has **no timeout**. `await proc.communicate()` is not wrapped in
`asyncio.wait_for`, there is no kill path, and the `TemporaryDirectory` context never exits. A
Typst compile that does not terminate pins the process indefinitely (D-07).

Second, there is no concurrency cap. N concurrent generations spawn N Typst processes, each
holding a temporary directory.

With `--workers 1` (which is itself forced by the SQLite situation in §1), one hung render takes
the whole service down rather than one worker.

**Fix now.** Restart the container. If it recurs on the same input, the YAML is the trigger:
fetch it with `GET /api/resumes/{id}` and try rendering it locally with
`rendercv render <file>.yaml --design backend/rendercv_config/design.yaml` to see the real CLI
output, which the server swallows into an error string.

**Fix properly.** Task 1.3 adds `asyncio.wait_for` with `proc.kill()` on timeout and an
`asyncio.Semaphore` bounding concurrent renders.

---

## 3. `no such column` after a schema change

**Symptom.** You edited `backend/db/schema.sql`, rebuilt, restarted, and now every request that
touches the changed table returns a 500 containing `sqlite3.OperationalError: no such column`.
Startup gave no warning. A **fresh** database works fine, which makes it look like your change
was correct.

**Cause.** There is no migration mechanism. `init_db` runs the whole schema file through
`executescript` on every boot, and every statement in it is `CREATE TABLE IF NOT EXISTS`. Against
an existing volume the entire script is a **silent no-op**. Your column was never added. The next
query looks for it and fails (D-02).

This is the most dangerous latent operational issue in the project, precisely because the
deploy appears to succeed.

**Fix now, on a development database.** Back up (see [`DEPLOYMENT.md`](./DEPLOYMENT.md) §5), then
recreate:

```bash
docker compose down
docker volume rm <project>_resumedb-data
docker compose up
```

That destroys all data. On anything you care about, apply the `ALTER TABLE` by hand against the
live file instead, after taking a backup.

**Fix properly.** Task 1.2 introduces numbered SQL migrations with a `schema_version` table,
applied in order at startup, plus a CI gate that replays the chain against a populated database
and asserts the data survives. The mechanism choice is
[ADR 0002](./adr/0002-numbered-sql-migrations.md).

---

## 4. The first render after boot freezes the app for about five seconds

**Symptom.** The first generation or preview after a container start takes several seconds
longer than it should, and during that window **nothing else responds**: other requests queue,
and the Docker healthcheck can time out and mark the container unhealthy.

**Cause.** `normalize_to_rendercv` runs the RenderCV validation backstop, which imports RenderCV
and builds a full pydantic model, up to five times over deep copies of the document. It is
CPU-bound, synchronous, and called **directly on the event loop** from four places. It is not
wrapped in `asyncio.to_thread`, unlike every database call.

Measured on a real master resume: **4.94s cold, 0.13s warm**. The cold cost is the RenderCV
import itself, paid once per process (D-05, `reports/audit-data-pipeline.md` P1 #4).

**Fix now.** Nothing to do. It happens once per container start. If a healthcheck flap is
causing restarts, raise the healthcheck `start_period`.

**Fix properly.** Task 1.3 wraps all four call sites in `asyncio.to_thread` and warms the
RenderCV import during lifespan startup so the cold cost is paid before the app accepts traffic.

---

## 5. The PDF comes out blank, or missing data you know you entered

There are two different blank-PDF problems. Check which one you have.

### 5a. Fields are silently missing from an otherwise correct PDF

**Symptom.** The resume renders, looks right, and your email address is simply not there. Or
your phone number. Or a social link. No error, no warning, nothing in the UI.

**Cause.** The validation backstop **deletes** whatever RenderCV rejects rather than reporting
it. An invalid email is pruned and you get a PDF with no email address and are never told. The
same applies to phone numbers that `phonenumbers` cannot parse into E.164, to social networks
that are not in RenderCV's accepted list, and to any `cv:` key outside the allowlist.

`normalize_to_rendercv` returns a bare `str`, so there is no channel through which a diagnostic
could reach the **UI** even in principle (D-08). It does log each prune, so since task 1.1 wired
up logging you can see what was dropped in `docker compose logs app`. Grep for `dropping` and
`prune`.

**Fix now.** Open the master resume in the editor and check the field against what RenderCV
accepts: email must be a real address, phone must be parseable to E.164 (include the country
code), `social_networks` entries must use a `network` value RenderCV knows (`LinkedIn`,
`GitHub`, `GitLab`, `ORCID`, `StackOverflow`, `X` and so on) with a bare handle as `username`,
not a URL. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §6 for the full chain.

**Fix properly.** Task 1.3 changes the return type to a `NormalizeResult` carrying the list of
dropped fields so the UI can say what it removed.

### 5b. The render fails outright

**Symptom.** `code: RENDER_FAILED` at 500, or a 422 from `GET /api/master-resume/preview`, with
a long error body full of absolute paths, box-drawing characters and a Python traceback.

**Cause.** The `rendercv` CLI exited non-zero and its entire stdout plus stderr was passed
through verbatim to the client (D-53). The text is ugly but it is the real diagnostic: read it.

Note the asymmetry that will confuse you: **the same YAML can fail one path and succeed
another.** `GET /api/master-resume/preview` normalizes before rendering;
`POST /api/resumes/{id}/render` does not. And `PATCH /api/resumes/{id}` stores YAML with no
validation at all, so a bad edit is only discovered at render time (D-57).

**Fix now.** If the failure is on a generated resume you edited, run the YAML through the
preview path instead, or fix the YAML against the RenderCV schema. If the render succeeded
before your edit, the edit is the cause.

### 5c. The preview is blank in the browser but the file is fine

If a downloaded PDF opens correctly but the in-app preview is blank, that is a viewer problem,
not a render problem. Generated PDFs are served with `Content-Disposition: inline` from the
app's own origin and rendered by the browser's built-in viewer.

---

## 6. Invalid or missing API key

**Symptom.** Every LLM-backed action fails. On the three streaming routes you get **HTTP 200**
with `event: error` and `"code": "LLM_AUTH_ERROR"`, and the message
`Invalid LLM API key (check OPENAI_API_KEY)`. On `POST /api/master-resume/import` you get a
genuine **HTTP 500** with the same code, because that route is not a stream.

Note that `LLMAuthError` maps to **500**, not 401 or 502. A server misconfiguration is presented
as an internal error.

**Cause.** The key is wrong, expired, or scoped away from the model in `LLM_MODEL`.

A **missing** key no longer produces this symptom. Since task 1.1, `validate_startup_settings`
fails the boot with a `ConfigurationError` naming `OPENAI_API_KEY` whenever `LLM_MOCK` is false
and the key is empty. A container with no key at all now refuses to start rather than reporting
itself healthy and failing at the first provider call. If you want to run with no key, set
`LLM_MOCK=true`.

**Fix.**

1. Confirm `.env` exists at the repo root and contains a real `OPENAI_API_KEY`.
   `docker-compose.yml` loads it via `env_file:` and **hard-fails if the file is absent**, so a
   missing `.env` shows up as a compose error rather than this symptom.
2. Confirm the key reached the container: `docker compose exec app printenv | grep -c OPENAI` (do
   not print the value).
3. Settings are cached with `lru_cache` at process level. **Changing `.env` requires a container
   restart**, not just a page reload.
4. Check `LLM_MODEL`. Only OpenAI-shaped auth is wired: the adapter unconditionally sets
   `OPENAI_API_KEY` regardless of what `LLM_MODEL` names, so pointing it at an Anthropic or
   Gemini model routes correctly in litellm and then fails auth.

**Related symptom, different cause.** `"code": "LLM_UNAVAILABLE"` at HTTP 503 is a rate limit, a
provider outage or a network failure. There is **no retry and no backoff**, so a single rate-limit
response becomes an immediate user-visible failure. Wait and retry by hand (D-46).

---

## 7. Port 8000 is already in use

**Symptom.** `docker compose up` fails to bind, or the app starts but shows someone else's data.

**Cause.** Historically three things bound host port 8000: `docker-compose.yml`, the old
`docker-compose.test.yml`, and the start scripts. Task 0.4 moved the e2e stack to
`${E2E_HOST_PORT:-18173}` under its own compose project name, so the remaining collision is
between the compose stack and the start scripts, which are two ways of running the same thing.

**Fix.** Stop whichever one is already running (`docker compose down`, or
`./scripts/stop_mac.sh`). To move the dev stack, the start scripts honour `PORT`:
`PORT=8080 ./scripts/start_mac.sh`.

**Never point the e2e suite at port 8000.** `test/playwright.config.ts` refuses a loopback
`BASE_URL` on 8000 outright, because every spec's `beforeEach` issues destructive calls and the
dev stack holds real data and a live key (D-29). Run `./scripts/run_e2e.sh`.

---

## 8. A delete appears to fail but actually succeeded

**Symptom.** You delete the master resume, a generated resume, or the chat history. A red error
bar appears saying `Unexpected end of JSON input`. The item is still on screen. Reload and it is
gone.

**Cause.** Three endpoints return `204 No Content`, and the API client used to call `res.json()`
unconditionally, which rejects on an empty body (D-31).

**Status: fixed** in task 0.1. The client now returns early on 204 and on any empty body. If you
still see this, you are running a stale build of the frontend. Rebuild the image; the static
export is baked in at build time and `./scripts/start_mac.sh` without `--build` will not pick it
up.

---

## 9. Unsaved editor work disappeared

**Symptom.** You edit the master resume YAML, the header shows "edited", you click Generate or
Resumes in the sidebar, come back, and your changes are gone. No warning, no undo.

**Cause.** The YAML buffer lives in `MasterResumePanel`'s local state and the panel is
conditionally rendered by `WorkstationShell`. Navigating unmounts it and discards the buffer.
There is no dirty guard, no `beforeunload` handler, and no draft persistence (D-30).

**Fix now.** Save before navigating. There is no recovery path: `master_resume_history` only
stores bodies that were actually saved.

**Related.** Generate and Evaluate operate on the last **saved** resume, not what is on screen,
so unsaved edits are ignored even before they are destroyed (D-41).

**Fix properly.** Task 0.3 adds the dirty-state guard and a `beforeunload` handler; task 3.1
moves both features onto the editor buffer.

---

## 10. The chat says it changed something and nothing changed

**Symptom.** The assistant replies as though it edited your master resume, generated a resume or
updated your rules. Nothing in the workstation changes.

**Cause.** The chat route is a plain streaming completion. There is no tool calling, no action
parsing and no database write beyond the two chat rows. The `done` event hardcodes
`"action": null`. The in-app copy saying "changes apply directly" describes a capability that
was specified and never built (D-33).

**Fix now.** Treat the assistant as advisory. Make the change yourself in the editor.

**Fix properly.** Task 3.3 implements tool calling, scoped to four actions, per
[ADR 0005](./adr/0005-assistant-fixed-tool-set.md).

---

## 11. `make check` fails on something you did not touch

**Symptom.** A gate fails in a file outside your task's ownership.

**Cause, most likely.** The ruff, mypy and coverage configuration in `backend/pyproject.toml`
carries an explicit, itemised list of **legacy exemptions**, scoped to the modules that predate
the restructure: the top-level modules under `src/resumetailor/`,
`src/resumetailor/api/routers/*.py`, and `tests/**`. If you added a file, it is **not** exempt:
everything new is held to the full rule set. Tasks 0.13 and 0.14 clear the legacy half.

**Fix.** Run the specific gate to see the real output:

```bash
make lint-backend      # ruff check
make typecheck-backend # mypy
make test-backend      # pytest, with the coverage floor
make lint-frontend     # eslint
make typecheck-frontend
make test-frontend     # jest
```

If a gate genuinely fails on a file you do not own, that is a blocker: say so and name the file,
per [`../AGENTS.md`](../AGENTS.md) rule 3. Do not edit it.

**Coverage.** The floor in `pyproject.toml` is the **measured** level, not the target. It fails
on a regression, not on rounding. If coverage drops because you added uncovered code, add tests
rather than lowering the floor.

---

## 12. The test suite passes together and fails alone (or vice versa)

**Symptom.** A test passes in a full run and fails under `-k`, in an IDE single-test run, or in a
different order.

**Cause, historically.** `get_settings` is `lru_cache`d, and 21 tests called `cache_clear()` on
entry and none on exit, leaking a stale `Settings` pointing at a deleted `tmp_path` into whatever
ran next (D-37).

**Status: fixed** in task 0.10. A single autouse `isolated_settings` fixture in
`backend/tests/conftest.py` gives every test its own temporary `DB_PATH` and `PDFS_DIR` and
clears both `get_settings` and `deps._backend` on entry **and** on exit. `pytest-randomly` is now
a declared dev dependency, so test order is shuffled on every run and a new order-dependence
cannot hide.

**If you see it again**, you have introduced module-level or cached state. Find it, do not work
around it by pinning the order.

---

## 13. Things that look wrong but are not

| Observation | Explanation |
|---|---|
| `DELETE /api/rules` returns 200 with a body, not 204 | Deliberate. It is a reset, not a delete. Same for `DELETE /api/system-prompt`. See [`API.md`](./API.md) §0 |
| An SSE failure returns HTTP 200 | Known defect, not a proxy problem. The status is committed before the generator can fail (D-55) |
| `/docs` and `/openapi.json` are reachable with no auth | True in every environment, and every response body in that spec shows as `{}` because no route declares a `response_model` (D-54, D-58) |
| Timestamps display a few hours off | Stored UTC-naive and space-separated; the browser parses them as local time (D-09) |
| The UI is dark and has no theme toggle | Hardcoded; `next-themes` is installed and unused (D-11). The Letterpress redesign in task 1.4 is light-first with a toggle |
| The layout breaks below about 900px | Zero responsive handling: not one Tailwind breakpoint prefix exists in any component (D-43) |
| The screenshots in the README do not match the app | They predate the redesign. Retaking them is task 4.5 (D-61) |
| `backend/rendercv_config/settings.yaml` seems to do nothing | It does nothing. Dead configuration, never read by any code (D-15) |
