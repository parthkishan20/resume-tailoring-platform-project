# Infrastructure / Build / Security Audit — `resume-tailoring-platform`

Scope: read-only audit of infrastructure, build, deployment, and security posture.
Repo: `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform`
Remote: `https://github.com/parthkishan20/resume-tailoring-platform.git`
Branch: `main` (no tags, no other branches)
Audit date: 2026-09-18

---

## 0. Raw command results

### `git log --oneline -30`

```
e943dfb feat: add ChatDrawer and Sidebar components for improved navigation and chat functionality
a973923 Refactor code structure for improved readability and maintainability
e8f39b8 docs: add screenshots and rewrite README; fix editor scroll and certifications
3b50be8 fix: embed locale content in YAML instead of passing --locale file path
7cf9c1d fix: update yaml_utils docstring to reflect design is provided via --design flag
1261920 fix: strip design block from normalized YAML, design provided via --design flag
cca8c13 feat: pass --design and --locale flags to rendercv render
c447c41 feat: move rendercv config files into backend/rendercv_config
fd4d575 docs: add rendercv config integration implementation plan
71fb297 docs: add rendercv config integration design spec
414cf13 Fix rendercv schema validation errors from bad import format
11284b7 Fix rendercv PDF generation failure on Generate Tailored Resume
c6c20da fix: rendercv[full] to include Typst for PDF generation
ba2f918 feat: switch from OpenRouter to direct OpenAI API (gpt-4o-mini default)
4f3a68a Refactor code structure for improved readability and maintainability
cb5e29d fix: master-resume preview route, chat SSE error handling, LLM_MODEL config, scenario 4 assertion
32e642d fix(test): wire rules-toggle testid, resume-list-item assertion, name fragment content check
ee00e79 docs(test): T6 integration tester report — all 8 scenarios pass
28e37d7 feat(test): Playwright E2E infrastructure and all 8 integration test scenarios
d481e27 fix(api): spec SSE error codes, error-path tests, two-pass call count assertion
09d2d87 feat(api): route unit tests — all endpoints covered
a9e24e2 feat(api): FastAPI app, startup handler, health route, route stubs
51a95e9 feat(api): pyproject.toml, settings, BackendAPI facade, deps
ec8005e feat(devops): start/stop scripts (mac + windows) — Wave 1 DevOps complete
a389a44 feat(devops): docker-compose for production and testing
4d7904a feat(devops): multi-stage Dockerfile (Node→Python, Typst via rendercv pip)
25b8dd5 chore: gitignore, env example, db directory
5743500 fix(frontend): rules-toggle testid, distDir config, gitignore frontend artifacts
9a784ba feat(frontend): chat panel, evaluation panel, all tests pass
99c37fc feat(frontend): chat panel, evaluation panel, all tests pass
```

Observations: 30 commits, all direct to `main`. No merge commits, no PRs, no tags. Two commits share the identical message `Refactor code structure for improved readability and maintainability` (`a973923`, `4f3a68a`) — generic, non-descriptive. Commit `9a784ba`/`99c37fc` also share a message. No branch protection is implied by this history.

### `git status --porcelain`

```
 M .claude/settings.json
 M .gitignore
 M backend/app/routes/master_resume.py
 M backend/app/yaml_utils.py
 M docker-compose.yml
?? backend/tests/test_rendercv_validation.py
?? planning/master-resume.yaml
```

### `git diff --stat`

```
 .claude/settings.json               |  10 +-
 .gitignore                          |   5 +
 backend/app/routes/master_resume.py |   1 +
 backend/app/yaml_utils.py           | 219 ++++++++++++++++++++++++++++++++++--
 docker-compose.yml                  |   2 -
 5 files changed, 221 insertions(+), 16 deletions(-)
```

Uncommitted infra diffs in full:

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
@@ -1,6 +1,4 @@
 # docker-compose.yml
-version: "3.9"
-
 services:
   app:
     build: .
```

```diff
diff --git a/.gitignore b/.gitignore
@@ -72,3 +72,8 @@ backend/static/

 # Windows
 Thumbs.db
+
+# Agent skills installed via `npx skills add` (machine-local, not vendored)
+.agents/
+skills-lock.json
+.claude/skills/
```

```diff
diff --git a/.claude/settings.json b/.claude/settings.json
@@ -1,12 +1,10 @@
 {
+  "env": {
+    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
+  },
   "enabledPlugins": {
-    "context7@claude-plugins-official": true,
     "frontend-design@claude-plugins-official": true,
-    "code-simplifier@claude-plugins-official": true,
-    "playwright@claude-plugins-official": true
-  },
-   "env": {
-    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
+    "code-simplifier@claude-plugins-official": true
   },
   "teammateMode": "in-process"
 }
```

### `git ls-files | wc -l`

```
129
```

### Build-artifact probe

`git ls-files | grep -E '^(frontend/out|backend/static|frontend/\.next|test/playwright-report|test/test-results|\.playwright-mcp|\.pytest_cache|\.superpowers|\.agents)'`

```
.superpowers/sdd/t2-llm-report.md
.superpowers/sdd/t6-tester-report.md
```

Result: **no build artifacts are committed.** The only hits are two agent report markdown files under `.superpowers/`. No `frontend/out`, no `backend/static`, no `frontend/.next`, no `test/playwright-report`, no `test/test-results`, no `.playwright-mcp`, no `node_modules`, no `.venv`.

`git ls-files | grep -i 'ds_store'` → `NONE`
`git ls-files | grep -E '\.env'` → `.env.example` only.

### Tracked files by top-level directory

```
  41 backend
  33 frontend
  18 docs
  14 test
   7 planning
   4 scripts
   3 .claude
   2 .superpowers
   1 README.md
   1 Dockerfile
   1 docker-compose.yml
   1 docker-compose.test.yml
   1 db
   1 .gitignore
   1 .env.example
```

### `du -sh .git` and `git count-objects -vH`

```
4.5M	.git

count: 534
size: 4.38 MiB
in-pack: 0
packs: 0
size-pack: 0 bytes
prune-packable: 0
garbage: 0
size-garbage: 0 bytes
```

534 loose objects, **zero packs** — the repo has never been `gc`'d.

### Largest tracked blobs

```
448K	planning/example-yaml-preview.png
428K	backend/uv.lock
236K	frontend/package-lock.json
156K	docs/screenshots/05-generation-rules.png
140K	docs/screenshots/04-generate-tab.png
124K	docs/screenshots/08-chat-assistant.png
124K	docs/screenshots/07-evaluate-tab.png
124K	docs/screenshots/02-workstation-editor.png
120K	docs/screenshots/06-resumes-tab.png
100K	frontend/tsconfig.tsbuildinfo
 76K	docs/screenshots/03-master-resume-preview.png
 52K	docs/superpowers/plans/2026-07-06-wave1-frontend-engineer.md
```

All legitimate except `frontend/tsconfig.tsbuildinfo` (a TypeScript incremental build cache — should not be tracked). No history rewrite is warranted.

### Working-tree sizes

```
453M	frontend            (360M node_modules + 92M .next + 1.6M out)
348M	backend             (345M .venv)
 41M	test                (40M node_modules + 532K playwright-report + 4.0K test-results)
2.9M	.superpowers
1.1M	docs
556K	planning
324K	.agents
168K	.playwright-mcp
 20K	.pytest_cache
   0B	db
```

Total working tree ≈ **1.2 GB**, of which ~745 MB is `node_modules` + `.venv` (legitimate, gitignored).

### CI config probe

`ls -la .github` → **NO .github**
`find . -maxdepth 3 -name '*.yml' -o -name '*.yaml'` (excluding node_modules/.venv/.agents) →

```
./docker-compose.yml
./docker-compose.test.yml
./planning/example-master-resume.yaml
./planning/master-resume.yaml
./.playwright-mcp/page-2026-07-07T03-*.yml   (25 stale Playwright page dumps)
```

**No CI configuration of any kind exists.**

### `.dockerignore` probe

```
NO .dockerignore
```

### Untracked `.DS_Store` files

```
./.DS_Store
./docs/.DS_Store
```

Both untracked (correctly ignored via `.gitignore:40`), but present on disk and therefore in the Docker build context.

---

## 1. Container build — `Dockerfile` (43 lines)

The file is a two-stage build: `node:20-slim` (Next.js static export) → `python:3.12-slim` (FastAPI runtime serving the export). The *shape* is right. The COPY ordering defeats both stages.

### Full source, annotated

```dockerfile
 1  # Dockerfile
 3  # ── Stage 1: Build Next.js static export ────────────────────────────────────
 4  FROM node:20-slim AS frontend-builder
 6  WORKDIR /build/frontend
 7  COPY frontend/package*.json ./
 8  RUN npm ci --quiet
 9  COPY frontend/ ./                    ← P0: overwrites the linux node_modules
10  RUN npm run build
13  # ── Stage 2: Python runtime ──────────────────────────────────────────────────
14  FROM python:3.12-slim
17  COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv   ← P1: floating tag
19  WORKDIR /app
22  COPY backend/ ./backend/             ← P0: bakes in 345 MB darwin .venv
                                        ← P1: also busts the dep cache
25  WORKDIR /app/backend
26  RUN uv sync --frozen --no-dev
29  COPY --from=frontend-builder /build/frontend/out ./static/
32  RUN mkdir -p /app/db /app/pdfs
34  WORKDIR /app/backend                 ← P2: duplicate WORKDIR
36  EXPOSE 8000
38  HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
39      CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1
41  CMD ["uv", "run", "--project", "/app/backend", "uvicorn", "app.main:app", \
42       "--host", "0.0.0.0", "--port", "8000", \
43       "--workers", "1"]              ← P1: uv is PID 1, no SIGTERM forwarding
```

### Findings

| Sev | Finding |
|---|---|
| **P0** | **No `.dockerignore` exists.** The build context is the entire repository ≈ **850 MB** (`frontend/node_modules` 360 M + `frontend/.next` 92 M + `backend/.venv` 345 M + `test/node_modules` 40 M + `.git` 4.5 M + `.superpowers` 2.9 M + `.playwright-mcp` 168 K + `.DS_Store` files). Every single `docker build` tars and streams all of it to the daemon before the first instruction runs. It also means `.env` — containing a live 164-character `OPENAI_API_KEY` — is transmitted into the build context on every build. It is *not* baked into the image today (only `backend/` and `frontend/` are `COPY`'d), but the margin is one careless `COPY . .` wide. |
| **P0** | **`Dockerfile:9` destroys the frontend dependency install.** `COPY frontend/ ./` runs *after* `npm ci` at `:8` and copies the host's `frontend/node_modules` over the freshly-installed linux tree. Confirmed on disk: `frontend/node_modules/@next/swc-darwin-arm64` exists (the only `*darwin*` entry). `npm run build` at `:10` therefore executes against **darwin-arm64 SWC binaries inside a linux image**. The build is non-reproducible and architecturally wrong; it only appears to work via Next's WASM fallback or a stale cached layer. |
| **P0** | **`Dockerfile:22` bakes a 345 MB foreign virtualenv into the image.** `COPY backend/ ./backend/` includes `backend/.venv`. Verified `backend/.venv/pyvenv.cfg`: `home = /opt/miniconda3/bin`, `implementation = CPython`, `version_info = 3.13.5`, `uv = 0.11.11` — a macOS conda-based **Python 3.13** venv being copied into a **Python 3.12** linux image. `uv sync --frozen --no-dev` at `:26` then runs on top of it. Whatever uv does with the mismatched interpreter, the 345 MB layer is permanent image weight and permanently in the layer history. It is also a silent version skew against `backend/pyproject.toml:4` (`requires-python = ">=3.12"`) and the 3.12 base image — local development runs 3.13, production runs 3.12, and nothing tests the difference. |
| **P1** | **Dependency layer caching is fully defeated.** `:22` copies *all* backend source before `:26 uv sync`. A one-character edit to any file under `backend/app/` invalidates the copy layer and forces a complete re-resolve and re-install of the 80-package dependency tree (litellm, pymupdf, rendercv, typst, tiktoken, tokenizers, huggingface-hub…). Stage 1 has the correct pattern at `:7-8` (`COPY package*.json` then `npm ci`) but then throws it away at `:9`. |
| **P1** | **Runs as root.** There is no `USER` directive anywhere in the file. The container writes to `/app/db` and `/app/pdfs` as uid 0, so volume contents become root-owned on the host. This compounds every other issue below — notably the LLM-authored-YAML → `rendercv`/Typst → filesystem chain in §3. |
| **P1** | **PID 1 and signal handling are wrong.** `:41` makes `uv` PID 1, not uvicorn. `uv run` is not an init process and does not reliably forward `SIGTERM` to its child. `docker stop` will therefore wait out the full 10-second grace period and then `SIGKILL`, aborting in-flight SSE streams (`/api/resumes/generate`, `/api/chat`, `/api/evaluate`) and any `rendercv` subprocess mid-write to `/app/pdfs`. No `tini`, no `--init`, no `stop_grace_period` in compose. Secondary cost: `uv run` re-resolves the project environment on *every* container start — slow, and a hard failure if the network is unavailable at boot. |
| **P1** | **Nothing is pinned.** `:17` `COPY --from=ghcr.io/astral-sh/uv:latest` — a floating tag for a tool that installs your entire dependency tree. `:4 node:20-slim` and `:14 python:3.12-slim` are floating tags with no digests. `backend/pyproject.toml:5-13` uses `>=` ranges throughout. Mitigating: `backend/uv.lock` **is** committed (428 KB, 80 packages) and `--frozen` is used, so Python deps are genuinely reproducible. `frontend/package-lock.json` is committed too — but per the P0 above its `npm ci` output is discarded, so the frontend build is not reproducible. |
| **P2** | **Healthcheck is duplicated and near-useless.** The `HEALTHCHECK` at `:38-39` is repeated verbatim in `docker-compose.yml:14-20` — guaranteed drift. The probe hits `/api/health`, which is `backend/app/routes/health.py:8` returning a static `{"status": "ok"}`. It does not touch SQLite, does not verify `PDFS_DIR` is writable, and does not check that `rendercv` is on `PATH`. A container with a corrupt database or a missing Typst binary reports itself healthy and receives traffic. |
| **P2** | `WORKDIR /app/backend` is set twice (`:25`, `:34`). `:32 RUN mkdir -p /app/db /app/pdfs` is redundant with `backend/app/main.py:23-24`, which mkdirs both at lifespan startup. |
| **P2** | No `ENV PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, `UV_COMPILE_BYTECODE=1`, or `UV_LINK_MODE=copy`. Unbuffered stdout matters directly for `docker logs` usability given there is no logging framework (§6). |
| **(good)** | **The LaTeX/RenderCV toolchain footprint is correct and should be preserved.** `backend/pyproject.toml:9` declares `rendercv[full]>=2.8`, which pulls `typst` as a pip wheel (confirmed in `backend/uv.lock` alongside `rendercv-fonts`). There is **no `apt-get` layer at all** in the Dockerfile and no `texlive` anywhere. This is the single best decision in the image — a naive "just add texlive-full" would add roughly 4 GB. Commit `c6c20da` ("fix: rendercv[full] to include Typst for PDF generation") shows this was learned the hard way. Do not regress it. |

### Image size accounting

| Component | Current | After fixes |
|---|---|---|
| `python:3.12-slim` base | ~130 MB | ~130 MB |
| Python deps (litellm, pymupdf, rendercv, typst, tokenizers…) | ~250 MB | ~250 MB |
| **Stowaway `backend/.venv`** | **~345 MB** | 0 |
| Backend source | ~1 MB | ~1 MB |
| Frontend static export (`out/`) | ~1.6 MB | ~1.6 MB |
| uv binary | ~30 MB | 0 (builder-only) |
| **Total** | **~1.1–1.3 GB** | **~400 MB** |

---

## 2. Compose topology

### `docker-compose.yml` (24 lines)

Single `app` service. `build: .`, `image: resumetailor`, `ports: 8000:8000`, named volumes `resumedb-data:/app/db` and `resumepdf-data:/app/pdfs`, `env_file: .env`, `restart: unless-stopped`, inline healthcheck duplicating the Dockerfile's. The uncommitted diff correctly removes the obsolete top-level `version: "3.9"` key.

### `docker-compose.test.yml` (39 lines)

Two services:
- `app` — same build/image, **also** `ports: 8000:8000`, volumes `test-db`/`test-pdfs`, inline `environment:` with `LLM_MOCK=true`, `OPENAI_API_KEY=mock-key-not-used`, `LLM_MODEL=gpt-4o-mini`, tighter healthcheck (10s/5s/5/30s).
- `playwright` — `mcr.microsoft.com/playwright:v1.44.0-jammy`, `depends_on: app: condition: service_healthy`, mounts `./test:/test`, `working_dir: /test`, `command: npx playwright test`, `BASE_URL=http://app:8000`.

### Findings

| Sev | Finding |
|---|---|
| **P0** | **Port 8000 triple-collision — this is the issue recorded in the project memory notes.** Three things bind host port 8000: `docker-compose.yml:7`, `docker-compose.test.yml:9`, and `scripts/start_mac.sh:31` / `scripts/start_windows.ps1:30` (`-p "${PORT}:${PORT}"` with `PORT=8000`). Worse than a port clash: **both compose files declare a service literally named `app`**, and neither sets a `name:`. Run from the same directory they resolve to the *same* compose project (`resume-tailoring-platform`). `docker compose -f docker-compose.test.yml up` therefore does not create a parallel stack — it **recreates the dev `app` container in place**, swapping its volumes and environment. Fix: add `name:` to each compose file, parameterise the port (`${PORT:-8000}:8000`), and bind test to 8001. |
| **P1** | `docker-compose.test.yml:2` still carries `version: "3.9"`. The prod file's uncommitted diff removes it; the test file was not updated. Emits a deprecation warning on every test run. |
| **P1** | **The Playwright service inherits the same darwin-binary trap.** `docker-compose.test.yml:30-33` bind-mounts `./test:/test` into a linux `playwright:v1.44.0-jammy` image and runs `npx playwright test` — against the **host's macOS `test/node_modules` (40 MB)**. There is no `npm ci` step in that service. It is the §1-P0 defect repeated at the test tier. |
| **P1** | **Playwright version drift.** `docker-compose.test.yml:26` pins the image at `v1.44.0-jammy` while `test/package.json:11` declares `"@playwright/test": "^1.44.0"`. The caret will float the mounted client away from the pinned image's bundled browsers. Pin both exactly, or install the client inside the container. |
| **P1** | **No dev / test / prod separation.** There are no compose profiles, no `docker-compose.override.yml`, and no prod file. The development story in `README.md:85-100` is entirely manual — `uv sync`, `LLM_MOCK=true DB_PATH=/tmp/... uv run uvicorn --reload`, then `npm run build && cp -r out ../backend/static` — with no compose equivalent, no bind-mount for hot reload, and no `develop.watch`. |
| **P1** | **Nothing present for a real deployment.** Missing: reverse proxy (Caddy/Traefik/nginx), TLS, `deploy.resources.limits` (a runaway Typst render or a large PDF import can OOM the host), `logging:` driver options (default `json-file` is unbounded → eventual disk fill), `stop_grace_period` (needed given the PID-1 issue), `read_only: true` + `tmpfs`, `security_opt: [no-new-privileges:true]`, `user:`. |
| **P2** | **The two files configure the app by different mechanisms.** `docker-compose.yml:11-12` uses `env_file: .env` and hard-fails if `.env` is absent; `docker-compose.test.yml:13-16` uses inline `environment:`. Neither sets `DB_PATH` or `PDFS_DIR` explicitly — both rely on the defaults in `backend/app/config.py:11-12` (`/app/db/resumedb.db`, `/app/pdfs`) happening to match the volume mount points. That coupling is undocumented and breaks silently if either side moves. |
| **P2** | **SQLite persistence.** The named volume `resumedb-data:/app/db` is the right call and survives `docker compose down` (but not `down -v`). Two wrinkles: (a) `db/.gitkeep` creates a second, entirely unused `./db` directory at the repo root — confusing; (b) `backend/app/database.py:35` uses plain `sqlite3.connect` with default journal mode — no WAL, no `busy_timeout`. With `--workers 1` (`Dockerfile:43`) that is survivable, but it is precisely why worker count cannot be raised. |
| **P2** | `docker-compose.test.yml` hardcodes `OPENAI_API_KEY=mock-key-not-used`. Harmless (it matches the `LLM_MOCK` path and `config.py:8`'s `"mock-key"` default), but it means the test stack silently still constructs a real adapter if `LLM_MOCK` is ever unset. |

---

## 3. Secrets & security posture

### Secret-exposure verdict: **clean.** No credential leak found.

Evidence gathered (existence and status only — no secret values were read or printed at any point):

- **`.env` is not tracked.** `git ls-files | grep -E '\.env'` returns only `.env.example`.
- **`.env` is ignored** at `.gitignore:43` (`.env`), plus `:44-45` for `.env.local` / `.env.*.local`.
- **`.env` was never committed, at any point in history.** `git log --all --diff-filter=A --name-only` across all refs shows the only `.env*` blob ever added is `.env.example`.
- **No key-shaped string exists in any commit.** Scanned every revision in `--all` with `git grep -I -E 'sk-(proj-)?[A-Za-z0-9_-]{32,}'`: **zero hits**. The same scan across all tracked files in the working tree: **zero hits**.
- The five commits returned by the coarse probe `git log --all -S'sk-'` (`e8f39b8`, `fd4d575`, `4f3a68a`, `740a2da`, `47a5ea0`) are false positives — they touch `README.md:68`, which contains the literal placeholder `# edit .env and set OPENAI_API_KEY=sk-...`, and planning docs with similar placeholder text. The two commits returned by `-S'OPENAI_API_KEY='` (`e8f39b8`, `ba2f918`) are the README placeholder and the OpenRouter→OpenAI migration, respectively.
- **Local `.env` key inventory** (names and presence only, values never read):

  | Key | Status |
  |---|---|
  | `OPENAI_API_KEY` | PRESENT — 164 characters (consistent with a live `sk-proj-` project key) |
  | `LLM_MODEL` | PRESENT — 11 characters |
  | `LLM_MOCK` | PRESENT — 5 characters |

  This matches `.env.example` exactly (no undocumented keys, no missing keys).
- Only two `.env*` files exist anywhere outside `node_modules`/`.venv`/`.git`: `./.env` and `./.env.example`. No stray `backend/.env` or `frontend/.env.local`.
- **No unsafe YAML deserialization.** `grep -rn "yaml.load\|Loader=\|unsafe_load\|full_load" backend/app/` → no matches. Only `yaml.safe_load` is used (`backend/app/adapters.py:77`, `:80`).
- **No shell injection surface.** `grep -rn "eval(\|exec(\|shell=True\|os.system" backend/app/` → the only hit is `backend/app/adapters.py:87 asyncio.create_subprocess_exec`, which takes an argv **list** (`:88-96`), not a shell string. Correct by construction.

### Security findings

| Sev | Finding |
|---|---|
| **P0** | **Zero authentication or authorization — anywhere.** `backend/app/main.py:57-70` registers seven routers and a `StaticFiles` mount and **no middleware of any kind** (`grep -rn "CORS\|allow_origins\|TrustedHost\|middleware" backend/app/` → no matches). Every row in every table is keyed to the literal string `'default'` (`backend/app/database.py:4 DEFAULT_USER_ID = "default"`; `backend/db/schema.sql:3,10,17,28,36,45` all `user_id TEXT NOT NULL DEFAULT 'default'`). Consequences: anyone who can reach port 8000 can read and overwrite the master resume, read the full chat history, read and rewrite the system prompt (`/api/system-prompt`), and — the expensive one — **spend the owner's OpenAI credits without limit** via `/api/chat`, `/api/resumes/generate`, `/api/evaluate`, and `/api/master-resume/import`. There is no rate limiting, no per-request token budget, and no spend ceiling. This is tolerable *only* on `localhost`. `docker-compose.yml:7` publishes `8000:8000`, binding `0.0.0.0` — on any shared network, VPS, or cloud host the application is fully open to the internet. |
| **P1** | **Unbounded upload read → trivial memory DoS.** `backend/app/routes/master_resume.py:134` does `pdf_bytes = await file.read()`, loading the **entire** request body into RAM before any size check. The 10 MB guard lives downstream at `backend/app/adapters.py:107-111` (`PyMuPDFAdapter._MAX_BYTES = 10 * 1024 * 1024`) — i.e. *after* the allocation has already happened. A 2 GB POST to `/api/master-resume/import` OOMs the container. Additionally, the `content_type != "application/pdf"` check at `:132` is client-supplied and trivially spoofed; the only real validation is `pymupdf.open(stream=..., filetype="pdf")` at `adapters.py:120`. Fix: stream to a temp file with a running byte cap, or reject on `Content-Length` before the first read. (The `_MAX_PAGES = 50` guard at `adapters.py:106,114-117` is well-placed and correct.) |
| **P1** | **LLM-authored YAML is handed to a document renderer running as root.** `backend/app/adapters.py:70-102`: model output is written to `resume.yaml` in a `tempfile.TemporaryDirectory()` and `rendercv render` is spawned on it. RenderCV/Typst resolves file paths declared inside the YAML (photos, includes, asset references). Typst's own sandbox is the only barrier between model-controlled input and the container filesystem — and per §1 the container runs as **root** with the SQLite volume mounted at `/app/db`. This is the highest-value exploit chain in the application. Mitigation is structural, not code-level: non-root `USER`, `read_only: true` rootfs, `tmpfs` for the render scratch directory. |
| **P1** | **API key leaks into the process environment and every child process.** `backend/app/adapters.py:28` — `LiteLLMAdapter.__init__` does `os.environ["OPENAI_API_KEY"] = api_key`, mutating **process-global** state. Every subprocess spawned afterwards inherits it, including `rendercv` at `:87-96`, which has no use for it. If `rendercv`/Typst ever logs or echoes its environment (e.g. in a crash dump), the key surfaces in `RenderError` output — which, per the next finding, is returned to the client. Fix: pass an explicit scrubbed `env=` to `create_subprocess_exec`, and hand the key to litellm per-call rather than via `os.environ`. |
| **P2** | **Internal detail leaks to clients in error bodies.** `backend/app/adapters.py:97-101` embeds the full `rendercv` stdout **and** stderr (absolute container paths, Python tracebacks, Typst diagnostics) into the `RenderError` message, and `backend/app/main.py:45-47` returns `str(exc)` verbatim in the 500 JSON body. The same pattern applies to `LLMUnavailableError` at `main.py:40-42`, which returns raw litellm exception text — that can include request URLs, provider names, and model routing detail. Log the detail server-side; return an opaque `code` to the client. |
| **P2** | **No CORS middleware.** Correct as of today — the frontend is served same-origin from `main.py:68-70`'s `StaticFiles` mount, so no CORS is needed. Recording it because the failure mode is predictable: the moment the frontend moves to a separate origin, every route breaks, and the reflexive fix (`allow_origins=["*"]` with credentials) applied to a **completely unauthenticated API** would be materially worse than the current state. Document the same-origin assumption explicitly. |
| **P2** | **No security headers.** Nothing sets CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, or HSTS on the static mount or the API. Relevant because `backend/app/routes/resumes.py:176-177` serves generated PDFs with `Content-Disposition: inline` — rendered in-browser from the application's own origin. |
| **P2** | **Unguarded path join on a DB-sourced value.** `backend/app/routes/resumes.py:173` and `:202` construct `Path(_pdfs_dir()) / row["pdf_path"]`. The stored value is always server-generated (`:186` and `:190` write `f"{resume_id}.pdf"`), so this is not exploitable today. But there is no `.resolve().is_relative_to(pdfs_dir)` assertion, so the first time that column becomes user-influenced — an import path, a user-chosen filename — it is an immediate directory traversal (read via `:173`, and `unlink` via `:202-203` in the delete handler). Add the guard now while it is free. |
| **P2** | **Dependency vulnerability posture is unknown, and nothing would tell you.** 80 locked packages in `backend/uv.lock`. The notable attack-surface ones are `pymupdf 1.2x` (parses untrusted PDFs from `/api/master-resume/import` — historically CVE-prone), `litellm 1.9x` (large, fast-moving, network-facing), and `aiohttp`. Frontend: `next 14.2.5` pinned exactly, React 18.3.1. No `pip-audit` / `uv pip audit`, no `npm audit`, no Dependabot, no Trivy, no SBOM. Not flagging a specific CVE — flagging that there is **no mechanism by which you would ever learn about one**. |
| **P2** | **`.gitignore` is internally inconsistent about agent artifacts.** The uncommitted `.gitignore:76-79` newly ignores `.agents/`, `skills-lock.json`, and `.claude/skills/` — but `skills-lock.json` is currently untracked-and-present, while `.superpowers/sdd/*.md` (2 files) **is tracked** and `.superpowers/` is not ignored at all. Pick one policy. |
| **P2** | **Personal data sitting one `git add -A` away from a public repo.** `planning/master-resume.yaml` is untracked, contains real personal resume content, and `.gitignore` does not cover `planning/`. The repo has a public-looking GitHub remote. Add the path to `.gitignore` before it becomes a history-rewrite problem. |

---

## 4. CI/CD

### What exists

**Nothing.** No `.github/` directory. No `.gitlab-ci.yml`, no `.circleci`, no Jenkinsfile, no `.pre-commit-config.yaml`. The `find` probe for CI YAML returns only the two compose files, planning YAML, and 25 stale `.playwright-mcp/` page dumps.

No linter or formatter config exists either: no `ruff`/`black`/`mypy` sections in `backend/pyproject.toml` (which has only `[project]`, `[dependency-groups]`, and `[tool.pytest.ini_options]`), and no `.eslintrc` / `eslint.config.js` in `frontend/` despite Next 14 shipping `next lint`.

History corroborates: 30 commits straight to `main`, no merge commits, no tags, no release process.

### What should exist — `.github/workflows/ci.yml`

Three jobs, fanning into a gate.

**Job `backend`** — `ubuntu-latest`, `astral-sh/setup-uv@v5` with cache enabled:

1. `uv sync --frozen` — doubles as the **lockfile-drift gate**: fails if `pyproject.toml` and `uv.lock` have diverged.
2. `uv run ruff check . && uv run ruff format --check .` — requires adding `ruff` to the dev group; none exists today.
3. `uv run mypy app` — requires adding `mypy`. Cheap to adopt: the codebase already uses `from __future__ import annotations` (`main.py:2`, `adapters.py:1`) and modern `X | None` unions throughout.
4. `uv run pytest --cov=app --cov-report=term --cov-fail-under=70`. There are 13 tracked test files under `backend/tests/` (`test_database`, `test_llm`, `test_yaml_utils`, and seven `test_routes_*`), plus the untracked `backend/tests/test_rendercv_validation.py` which should be committed. `[tool.pytest.ini_options] testpaths = ["tests"]` is already set.
5. **Migration / schema check** (new): assert that `init_db` against a fresh temp DB produces a schema identical to `backend/db/schema.sql`; once migrations exist (§6), additionally assert that replaying the migration chain against an empty DB yields that same schema. This is the gate that catches the §6 `CREATE TABLE IF NOT EXISTS` silent-no-op class of bug.

**Job `frontend`** — `ubuntu-latest`, `actions/setup-node@v4` with `node-version: 20`, `cache: npm`, `cache-dependency-path: frontend/package-lock.json`:

1. `npm ci` — `frontend/package-lock.json` is committed, so this is sound.
2. `npx tsc --noEmit` — **nothing typechecks today.** Corroborating evidence: `frontend/tsconfig.tsbuildinfo` (100 KB) is committed, i.e. someone's local incremental build state is the only record of a typecheck ever running.
3. `npm test` — but **drop the `--passWithNoTests`**. `frontend/package.json:9` is `"test": "jest --passWithNoTests"`, which passes green on a repo with zero tests. There are three real test files (`src/__tests__/ChatPanel.test.tsx`, `MasterResumePanel.test.tsx`, `ResumeListPanel.test.tsx`); CI should fail if they are deleted.
4. `npm run build` — gates the static export (`next.config.js:3-6`: `output: 'export'`, `distDir: 'out'`, `trailingSlash: true`, `images.unoptimized`).
5. Add ESLint: `npx next lint`. No config exists at present.

**Job `image-and-e2e`** — `needs: [backend, frontend]`:

1. `docker/setup-buildx-action@v3` + `docker/build-push-action@v6` with `cache-from: type=gha` / `cache-to: type=gha,mode=max`. Build once with `load: true`.
2. **E2E gate**: `docker compose -f compose.test.yaml up --abort-on-container-exit --exit-code-from playwright`, after the §2 fixes (own project name, port 8001, `npm ci` inside the container instead of a darwin bind-mount). Upload `e2e/playwright-report/` as a workflow artifact on failure — the config already emits it (`test/playwright.config.ts:18`, `["html", { open: "never" }]`) and captures `screenshot: only-on-failure`, `video: retain-on-failure`, `trace: on-first-retry` (`:11-13`).
3. **Image scan**: Trivy or Grype against the built image; fail on HIGH+ with a fix available.
4. **On `main` only** — publish to `ghcr.io/parthkishan20/resume-tailoring-platform`, tags `sha-<sha>` and `latest`, with `--sbom=true --provenance=true`.

**Supporting config**

- `.github/dependabot.yml` covering four ecosystems: `pip` (`/backend`), `npm` (`/frontend`), `npm` (`/e2e`), `docker` (`/docker`), plus `github-actions` (`/`).
- Enable GitHub secret scanning + push protection on the public repo (or add `gitleaks` as a CI step). The history is clean today — keep it that way automatically rather than by audit.
- Branch protection on `main`: require the `ci` check, require a PR. The current 30-straight-to-main history makes this the biggest process change of the set.

---

## 5. Repo hygiene

**Materially better than expected.** `git ls-files` confirms **no build artifacts are committed**: no `frontend/out`, no `backend/static`, no `frontend/.next`, no `test/playwright-report`, no `test/test-results`, no `.playwright-mcp`, no `.pytest_cache`, no `.DS_Store`, no `node_modules`, no `.venv`. The 79-line `.gitignore` covers every one of those. 129 tracked files total.

| Sev | Finding | Action |
|---|---|---|
| **P1** | `.superpowers/sdd/t2-llm-report.md` and `.superpowers/sdd/t6-tester-report.md` are **tracked**, while the `.superpowers/` directory (2.9 MB on disk) is **not** gitignored. Inconsistent with the uncommitted `.gitignore:76-79` block that ignores the other agent-tooling directories. | Either ignore `.superpowers/` and `git rm --cached` the two files, or move both into `docs/` where the sibling reports already live (`docs/superpowers/plans/`, `docs/superpowers/specs/`). |
| **P2** | `frontend/tsconfig.tsbuildinfo` (100 KB) is committed — a TypeScript **incremental build cache**, machine-local by nature and the 10th-largest blob in the repo. | Add `*.tsbuildinfo` to `.gitignore`; `git rm --cached frontend/tsconfig.tsbuildinfo`. |
| **P2** | `backend/rendercv_config/settings.yaml` (17 lines) is committed but **never read by any code** — `backend/app/adapters.py:12,88-90` references only `design.yaml` and `locale.yaml`. It also hardcodes a personal identity at `:4`: `pdf_title: Parthkumar_Patel_resume_{role}`, and at `:8` has a trailing-whitespace typst_path. Dead configuration carrying personal data in a public repo. | Delete it, or wire it into the render call and parameterise the name. |
| **P2** | `planning/master-resume.yaml` is untracked, present, and contains **real personal resume data**. `.gitignore` has no `planning/` rule. The repo has a public GitHub remote. | Add `planning/master-resume.yaml` to `.gitignore` immediately (keep `planning/example-master-resume.yaml` tracked). |
| **P2** | Stale working-tree directories, untracked but cluttering the tree and the Docker build context: `.playwright-mcp/` (168 K — 25 page dumps dated 2026-07-07), `.pytest_cache/` (20 K), `.superpowers/` (2.9 M), `./.DS_Store`, `./docs/.DS_Store`, and `frontend/.next/` (92 MB — **stale**, since `next.config.js:4` sets `distDir: 'out'`). | `rm -rf` all of them; add `*.tsbuildinfo` and `.superpowers/` to `.gitignore`. Reclaims ~95 MB of working tree. |
| **P2** | `.git` is 4.5 MB across **534 loose objects and zero packs** — never garbage-collected. | `git gc --aggressive --prune=now` → well under 2 MB. |
| **P2** | `.claude/settings.json` is tracked but its uncommitted diff is pure machine-local churn (dropping the `context7` and `playwright` plugins, reindenting `env`). | Move machine-local overrides to `.claude/settings.local.json`; keep only shared config tracked. |
| **P2** | Commit-message quality: `a973923` and `4f3a68a` share the identical generic message *"Refactor code structure for improved readability and maintainability"*; `9a784ba` and `99c37fc` also duplicate. | Adopt Conventional Commits consistently (most of the history already does) and enforce via a CI commitlint step. |

**Purge vs. gitignore, explicitly**

- **Purge outright (delete from disk):** `.playwright-mcp/`, `.pytest_cache/`, `./.DS_Store`, `docs/.DS_Store`, `frontend/.next/`.
- **Gitignore *and* untrack:** `frontend/tsconfig.tsbuildinfo`, `.superpowers/` (after relocating the two tracked reports).
- **Gitignore before it bites:** `planning/master-resume.yaml`.
- **Leave alone:** all eight `docs/screenshots/*.png` (76–156 K, referenced from `README.md:11-23`), `planning/example-yaml-preview.png`, `backend/uv.lock`, both `package-lock.json` files, `backend/tests/fixtures/mock.pdf`. All legitimate.
- **No `git filter-repo` / history rewrite is needed.** No secret and no large binary has ever been committed.

---

## 6. Observability & ops — entirely absent

| Area | Current state | Target |
|---|---|---|
| **Logging** | **Zero.** No `logging` import anywhere in `backend/app/`. The only output is uvicorn's default access log to stdout, and even that is not guaranteed line-buffered (no `PYTHONUNBUFFERED` in the Dockerfile). Critically, the four exception handlers at `backend/app/main.py:35-52` return `str(exc)` to the client and **never log server-side** — every LLM auth failure, every render failure, every PDF extraction failure is invisible in `docker logs`. | `structlog` or a stdlib JSON formatter; a request-id middleware; log *every* exception with full context **before** returning the opaque response; `logging: json-file` with `max-size: 10m, max-file: 3` in compose. |
| **Metrics** | **None.** No visibility into LLM latency, token spend, render success rate, request p95, or queue depth. | `prometheus-fastapi-instrumentator` (a one-line install) for the HTTP basics, plus explicit application counters: `llm_tokens_total{model,route}`, `llm_requests_total{model,route,outcome}`, `render_duration_seconds`, `render_failures_total`, `pdf_import_bytes`. Token spend is the one that costs real money and is currently completely unmeasured. |
| **Error tracking** | **None.** | `sentry-sdk[fastapi]` with `send_default_pii=False`. Note: resume content and job descriptions **are PII** — scrub `yaml_content`, `job_description`, and chat message bodies from event payloads via `before_send`. |
| **Health / readiness** | `/api/health` (`backend/app/routes/health.py:7-9`) returns a hardcoded `{"status": "ok"}`. Both the Dockerfile healthcheck (`:38-39`) and both compose healthchecks point at it. It cannot detect a corrupt DB, a full or unwritable `PDFS_DIR`, or a missing `rendercv` binary. | Split the concerns: keep `/api/health` trivial (liveness), add `/api/ready` (readiness) that does `SELECT 1` against SQLite, checks `PDFS_DIR` is writable, and does `shutil.which("rendercv")`. Repoint all three healthchecks at `/api/ready`. |
| **Backups** | **None.** The SQLite database exists only inside the `resumedb-data` named Docker volume, and generated PDFs only in `resumepdf-data`. A `docker compose down -v`, a Docker Desktop factory reset, or volume corruption means **total, unrecoverable loss** of the master resume, every generated resume, all chat history, all generation rules, and the custom system prompt. No backup mechanism and no restore procedure appears anywhere in `README.md` or `scripts/`. | A sidecar or host cron running `sqlite3 /app/db/resumedb.db ".backup /backup/$(date +%F).db"` — the **online backup API**, which is safe against a live database, unlike `cp` — plus a `tar` of `/app/pdfs`. Retain 7 daily + 4 weekly. Document a single-command restore, and **actually test it once**. |
| **Migrations** | **None, and the current mechanism fails silently.** `backend/app/database.py:33-37` runs `conn.executescript(_schema_sql())` on every boot, and `backend/db/schema.sql` is entirely `CREATE TABLE IF NOT EXISTS` (lines 1, 8, 15, 26, 34, 43). Adding a column to `schema.sql` is therefore a **silent no-op against any existing database**. The app then queries a column that does not exist and 500s at runtime, with no warning at startup and no error in the logs (because there are no logs). This is the most dangerous latent operational issue in the project. | Alembic, or a minimal `PRAGMA user_version`-based runner: ordered `backend/migrations/NNN_*.sql`, each applied in a transaction at lifespan startup, with an automatic `.backup` taken before the first migration of a run. Gate it in CI per §4. |
| **Upgrade procedure** | Undocumented, and the provided script is actively misleading. `scripts/start_mac.sh:23` rebuilds **only** if `--build` was passed *or* the image is absent (`docker image inspect`). So running `./scripts/start_mac.sh` after a `git pull` silently starts the **old** image with none of the new code. Same logic in `scripts/start_windows.ps1:22`. | Document `git pull && ./scripts/start_mac.sh --build`; better, switch to pulling a tagged image from GHCR. Have the start scripts print the running image digest and warn when it differs from the built source. |
| **Resource ceilings** | None. No CPU or memory limit on the container, no request timeout, no concurrency cap on `rendercv` invocations (each spawns a Typst process). A burst of `/api/resumes/{id}/render` calls forks unbounded subprocesses. | `deploy.resources.limits` in the prod compose file; a `asyncio.Semaphore` around `RenderCVAdapter.render`; uvicorn `--timeout-keep-alive`. |

---

## 7. Restructure proposal

### 7.1 Target top-level layout

```
.
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                   ← NEW: lint, typecheck, test, build, e2e, scan
│   │   └── release.yml              ← NEW: tag → GHCR publish w/ SBOM + provenance
│   └── dependabot.yml               ← NEW: pip, npm ×2, docker, github-actions
├── .dockerignore                    ← NEW (§7.3) — the single highest-value file here
├── .gitignore                       ← + *.tsbuildinfo, .superpowers/, planning/master-resume.yaml
├── .env.example
├── Justfile                         ← NEW (§7.2)
├── README.md
├── compose.yaml                     ← dev: bind-mounts, --reload, watch
├── compose.prod.yaml                ← proxy + TLS + limits + logging + backups
├── compose.test.yaml                ← own project name, port 8001, in-container npm ci
├── docker/
│   ├── Dockerfile                   ← moved + rewritten (§7.4)
│   └── Caddyfile                    ← NEW
├── backend/
│   ├── pyproject.toml               ← + ruff, mypy in the dev group
│   ├── uv.lock
│   ├── app/
│   ├── db/schema.sql
│   ├── migrations/                  ← NEW (§6): 001_init.sql, 002_….sql
│   ├── rendercv_config/             ← design.yaml, locale.yaml (drop dead settings.yaml)
│   └── tests/                       ← + test_rendercv_validation.py (currently untracked)
├── frontend/
├── e2e/                             ← renamed from test/ — unambiguous vs backend/tests
├── docs/                            ← absorbs .superpowers/sdd/*.md
└── planning/                        ← master-resume.yaml gitignored
```

Removals: `scripts/start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1` are superseded by the Justfile plus a single `docker compose` path. If the non-technical-user quick-start in `README.md:61-77` is a real requirement, keep thin `start.sh` / `start.ps1` wrappers — **but fix the `--build` staleness bug** (`start_mac.sh:23`, `start_windows.ps1:22`) first, since it currently ships stale code after every `git pull`.

### 7.2 Task surface — `Justfile`

```make
default: help

# — development —
dev:            # docker compose up --build --watch        (dev profile)
down:           # docker compose down
logs:           # docker compose logs -f app
shell:          # docker compose exec app bash

# — quality —
lint:           # uv run ruff check . && uv run ruff format --check . && npx next lint
typecheck:      # uv run mypy app && npx tsc --noEmit
test:           # uv run pytest --cov=app && npm test --prefix frontend
e2e:            # docker compose -f compose.test.yaml up --abort-on-container-exit \
                #   --exit-code-from playwright
build:          # docker build -f docker/Dockerfile -t resumetailor .
ci:             # lint typecheck test build e2e   ← byte-identical to GH Actions

# — operations —
migrate:        # uv run python -m app.migrate
backup:         # sqlite3 .backup + tar pdfs → ./backups/$(date +%F)/
restore f=:     # guided restore from ./backups/{{f}} with explicit confirmation
audit:          # uv pip audit && npm audit --prefix frontend && trivy image resumetailor
clean:          # rm -rf .pytest_cache .playwright-mcp frontend/.next e2e/test-results \
                #   **/*.tsbuildinfo **/.DS_Store
gc:             # git gc --aggressive --prune=now
```

The `ci` recipe running byte-identically locally and in GitHub Actions is the single highest-leverage addition in this proposal — it is what makes the CI gate trustworthy rather than a second, divergent build.

### 7.3 `.dockerignore` — the P0 fix (≈850 MB context → ≈3 MB)

```gitignore
# VCS
.git
.gitignore
.gitattributes

# Dependencies — never ship host-built trees into a linux image
**/node_modules
**/.venv
**/__pycache__
**/*.py[cod]

# Build outputs
frontend/.next
frontend/out
backend/static
**/*.tsbuildinfo

# Caches
.pytest_cache
**/.pytest_cache
.mypy_cache
.ruff_cache
.cache

# Secrets — belt and braces against a future `COPY . .`
.env
.env.*
!.env.example

# Runtime data
db/*.db
db/*.db-wal
db/*.db-shm
pdfs/
backups/

# Not needed at build time
docs/
planning/
e2e/
test/
scripts/
.playwright-mcp
.superpowers
.agents
.claude
skills-lock.json
README.md
Justfile
compose*.yaml
docker-compose*.yml

# OS noise
**/.DS_Store
Thumbs.db
```

`.env` / `.env.*` and `planning/` are excluded explicitly and redundantly — the correct posture for a file containing a live API key and a file containing personal data.

### 7.4 Target Dockerfile — `docker/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7

# ── Stage 1: frontend dependencies (cached on lockfile only) ─────────────────
FROM node:20.18-slim@sha256:<pin> AS fe-deps
WORKDIR /b/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# ── Stage 2: frontend build (explicit source paths ONLY) ─────────────────────
FROM fe-deps AS fe-build
COPY frontend/src ./src
COPY frontend/public ./public
COPY frontend/next.config.js frontend/tsconfig.json \
     frontend/tailwind.config.ts frontend/postcss.config.js ./
RUN npm run build                                  # → /b/frontend/out

# ── Stage 3: Python dependencies (cached on pyproject+lock only) ─────────────
FROM python:3.12.8-slim@sha256:<pin> AS py-deps
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── Stage 4: runtime ─────────────────────────────────────────────────────────
FROM python:3.12.8-slim@sha256:<pin> AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -r app && useradd -r -g app -u 10001 app \
 && install -d -o app -g app /app/db /app/pdfs

COPY --from=py-deps /opt/venv /opt/venv

WORKDIR /app/backend
COPY --chown=app:app backend/app             ./app
COPY --chown=app:app backend/db              ./db
COPY --chown=app:app backend/migrations      ./migrations
COPY --chown=app:app backend/rendercv_config ./rendercv_config
COPY --from=fe-build --chown=app:app /b/frontend/out ./static

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import urllib.request,sys; \
      sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=4).status == 200 else 1)"

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
```

Each change maps to a finding:

| Change | Fixes |
|---|---|
| Explicit `COPY frontend/src`, `frontend/public`, named config files — never `COPY frontend/ ./` | §1-P0 (darwin `node_modules` overwrite) |
| Explicit `COPY backend/app`, `backend/db`, … — never `COPY backend/ ./backend/` | §1-P0 (345 MB darwin `.venv` stowaway) |
| `pyproject.toml` + `uv.lock` copied alone before `uv sync`; `--no-install-project` | §1-P1 (dependency layer caching) |
| `UV_PROJECT_ENVIRONMENT=/opt/venv` + `PATH=/opt/venv/bin` → uvicorn invoked directly, no `uv run` | §1-P1 (PID 1 / SIGTERM); also removes per-boot re-resolution |
| `ENTRYPOINT ["tini","--"]` | §1-P1 (signal forwarding, zombie reaping of `rendercv` children) |
| `useradd -u 10001 app` + `USER app` + `--chown` on every COPY | §1-P1 (root), §3-P1 (LLM-YAML→renderer chain) |
| Digest-pinned `node`/`python`, `uv:0.5.11` pinned | §1-P1 (reproducibility) |
| `PYTHONUNBUFFERED`, `PYTHONDONTWRITEBYTECODE`, `UV_COMPILE_BYTECODE` | §1-P2, §6 (logging) |
| Healthcheck → `/api/ready` | §1-P2, §6 (health) |
| `--proxy-headers --forwarded-allow-ips` | §2 (reverse proxy in prod) |
| **No `apt-get install texlive`** — `rendercv[full]` keeps shipping Typst as a wheel | preserves the existing good decision |

`.dockerignore` remains mandatory alongside this: it is what keeps the context small, and it is the backstop if an explicit COPY ever regresses to a wildcard.

### 7.5 Compose profiles

**`compose.yaml` (development)**

```yaml
name: resumetailor-dev
services:
  app:
    build: { context: ., dockerfile: docker/Dockerfile }
    ports: ["${PORT:-8000}:8000"]
    environment:
      LLM_MOCK: "${LLM_MOCK:-false}"
      DB_PATH: /app/db/resumedb.db
      PDFS_DIR: /app/pdfs
    env_file: [.env]
    volumes: [resumedb-data:/app/db, resumepdf-data:/app/pdfs]
    develop:
      watch:
        - { action: sync+restart, path: ./backend/app, target: /app/backend/app }
        - { action: rebuild,      path: ./backend/uv.lock }
    stop_grace_period: 30s
volumes: { resumedb-data: , resumepdf-data: }
```

**`compose.test.yaml`**

```yaml
name: resumetailor-test          # ← alone, this fixes the §2-P0 project collision
services:
  app:
    build: { context: ., dockerfile: docker/Dockerfile }
    ports: ["8001:8000"]          # ← no longer fights the dev stack
    environment: [LLM_MOCK=true, LLM_MODEL=gpt-4o-mini, OPENAI_API_KEY=mock-key-not-used]
    tmpfs: [/app/db, /app/pdfs]   # ephemeral — no test volumes to leak between runs
    healthcheck: { test: [...], interval: 10s, timeout: 5s, retries: 5, start_period: 30s }
  playwright:
    image: mcr.microsoft.com/playwright:v1.44.0-jammy   # pin must match e2e/package.json exactly
    depends_on: { app: { condition: service_healthy } }
    volumes: ["./e2e:/e2e:ro", "pw-modules:/e2e/node_modules"]
    working_dir: /e2e
    command: sh -c "npm ci && npx playwright test"      # ← linux install, not a darwin bind-mount
    environment: [BASE_URL=http://app:8000]
volumes: { pw-modules: }
```

**`compose.prod.yaml`**

```yaml
name: resumetailor
services:
  caddy:
    image: caddy:2.8-alpine
    ports: ["80:80", "443:443"]
    volumes: [./docker/Caddyfile:/etc/caddy/Caddyfile:ro, caddy-data:/data, caddy-config:/config]
    restart: unless-stopped
  app:
    image: ghcr.io/parthkishan20/resume-tailoring-platform:${TAG}
    expose: ["8000"]              # ← NOT published to the host; only Caddy reaches it
    env_file: [.env]
    volumes: [resumedb-data:/app/db, resumepdf-data:/app/pdfs]
    restart: unless-stopped
    stop_grace_period: 30s
    read_only: true
    tmpfs: [/tmp]
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    deploy: { resources: { limits: { cpus: "2", memory: 2G } } }
    logging: { driver: json-file, options: { max-size: 10m, max-file: "3" } }
  backup:
    image: alpine:3.20
    volumes: [resumedb-data:/db:ro, resumepdf-data:/pdfs:ro, ./backups:/backup]
    entrypoint: /backup/run.sh    # sqlite3 .backup + tar, 7 daily / 4 weekly
    restart: unless-stopped
volumes: { resumedb-data: , resumepdf-data: , caddy-data: , caddy-config: }
```

Note that `app` is unpublished in prod — given §3-P0 (no authentication whatsoever), putting the container directly on a host port is the difference between "a local tool" and "an open API spending my OpenAI budget". Caddy should additionally enforce basic auth or forward-auth until real authentication exists in the application.

### 7.6 GitHub Actions workflow plan

`.github/workflows/ci.yml` — triggers `push: [main]`, `pull_request: [main]`, `workflow_dispatch`. Concurrency group per-ref with `cancel-in-progress: true`.

| Job | Runner | Steps | Gate |
|---|---|---|---|
| `backend` | ubuntu-latest | setup-uv (cached) → `uv sync --frozen` → `ruff check` + `ruff format --check` → `mypy app` → `pytest --cov=app --cov-fail-under=70` → schema/migration equivalence check | lockfile drift, lint, types, unit tests, schema drift |
| `frontend` | ubuntu-latest | setup-node 20 + npm cache → `npm ci` → `tsc --noEmit` → `next lint` → `jest` (no `--passWithNoTests`) → `npm run build` | types, lint, component tests, static export builds |
| `image` | ubuntu-latest, `needs: [backend, frontend]` | buildx + GHA cache → `build-push-action` (`load: true`) → Trivy scan (fail HIGH+ fixable) | image builds, no known-fixable HIGH CVEs |
| `e2e` | ubuntu-latest, `needs: [image]` | `docker compose -f compose.test.yaml up --abort-on-container-exit --exit-code-from playwright` → upload `e2e/playwright-report/` on failure | all 8 Playwright scenarios (`e2e/01-fresh-start` … `08-rules`) |
| `publish` | ubuntu-latest, `needs: [e2e]`, `if: github.ref == 'refs/heads/main'` | push to GHCR, tags `sha-<sha>` + `latest`, `--sbom=true --provenance=true` | — |

`.github/workflows/release.yml` — on `push: tags: ['v*']`: rebuild, push `v<semver>` + `latest`, generate release notes, attach the SBOM.

`.github/dependabot.yml` — weekly, five ecosystems (`pip` → `/backend`, `npm` → `/frontend`, `npm` → `/e2e`, `docker` → `/docker`, `github-actions` → `/`), grouped minor+patch updates to keep PR volume sane.

Branch protection on `main`: require `backend`, `frontend`, `image`, `e2e` to pass; require a pull request. Given the current 30-commits-straight-to-`main` history, this is the largest *process* change in the proposal and the one that makes every technical gate above actually binding.

---

## 8. Severity roll-up

### P0 — fix before any deployment, and the first three before the next `docker build`

1. **No `.dockerignore`** — ~850 MB build context on every build; `.env` (live 164-char API key) streamed into the context. (`.dockerignore` absent; §7.3 is the fix)
2. **`Dockerfile:9`** `COPY frontend/ ./` overwrites the linux `npm ci` tree with the host's macOS `node_modules` — confirmed `@next/swc-darwin-arm64` present. Frontend build is arch-wrong and non-reproducible.
3. **`Dockerfile:22`** `COPY backend/ ./backend/` bakes a 345 MB conda/darwin/Python-3.13 `.venv` into a Python-3.12 linux image, permanently in the layer history.
4. **Port 8000 + compose project collision** — `docker-compose.yml:7`, `docker-compose.test.yml:9`, `scripts/start_mac.sh:31`, `scripts/start_windows.ps1:30`; both compose files use service name `app` with no `name:` key, so the test stack recreates the dev container in place. (Matches the recorded memory note.)
5. **No authentication anywhere** (`backend/app/main.py:57-70`, `database.py:4`, `db/schema.sql` `user_id DEFAULT 'default'`) — unlimited read/write of all data and unlimited spend of the owner's OpenAI credits by anyone who can reach port 8000, which compose binds on `0.0.0.0`. P0 the moment this leaves `localhost`.

### P1

6. Dependency layer caching destroyed — any backend source edit re-installs 80 packages (`Dockerfile:22` before `:26`).
7. Container runs as **root** — no `USER` directive.
8. `uv` is PID 1; `SIGTERM` not forwarded → `docker stop` kills in-flight SSE and mid-write renders (`Dockerfile:41-43`).
9. Floating base images and `uv:latest` (`Dockerfile:4,14,17`); frontend build non-reproducible despite a committed lockfile.
10. Unbounded `await file.read()` at `backend/app/routes/master_resume.py:134` — size cap is downstream at `adapters.py:107-111`, after the allocation. Memory DoS.
11. LLM-authored YAML → `rendercv`/Typst → root-writable filesystem with the DB volume mounted (`adapters.py:70-102`).
12. API key written to process-global `os.environ` and inherited by the `rendercv` subprocess (`adapters.py:28`, `:87-96`).
13. Darwin `test/node_modules` bind-mounted into the linux Playwright container, with no `npm ci` (`docker-compose.test.yml:30-33`).
14. `version: "3.9"` left in `docker-compose.test.yml:2`; Playwright image pin vs `^1.44.0` caret drift.
15. No dev/test/prod separation; no reverse proxy, TLS, resource limits, log rotation, or `stop_grace_period`.
16. `.superpowers/sdd/*.md` tracked while `.superpowers/` is unignored.
17. **No CI whatsoever** (§4) — nothing lints, typechecks, or gates anything.
18. **No migrations** (`database.py:33-37` + all-`IF NOT EXISTS` schema) — schema changes are silent no-ops on existing databases, producing runtime 500s with no logs. **No backups** of the SQLite volume and no restore procedure (§6).

### P2

19. Healthcheck duplicated between Dockerfile and both compose files, and probes a static literal (`health.py:8`).
20. Full `rendercv` stderr and raw litellm exception text returned to clients (`adapters.py:97-101` → `main.py:45-47`; `main.py:40-42`).
21. No security headers; PDFs served `Content-Disposition: inline` from the app origin (`resumes.py:176-177`).
22. Unguarded `Path(pdfs_dir) / row["pdf_path"]` join, including in the `unlink` path (`resumes.py:173`, `:202`).
23. No CORS middleware — correct today, but the same-origin assumption is undocumented.
24. No dependency vulnerability scanning of any kind (80 Python packages incl. `pymupdf` parsing untrusted PDFs; `litellm`; `next`).
25. `frontend/tsconfig.tsbuildinfo` (100 KB build cache) committed.
26. `backend/rendercv_config/settings.yaml` is dead config and hardcodes a personal name at `:4`.
27. `planning/master-resume.yaml` — real personal data, untracked but unignored, public remote.
28. `.git` never gc'd — 534 loose objects, 0 packs.
29. Stale working-tree dirs: `.playwright-mcp/`, `.pytest_cache/`, `.superpowers/`, two `.DS_Store`, `frontend/.next` (92 MB, stale given `distDir: 'out'`).
30. Missing `PYTHONUNBUFFERED` / `PYTHONDONTWRITEBYTECODE`; duplicate `WORKDIR`; redundant `mkdir`.
31. `scripts/start_mac.sh:23` / `start_windows.ps1:22` silently run the stale image after `git pull` unless `--build` is passed.
32. `.claude/settings.json` tracked but carrying machine-local churn.
33. Duplicate generic commit messages (`a973923`/`4f3a68a`, `9a784ba`/`99c37fc`).

### Closing note

**Nothing in git history leaks a credential.** Every revision was scanned for key-shaped strings and `.env` was never committed at any point. That is the one class of problem that would have been expensive to fix — it is clean, and adding push protection or a `gitleaks` CI step keeps it that way without further audits.

The other genuinely good decision worth protecting: `rendercv[full]` ships Typst as a pip wheel, so there is **no TeX Live in the image**. Every restructure step above preserves that.
