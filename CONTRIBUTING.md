# Contributing

Everything you need to go from a clone to a merged change.

If you are an autonomous agent, read [`AGENTS.md`](./AGENTS.md) first: it is the binding
contract and it overrides anything here that conflicts. This document is the human-facing
version of the same rules.

**Orientation:** [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) is the mental model to have
before you read code. [`docs/API.md`](./docs/API.md) is the endpoint reference.
[`docs/TROUBLESHOOTING.md`](./docs/TROUBLESHOOTING.md) covers the failures you are most likely
to hit while developing. [`PLAN.md`](./PLAN.md) is what is being built and in what order.

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.12 | `backend/pyproject.toml` sets `requires-python = ">=3.12"`, and the image is `python:3.12-slim`. Note that a 3.13 local environment will work but is a version skew nothing tests |
| [uv](https://docs.astral.sh/uv/) | 0.11.x | The only supported Python package manager here. `uv.lock` is committed and `--frozen` is used everywhere |
| Node | 20 | Matches the `node:20-slim` build stage |
| Docker | any recent | Needed to run the full stack and the e2e suite. Not needed for `make check` |
| `make` | any | Every gate has a target |

You do **not** need an LLM API key to develop or to run any test. The whole backend swaps to a
deterministic simulator when `LLM_MOCK=true`, and both the unit suite and the e2e stack use it.

---

## 2. Setup

```bash
git clone <repo>
cd resume-tailoring-platform

cp .env.example .env          # for running the app; not needed for tests
make install                  # uv sync --locked --all-groups, then npm ci
make hooks                    # installs pre-commit, pre-push and commit-msg hooks
make check                    # confirm you start green
```

`make install` installs from the lockfiles. If `make install` fails because `uv.lock` has drifted
from `pyproject.toml`, that is the lockfile-drift gate working: whoever changed a dependency did
not commit the lock.

**If your home directory is read-only or sandboxed**, `make install` and `make check` fail with
`Operation not permitted` before any gate runs. uv caches in `~/.cache/uv` and npm in `~/.npm`.
Point both somewhere writable:

```bash
export UV_CACHE_DIR="$TMPDIR/uv-cache"
export npm_config_cache="$TMPDIR/npm-cache"
```

The Makefile deliberately does not set these for you. uv's cache is global on purpose: sharing it
across projects and hardlinking out of it into `.venv` is where its speed comes from, so a
project-local default would duplicate hundreds of megabytes and slow down everyone whose home
directory works fine. CI is unaffected, because `astral-sh/setup-uv` provisions its own cache on
the runner.

---

## 3. Running it

### The full stack, in Docker

```bash
docker compose up --build       # http://localhost:8000
```

This is the only configuration that matches production, because the frontend is a **static
export** baked into the image and served by FastAPI. See
[`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).

### Backend alone, with reload, no API key

```bash
cd backend
PYTHONPATH=src \
LLM_MOCK=true \
LOG_FORMAT=text \
DB_PATH=/tmp/resumetailor-dev.db \
PDFS_DIR=/tmp/resumetailor-pdfs \
uv run uvicorn resumetailor.main:app --reload --port 8000
```

`PYTHONPATH=src` is required. `resumetailor-backend` is a *virtual* project in `uv.lock`, so
`uv sync` installs the dependency tree but not this package. The Dockerfile sets the same
variable, and `[tool.pytest.ini_options] pythonpath` is how pytest gets it.

`LLM_MOCK=true` is not just convenience: without it, startup validation fails the boot when
`OPENAI_API_KEY` is empty.

`DB_PATH` and `PDFS_DIR` default to container-absolute paths (`/app/db/resumedb.db`, `/app/pdfs`)
and **must** be overridden for any host-local run.

### Frontend alone

```bash
cd frontend
npm run dev                      # http://localhost:3000
```

This gives you fast reload but **every `/api/*` call 404s**, because the client uses relative
paths and expects to be served same-origin by the backend. There is no dev proxy configured. To
see the frontend against a live API, build the export and let the backend serve it:

```bash
cd frontend && npm run build     # writes to frontend/out  (next.config.js: distDir: 'out')
cp -r out ../backend/static      # create_app mounts backend/static at /
```

Note the trap: `next.config.js` sets both `output: 'export'` and `distDir: 'out'`, so the export
lands in `out/` and not the default `.next/`. A `frontend/.next` directory on your disk is stale
build residue, not the thing being served.

---

## 4. The gates

`make check` is the gate. Run it before you call anything done. CI runs the same targets, so
local green means CI green.

```bash
make check       # lint + fmt-check + typecheck + test
```

| Target | What it runs |
|---|---|
| `make lint` | `ruff check` on the backend, `eslint` on the frontend |
| `make fmt` | Rewrites files in place: `ruff format`, `ruff check --fix`, `prettier --write` |
| `make fmt-check` | Fails if anything is unformatted. This is what CI runs |
| `make typecheck` | `mypy` on `backend/src/resumetailor`, `tsc --noEmit` on the frontend |
| `make test` | `pytest` with the coverage floor, `jest` |
| `make secrets` | `gitleaks` over tracked files and git history |
| `make help` | Lists everything |

Individual targets exist for every half (`make lint-backend`, `make test-frontend` and so on).
Use them while iterating; use `make check` before you report.

**`make secrets` is deliberately not part of `make check`.** gitleaks has to fetch and build its
hook environment on first use, and `check` must stay runnable offline. CI runs the scan on every
push and the pre-commit hook runs it on every commit, so nothing reaches a branch unscanned.

**The e2e suite is not part of `make check`** either, because it needs Docker. Run it explicitly:

```bash
./scripts/run_e2e.sh
```

That script brings up the isolated `resumetailor-e2e` compose project on port 18173 with tmpfs
storage and a mock LLM, runs Playwright inside the container, and tears everything down.
**Never point the e2e suite at port 8000.** Every spec's `beforeEach` issues destructive calls,
and 8000 is the dev stack holding real data and a live key. `test/playwright.config.ts` refuses
a loopback `BASE_URL` on 8000 outright, and refuses to default `BASE_URL` at all.

### The full gate list

This is [`AGENTS.md`](./AGENTS.md) §8, reproduced so you can see the target without leaving this
page. Two rows describe gates that do not exist yet; they are marked.

| Gate | Tool | Threshold |
|---|---|---|
| Python lint | `ruff check` | zero findings |
| Python format | `ruff format --check` | clean |
| Python types | `mypy --strict` | zero errors |
| Python tests | `pytest` | all pass, coverage floor enforced |
| TS lint | `eslint` | zero errors |
| TS types | `tsc --noEmit`, `strict: true` | zero errors |
| Frontend tests | `jest` | all pass |
| E2E | `playwright test` | all pass, hermetic, no live API key |
| Accessibility | `axe` on every route | zero serious or critical. **Not built yet, task 4.2** |
| Contract | OpenAPI against generated TS types | in sync. **Not built yet, task 2.2** |
| Secrets | `gitleaks` via `make secrets` | zero findings |

### About the exemptions in `backend/pyproject.toml`

The ruff, mypy and coverage configuration carries an explicit, itemised block of **legacy
exemptions**, scoped to the modules that predate the restructure: the top-level modules under
`src/resumetailor/` (`adapters.py`, `backend_api.py`, `database.py`, `deps.py`, `prompts.py`,
`simulator.py`, `yaml_utils.py`), `src/resumetailor/api/routers/*.py`, and `tests/**`. Two
things about it:

- **They are counted and owned.** Each line carries the number of findings it suppresses and the
  task that clears it (0.13 for lint and format, 0.14 for mypy). They exist because those modules
  are being split apart in tasks 1.2, 1.3 and 2.5, and reformatting code that is about to move is
  churn nobody can review.
- **Nothing new is exempt.** Any file you add is held to the full rule set, and the modules task
  1.1 wrote (`core/`) already are. Do not add entries to those lists; if a new file needs an
  exemption, the file is wrong.

The coverage floor is the **measured** level, not the aspirational one. It is set to fail on a
regression rather than on rounding. Raising it is a deliberate task, not something to do in
passing. Lowering it is not a fix.

---

## 5. Conventions

### Python

- `from __future__ import annotations` in every module.
- Absolute imports. Relative imports are banned by ruff (`flake8-tidy-imports`), with the
  existing `app/**` tree exempted until the src-layout move.
- Pydantic models for every request and response body. **No bare `dict` crossing a route
  boundary.** The current code violates this everywhere and that is exactly what task 2.2 fixes;
  do not add to it.
- Errors raise domain exceptions. Only the middleware translates them to HTTP.
- **Every synchronous SQLite call goes through `asyncio.to_thread`.** This is done consistently
  today and the suite depends on it. Do not add a blocking database call to an async handler.

### TypeScript

- `strict: true`. No `any`.
- Validate API responses at the boundary rather than trusting them.
- Server state belongs in TanStack Query; UI state in component state. (TanStack Query arrives in
  task 2.3; until then, existing components use `useState` plus `useEffect`.)
- One feature per folder, tests colocated.

### Testing

- Test behaviour, not implementation.
- **Every test runs without network and without an API key.** If a test needs either, it is
  wrong.
- **E2E selects on `data-testid` only, never on visible copy.** Product copy is not a selector.
  There is a source comment in `MasterResumePanel.tsx` instructing authors not to start a caption
  with the letter "s" because a text selector depends on it. That is the failure mode this rule
  prevents (D-27).
- Test order is shuffled by `pytest-randomly` on every run. A test that only passes in one order
  is a broken test, not a flaky one.

### Copy

- Everything user-visible follows [`docs/design/DESIGN-SYSTEM.md`](./docs/design/DESIGN-SYSTEM.md)
  §7.
- **No em-dash characters in any user-facing string.**

### Commits

Conventional commits, with the task id when the work belongs to a `PLAN.md` task:

```
feat(rendering): add subprocess timeout [1.3]
fix(api): return 204 consistently on delete [2.2]
docs: add architecture and deployment docs [1.6]
```

The commit-msg hook enforces the conventional prefix. Allowed types: `feat`, `fix`, `docs`,
`style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

---

## 6. Making a change

1. **Branch.** Never commit to `main` directly.
2. **Find or add the task in [`PLAN.md`](./PLAN.md).** If the work is not there, add it to the
   appropriate wave with an id rather than doing it silently.
3. **Write it, with tests.** New code has tests; changed behaviour has changed tests.
4. **`make check`.** Green, not "probably green".
5. **Update `PLAN.md` in the same change as the code:** tick your checkbox, and append one row to
   the §7 change log with the date, task id, role and a one-line summary. If reality diverged
   from the plan, edit the plan text so it describes what was actually built. A plan that
   documents an intention nobody followed is worse than no plan.
6. **If you discovered a defect you are not fixing**, register it rather than leaving a `TODO`. A
   `TODO` without a task id in `PLAN.md` fails the definition of done.
7. **Open a PR.** CI runs the same gates.

### When you need a file you do not own

Stop. Do not edit it. Report the blocker with the exact path and the exact change needed, and
append it to `PLAN.md` §6. Then continue with any unblocked part of your work.

---

## 7. Why the repository works this way

This codebase is being restructured by a team of agents working in parallel, and the process
shows up in the file layout, so it is worth one paragraph.

Work is organized into **waves**, which are barriers: nothing in wave N+1 starts until everything
in wave N is merged and green. Within a wave, tasks run in parallel, and **every task has an
exclusive file-ownership list** so two agents never hold write access to the same path at the
same time. That is why `PLAN.md` §4 reads as a list of tasks with owners rather than a backlog,
why anything that restructures directories runs in its own git worktree, and why an agent that
needs a file it does not own raises a blocker instead of editing it. `PLAN.md` is the one
deliberately shared file: everyone ticks their own box and appends their own change-log row, and
only the orchestrator restructures it. The full contract, including the role definitions and the
definition of done, is [`AGENTS.md`](./AGENTS.md).

As a human contributor the practical consequences are small: work in a branch, keep your diff
inside the area your change is about, check `PLAN.md` before starting so you are not duplicating
an in-flight task, and update it when you finish.

---

## 8. Decisions

Anything a future contributor would otherwise have to reverse-engineer is written down as an ADR
in [`docs/adr/`](./docs/adr/):

| ADR | Decision |
|---|---|
| [0001](./docs/adr/0001-ports-and-adapters.md) | Ports and adapters for the LLM, the renderer and the PDF extractor |
| [0002](./docs/adr/0002-numbered-sql-migrations.md) | Numbered SQL migrations with a `schema_version` table, not Alembic |
| [0003](./docs/adr/0003-sqlite.md) | SQLite, and what it costs |
| [0004](./docs/adr/0004-no-auth-loopback-only.md) | No authentication yet; loopback-only publishing as the interim |
| [0005](./docs/adr/0005-assistant-fixed-tool-set.md) | Assistant tool calling limited to a fixed four-tool action set |

If you make a decision at that level, add the next number. The format is short and fixed:
context, decision, consequences. The corresponding row in `PLAN.md` §5 links to it.

Historical planning documents from the original 2026-07 build are preserved under
[`docs/archive/planning/`](./docs/archive/planning/). They describe a system that has since
diverged. Read them for provenance, never as specification.
