# Deployment and operations

How to build, configure, run and operate ResumeTailor as it exists today, including the things
that are missing. Where something does not exist, this document says so rather than describing
the plan for it.

> **Read §6 before you publish the port anywhere.** This application has no authentication.

Companion documents: [`ARCHITECTURE.md`](./ARCHITECTURE.md) (how it works),
[`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md) (what breaks and what to do),
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) (local development).

---

## 1. Quick start

```bash
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
docker compose up --build
```

The app is then at `http://localhost:8000`. First boot creates the SQLite file, seeds the
default generation rules and the default system prompt, and serves the pre-built frontend.

There are also wrapper scripts that do the same thing with `docker run` instead of compose:

| Script | What it does |
|---|---|
| `scripts/start_mac.sh` | Stops and removes any container named `resumetailor`, builds if needed, runs it with both named volumes and `--env-file .env`, waits up to 90s for health, opens a browser |
| `scripts/stop_mac.sh` | Stops the container |
| `scripts/start_windows.ps1`, `scripts/stop_windows.ps1` | PowerShell equivalents |

**The start scripts rebuild only if you pass `--build` or the image is absent.** Running
`./scripts/start_mac.sh` after a `git pull` silently starts the **old** image with none of the
new code. Always use `./scripts/start_mac.sh --build` after pulling.

`PORT` can be overridden for the scripts (`PORT=8080 ./scripts/start_mac.sh`). The e2e stack
uses a separate port and never 8000 (§7).

---

## 2. Environment variables

The complete set. `backend/src/resumetailor/core/config.py` defines all of them; `.env.example` documents the
three the user is expected to set.

| Variable | Default | What it does |
|---|---|---|
| `OPENROUTER_API_KEY` | empty `SecretStr` | The provider credential read when `LLM_MODEL` starts with `openrouter/` (the default). **Required** in that case unless `LLM_MOCK=true`: an empty value fails the boot with a `ConfigurationError` rather than failing the user's first generation. Passed explicitly on each provider call, never written to `os.environ` (D-49), so the `rendercv` child process never inherits it |
| `OPENAI_API_KEY` | empty `SecretStr` | The provider credential read instead, only when `LLM_MODEL` does **not** start with `openrouter/` (e.g. a bare `gpt-4o-mini`). Same required-unless-mocked rule and the same D-49 handling |
| `LLM_MODEL` | `openrouter/free` | The one model used for all four workloads: chat, both generation passes, evaluation and PDF import. There is no per-task override. Its provider prefix selects which key above is read (`core/config.py`'s `llm_api_key`) |
| `LLM_MOCK` | `false` | When true, the whole backend object is swapped for the deterministic simulator. No network, no API key needed. Used by the test stack and CI |
| `DB_PATH` | `/app/db/resumedb.db` | Absolute path to the SQLite file. The default is container-absolute and wrong for every host-local run |
| `PDFS_DIR` | `/app/pdfs` | Directory for generated PDFs. Same caveat |
| `LOG_LEVEL` | `INFO` | Root log level |
| `LOG_FORMAT` | `json` | One JSON object per line on stdout. Set `text` when a human is reading the terminal |

Notes that will bite otherwise:

- **`DB_PATH` and `PDFS_DIR` are not set by either compose file.** Both rely on the container
  defaults happening to match the volume mount points. That coupling is real and undocumented in
  the compose files themselves: move either side and persistence silently breaks.
- **Startup validation covers the key only.** Nothing yet checks that `DB_PATH`'s directory and
  `PDFS_DIR` are writable before the app reports itself healthy.
- Settings are read once and cached with `lru_cache`. Changing an environment variable requires
  a process restart.
- `.env.example` documents the required key plus `LLM_MODEL` and `LLM_MOCK`; the table above is
  the authoritative list for everything else, including `LOG_LEVEL` and `LOG_FORMAT`.

`docker-compose.yml` loads `.env` wholesale with `env_file:`. `docker-compose.test.yml`
deliberately uses inline `environment:` with **no `env_file`**, so a real key cannot leak into a
test run.

> **Target, not built yet.** Repo-relative path defaults with the container paths set in compose,
> and settings for LLM timeouts, retries, token caps, upload caps and rate limits. Task 2.4.
> (`SecretStr` with no default and startup validation were the task 1.1 half of this and have
> landed.)

---

## 3. The image

Two stages, in `Dockerfile` at the repo root.

**Stage 1, `node:20-slim`.** Copies `frontend/package.json` and `frontend/package-lock.json`,
runs `npm ci`, then copies the named build inputs individually (`next.config.js`,
`tsconfig.json`, `postcss.config.js`, `tailwind.config.ts`, `src/`) and runs `npm run build`.
Output is the static export at `/build/frontend/out`.

**Stage 2, `python:3.12-slim`.** Copies the pinned `uv` binary by digest, then
`backend/pyproject.toml` and `backend/uv.lock` **only**, runs `uv sync --frozen --no-dev`, and
only then copies `backend/src`, `backend/db` and `backend/rendercv_config`. The frontend export
lands at `/app/backend/static/`, which is where the static mount resolves `STATIC_DIR` to.

It sets `PYTHONPATH=/app/backend/src`. That is load-bearing: `resumetailor-backend` is a
*virtual* project in `uv.lock`, so `uv sync` installs the dependency tree but not this package,
and `src/` has to be on the path for `resumetailor.main` to import. The entrypoint is
`uvicorn resumetailor.main:app`.

Both stages name their source paths individually rather than copying `frontend/` or `backend/`
wholesale. That is deliberate and load-bearing: copying the directories dropped the host's
darwin `node_modules` on top of the freshly installed linux tree, and baked a 345 MB
conda/darwin Python 3.13 virtualenv into a Python 3.12 linux image (D-35, D-36, fixed in task
0.5). **If you add a new top-level build input, add it to the `COPY` list**; it will not arrive
by itself.

`.dockerignore` exists and cuts the build context from roughly 868 MB to under 1 MB. It also
excludes `.env`, so the key no longer reaches the daemon on every build (D-34).

**There is no `apt-get` layer and no TeX Live.** RenderCV 2.x compiles with Typst, which
`rendercv[full]` ships as a pip wheel. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §7.

Expected size: roughly 430 MB. It was previously 1.1 to 1.3 GB. The remaining ~30 MB above the
theoretical floor is the `uv` binary, which stays in the runtime image while `CMD` is still
`uv run`.

**Known, not yet fixed:**

- **The container runs as root.** No `USER` directive. Volume contents become root-owned on the
  host, and the LLM-authored-YAML to Typst chain runs with full container privileges. This is
  the highest-value exploit chain in the application (D-50).
- **`uv` is PID 1** and does not reliably forward `SIGTERM`. `docker stop` waits out the grace
  period then `SIGKILL`s, aborting in-flight SSE streams and mid-write renders. No `tini`, no
  `--init`, no `stop_grace_period` (D-51).
- **`--workers 1`.** This is not arbitrary: SQLite has no WAL and no `busy_timeout` tuning, so
  more than one worker means immediate lock contention. Every blocking-on-the-event-loop defect
  (D-05 in particular) is therefore a whole-service stall rather than a per-worker one.

> **Target, not built yet.** Multi-stage build with a non-root `USER`, `tini` as PID 1, a
> `tmpfs` render scratch directory, a read-only rootfs, resource limits, compose profiles and a
> release workflow. Tasks 2.4 and 3.4.

---

## 4. The two compose stacks

They are deliberately isolated from each other on every axis.

| | `docker-compose.yml` (dev and production) | `docker-compose.test.yml` (e2e) |
|---|---|---|
| Project name | none, so it inherits the directory name | `resumetailor-e2e` |
| Image tag | `resumetailor` | `resumetailor-e2e` |
| Host port | `8000:8000` | `${E2E_HOST_PORT:-18173}:8000` |
| Storage | named volumes `resumedb-data`, `resumepdf-data` | `tmpfs` at `/app/db` and `/app/pdfs`, discarded on stop |
| Config | `env_file: .env` | inline `environment:` with `LLM_MOCK=true` and a dummy key |
| Services | `app` | `app` plus `playwright` |
| Healthcheck | 30s interval, 60s start period, 3 retries | 10s interval, 30s start period, 5 retries |

That isolation is not cosmetic. Both files previously declared a service named `app` with no
project name, so running the test compose from the same directory **recreated the dev container
in place**, swapping its volumes and environment, while every e2e spec's `beforeEach` issued
`DELETE /api/master-resume` and friends against real data with a live API key (D-29). Task 0.4
closed that. Do not reintroduce a shared project name or a shared host port.

**The in-container bind stays `0.0.0.0`.** Uvicorn must keep binding all interfaces inside the
container or the Docker bridge cannot reach it. What controls exposure is the **host-side
publish**, the left half of the `ports:` mapping. See §6.

**Not present in either stack, and needed for a real deployment:** a reverse proxy, TLS,
`deploy.resources.limits`, `logging:` driver options (the default `json-file` driver is
unbounded and will eventually fill the disk), `stop_grace_period`, `read_only: true` with
`tmpfs`, `security_opt: [no-new-privileges:true]`, and `user:`.

---

## 5. Volumes, state, and what the healthcheck does not check

### What is stateful

| Volume | Mount | Contents |
|---|---|---|
| `resumedb-data` | `/app/db` | `resumedb.db`. The master resume, its 10-entry history, every generated resume's YAML, all chat messages, all generation rules, the system prompt |
| `resumepdf-data` | `/app/pdfs` | Generated PDFs, flat, named `{resume_id}.pdf` |

That is the entire state of the application. Both survive `docker compose down`. **Neither
survives `docker compose down -v`**, a volume prune, or a Docker Desktop factory reset.

There is also a `db/.gitkeep` directory at the repo root that nothing uses. Ignore it.

### Backup and restore

`scripts/backup.sh` and `scripts/restore.sh`. Both work against a running compose stack or
against local files, and both auto-detect which: if the `app` service is up they use it,
otherwise they use `DB_PATH` and `PDFS_DIR`. Pass `--docker` or `--local` to decide explicitly.

```bash
./scripts/backup.sh                       # one backup into ./backups/<UTC timestamp>/
./scripts/backup.sh --out /mnt/backups    # somewhere durable, which is the point
BACKUP_KEEP=14 ./scripts/backup.sh        # keep 14 instead of the default 7

./scripts/restore.sh backups/20260918T074103Z
```

Each backup is one self-contained directory:

| File | Contents |
|---|---|
| `resumedb.db` | the database, snapshotted with SQLite's online backup API |
| `pdfs/` | every generated PDF |
| `MANIFEST` | schema version, per-table row counts, size, and the database's sha256 |

Three things about this are deliberate.

**The database is never copied with `cp`.** `cp` on a live database can capture a torn file, and
with WAL enabled it also misses whatever is still in the `-wal` sidecar. `backup.sh` uses
SQLite's online backup API, which takes a consistent snapshot while the application is writing,
so a backup does not require downtime.

**Every backup is verified before it counts.** `PRAGMA integrity_check` runs on the snapshot, and
retention only prunes after that passes. An unverified backup is a guess.

**Restoring is defended.** `restore.sh` verifies the backup opens, takes a safety backup of the
current state into `backups/pre-restore/` (skip with `--no-safety-backup`), prints the manifest,
and then asks for confirmation (skip with `--force`). It removes the `-wal` and `-shm` sidecars
before writing the restored file, because dropping a database next to a stale write-ahead log is
how a restore silently ends up as a mixture of the two.

A restored database does not need to match the current schema. The application migrates on start,
so a backup taken at an older schema version is brought forward on the next boot.

`./backups/` writes a `.gitignore` containing `*` into itself the first time it is created. A
backup holds the owner's real name, email, phone and address, and that is a class of accident
worth making structurally impossible rather than remembering not to have (D-01).

> **Still target, not built.** Scheduling. Nothing runs these automatically: they are a command
> you or a cron job invokes. Weekly-tier retention (7 daily plus 4 weekly), an automatic backup
> before the first migration of a run, a `make backup` / `make restore` entry point, and the move
> to `deploy/scripts/` belong to task 3.4.

### Migrations

`backend/migrations/NNNN_name.sql`, applied in numeric order at startup by
`resumetailor.db.migrate`, with a `schema_version` table recording what has been applied. A
migration and the row recording it commit in one transaction, so a migration either applies and
is recorded or does neither, and running the same migration twice is impossible.

```bash
# what version is a database at?
sqlite3 backend/db/resumedb.db "SELECT MAX(version) FROM schema_version"
```

Migrations run in the lifespan, before the application serves anything. A failure there fails the
boot rather than degrading into runtime errors, which is the point: the previous mechanism ran
`CREATE TABLE IF NOT EXISTS` on every boot, so against an existing volume a schema change applied
nothing at all and surfaced later as `no such column` (D-02).

To change the schema, add the next numbered file. Do not edit an applied migration and do not
edit `backend/db/schema.sql`, which is no longer read by anything.

The choice of numbered SQL over Alembic is recorded in
[ADR 0002](./adr/0002-numbered-sql-migrations.md).

### The healthcheck

Both the Dockerfile `HEALTHCHECK` and both compose healthchecks hit `GET /api/health`, which
returns a hardcoded `{"status": "ok"}`.

It does **not** check:

- that SQLite is reachable, or that the database is not corrupt
- that `PDFS_DIR` exists or is writable
- that `rendercv` is on `PATH` or that Typst works
- that the API key is valid
- anything at all about the LLM provider

A container with a corrupt database reports itself healthy and keeps receiving traffic. A
rolling deploy will happily promote a container that cannot reach its own data.

The healthcheck is also duplicated verbatim between the Dockerfile and both compose files, which
guarantees drift.

---

## 6. There is no authentication. Keep the port on loopback.

**No endpoint in this application requires any credential.** No API key check, no session, no
token, no middleware of any kind. Anyone who can reach the published port can:

- read the owner's full master resume, including name, email, phone, address and employment
  history
- overwrite or delete that master resume
- read and clear the entire chat history
- **rewrite the system prompt used for every subsequent chat turn**, which is a persistent
  stored prompt-injection primitive
- inject arbitrary text into both generation system prompts through `PUT /api/rules`
- spend the owner's LLM credits without limit, with no rate limiting, no request size cap and no
  spend ceiling

There is also no CORS middleware, which is correct today because the frontend is served
same-origin, and no security headers of any kind, which matters because generated PDFs are
served with `Content-Disposition: inline` from the application's own origin.

**The operational rule that follows:**

> Publish the container port on the loopback interface only. In `docker-compose.yml` that is
> `"127.0.0.1:8000:8000"` rather than `"8000:8000"`, and the same in the start scripts.
> **Uvicorn must keep binding `0.0.0.0` inside the container** or the Docker bridge cannot reach
> it. The host-side publish is what exposes the app, not the in-container bind.

As of this writing `docker-compose.yml` still publishes `"8000:8000"`, which binds all host
interfaces. Changing it is task 2.4; it is not yet done. Until then, do not run this stack on a
shared network, a VPS, or any cloud host.

The reasoning, and why the answer is "loopback" rather than "add auth", is
[ADR 0004](./adr/0004-no-auth-loopback-only.md). The deployment target is undecided, which is
why the auth model is deferred rather than designed wrong: blocker B-03 in
[`PLAN.md`](../PLAN.md) §6.

---

## 7. Running the e2e suite safely

**Use `./scripts/run_e2e.sh`.** It exports `E2E_HOST_PORT`, brings the isolated stack up,
runs Playwright inside the container, and tears everything down with `down -v` on exit.

Every e2e spec's `beforeEach` issues destructive calls. `test/playwright.config.ts` therefore
requires `BASE_URL` to be set explicitly, refuses to guess, and **refuses outright any loopback
`BASE_URL` on port 8000**, because that is the dev stack's address.

If you want to point a host-side `npx playwright test` at an already-running test stack:

```bash
BASE_URL=http://localhost:18173 npx playwright test
```

Never at 8000.

---

## 8. Logs, metrics, and error tracking

**Logging: configured, as of task 1.1.** `configure_logging` runs first thing in `create_app`,
before anything can fail silently. Output is one JSON object per line on stdout by default;
`LOG_FORMAT=text` gives a human-readable formatter instead, and `LOG_LEVEL` sets the root level.
`PYTHONUNBUFFERED=1` is set in the Dockerfile, so `docker logs` sees it immediately.

Every response carries an `X-Request-ID` header, assigned by `RequestContextMiddleware` or reused
from an inbound header of the same name, and every log line emitted inside that request carries
the same id. The domain error handler logs with `exc_info` before it serialises the response, so
a failure the user sees is a failure the operator can find.

**What is still dark.** The three SSE routes each end in a bare `except Exception` that flattens
the failure into an error frame **without logging it**. Those are still the least attributable
failures in the system, and they are the ones users hit most. Task 2.5 moves that orchestration
into services where the catch can be narrowed.

**Metrics: none.** No visibility into LLM latency, token spend, render success rate, request
p95, or concurrency. Token spend is the one that costs real money and it is entirely unmeasured.

**Error tracking: none.** No Sentry, no equivalent. Note for whoever adds one: resume content,
job descriptions and chat bodies are all PII and must be scrubbed from event payloads.

**Request IDs: none.** A user-reported error cannot be correlated with anything server-side.

> **Target, not built yet.** Structured JSON logging with a request-ID contextvar and
> `X-Request-ID` echo, a catch-all handler that logs the traceback before returning a redacted
> body, metrics, and a health and readiness split. Tasks 1.1 and 3.5.

---

## 9. Upgrading

```bash
git pull
docker compose up --build -d
```

Or `./scripts/start_mac.sh --build`. The `--build` is not optional: see §1.

Two things to be aware of on every upgrade:

1. **Schema changes will not apply** to your existing volume (§5). If the release notes mention
   a schema change, back up first and expect to recreate the database until migrations land.
2. **In-flight work is lost on stop.** Because `uv` is PID 1 and does not forward `SIGTERM`,
   `docker stop` kills the process after the grace period rather than draining. An in-progress
   generation loses its SSE stream, and a mid-write render can leave a partial PDF on the volume
   with a database row already committed (D-20, D-51).

---

## 10. Dependency and vulnerability posture

80 locked Python packages in `backend/uv.lock`, plus the npm tree. The notable attack surface is
`pymupdf`, which parses untrusted uploads from `POST /api/master-resume/import`, and `litellm`,
which is large, fast-moving and network-facing.

**There is no dependency scanning of any kind.** No `pip-audit`, no `npm audit` in CI, no
Dependabot, no Trivy, no SBOM. This is not a claim about a specific CVE. It is a claim that
there is no mechanism by which one would ever be noticed (D-63).

What does exist: `uv.lock` and `frontend/package-lock.json` are both committed, the Dockerfile
uses `uv sync --frozen`, `uv` itself is pinned by digest, and CI runs `uv sync --locked` so a
dependency cannot be added without the lockfile in the same commit. Secrets are scanned by
gitleaks on every push and in the pre-commit hook, and the repository history has been verified
clean: no key-shaped string exists in any revision, and `.env` was never committed at any point.

> **Target, not built yet.** Dependency scanning and image scanning in a release workflow.
> Task 3.4.
