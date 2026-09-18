# AGENTS.md — Agent Orchestration Contract

> How autonomous agents work on ResumeTailor. Read this **before** starting any task.
> Companion documents: [`PLAN.md`](./PLAN.md) (what to build, in what order),
> [`docs/design/DESIGN-SYSTEM.md`](./docs/design/DESIGN-SYSTEM.md) (how the UI must look and behave).
>
> Last updated: 2026-09-18

---

## 1. The three standing rules

**Rule 1 — The plan is the source of truth.**
Every agent updates `PLAN.md` when its work changes reality. Not at the end of the wave. Not in a
summary message. In the file, in the same change as the code. An agent that ships code without
updating the plan has not finished.

**Rule 2 — Own your files, touch nothing else.**
Every task in `PLAN.md` carries an explicit file-ownership list. Two agents never hold write access to
the same path in the same wave. If your task genuinely needs a file you do not own, you stop and
report it as a blocker rather than editing it.

**Rule 3 — Green before done.**
`make check` passes locally before an agent reports a task complete. "It probably works" is not a
status. If a gate fails for a reason outside your ownership, say so explicitly and name the file.

---

## 2. Roles

Each role below is a persistent agent identity with a fixed remit and a fixed file boundary. Roles
are reused across waves so context accumulates rather than being rebuilt.

| Role | Remit | Owns |
|---|---|---|
| `orchestrator` | Wave sequencing, blocker resolution, merge order, plan integrity. Writes no production code. | `AGENTS.md`; `PLAN.md` structure (see the note below) |
| `platform` | Repo hygiene, tooling, Makefile, pre-commit, CI workflows, Docker, compose | `Makefile`, `.github/`, `Dockerfile*`, `docker-compose*.yml`, `.dockerignore`, `.gitignore`, `scripts/` |
| `backend-core` | FastAPI application layer: routing, schemas, middleware, error envelope, settings, DI | `backend/src/resumetailor/api/`, `.../core/` |
| `backend-domain` | Business logic: tailoring pipeline, evaluation, rules, prompt assembly | `backend/src/resumetailor/domain/`, `.../services/` |
| `data` | Persistence: models, repositories, migrations, schema ownership, backup/restore | `backend/src/resumetailor/db/`, `backend/migrations/` |
| `rendering` | RenderCV pipeline, YAML normalization and validation, PDF lifecycle, subprocess safety | `backend/src/resumetailor/rendering/`, `backend/rendercv_config/` |
| `llm` | Provider adapters, streaming, retries, timeouts, token accounting, the deterministic stub | `backend/src/resumetailor/llm/` |
| `design-system` | Tokens, primitives, theming, fonts, icons, Tailwind config | `frontend/src/design-system/`, `frontend/tailwind.config.*`, `frontend/src/app/globals.css` |
| `frontend-shell` | App shell, navigation, document region, inspector, routing, global state | `frontend/src/app/`, `frontend/src/features/workspace/` |
| `frontend-features` | Tailor, Evaluate, Assistant, Library feature modules | `frontend/src/features/{tailor,evaluate,assistant,library}/` |
| `api-contract` | OpenAPI export, generated TS types, runtime response validation, the typed client | `frontend/src/lib/api/`, `backend/src/resumetailor/api/openapi.py` |
| `qa-unit` | Backend and frontend unit/integration tests, fixtures, deterministic stubs | `backend/tests/`, `frontend/src/**/*.test.tsx` |
| `qa-e2e` | Playwright suite, hermetic harness, test data, visual and a11y regression | `tests/e2e/`, `tests/fixtures/` |
| `security` | Auth, authz, rate limiting, input limits, CORS, secret handling, dependency audit | cross-cutting, review-only except `.../core/security.py` |
| `docs` | Architecture, API reference, deployment, runbooks, ADRs, README | `docs/`, `README.md`, `CONTRIBUTING.md` |
| `reviewer` | Adversarial review of every merged wave. Ships no code. | nothing |

> **`PLAN.md` is the one shared file, by design.** Rule 1 requires every agent to update it, and the
> ownership rule would otherwise forbid that. The reconciliation: an agent may only *tick its own
> checkbox*, *append* a row to §7 Change log, and *append* to §6 Open blockers. Restructuring sections,
> renumbering defects, and editing anything outside those three places is the orchestrator's alone.
> Appends can collide when several agents finish at once; on a conflict, re-read the file and re-apply
> your one line rather than overwriting.

---

## 3. Task contract

Every task handed to an agent uses this shape. An agent that receives a task missing any field asks
for it rather than guessing.

```markdown
## TASK <wave>.<id> — <title>
**Role:** <role from section 2>
**Wave:** <n>          **Depends on:** <task ids, or "none">
**Isolation:** <shared worktree | dedicated worktree>

### Objective
One paragraph. What is true after this task that is not true now.

### Owns (exclusive write access)
- path/one
- path/two

### Reads (no write access)
- path/three

### Acceptance criteria
- [ ] Testable statement
- [ ] Testable statement
- [ ] `make check` passes
- [ ] PLAN.md updated: task marked done, deviations recorded

### Deliverable artifacts
- Code at the owned paths
- Report at `docs/reports/<wave>-<id>.md` when the task produces findings others need

### Out of scope
Explicit list. Anything not named here and not in Owns is out of scope by default.
```

---

## 4. Wave plan

Waves are barriers. No agent in wave N+1 starts until every task in wave N is merged and `make check`
is green on the integration branch. Within a wave, every task runs in parallel.

### Wave 0 — Stop the bleeding, then build the gates

**The authoritative task list is `PLAN.md` §4.** This table is the shape of the wave; the numbered
tasks, their current state, and anything discovered mid-wave live there and only there.

Wave 0 runs in two parts. **0.A** is emergency P0 triage: seven findings that are both actively
harmful and cheap, fixed as small isolated changes before any restructuring begins. It is not
defensible to spend a week on architecture while a `DELETE` silently corrupts the UI's view of the
database and running the documented test command can wipe the user's real resume. **0.B** builds the
gates that every later wave is measured against.

| Part | Roles | Summary |
|---|---|---|
| 0.A | `platform`, `frontend-shell`, `qa-e2e` | PII exposure, the 204 delete bug, the destructive-onboarding path, editor dirty-state, e2e/dev stack isolation, the three Docker build P0s, keyboard PDF import |
| 0.B | `platform`, `qa-unit` | Repo hygiene, ruff/mypy/eslint/prettier/pre-commit, `Makefile check`, CI, test-ordering isolation |

Unlike later waves, 0.A parallelises across agents rather than running serially, because its tasks
touch disjoint files. File ownership is still exclusive; see `PLAN.md` §4 for the split.

### Wave 1 — Foundations (6 parallel)
Every track here is independent. This is the widest fan-out in the project.

| Task | Role | Summary | Isolation |
|---|---|---|---|
| 1.1 | `backend-core` | Restructure to `backend/src/resumetailor/`; settings, logging, request IDs, error envelope, middleware | dedicated worktree |
| 1.2 | `data` | Numbered SQL migrations with a `schema_version` table (not Alembic, per decision D3), repository layer, schema as single source, `UNIQUE` constraints, WAL, indexes and FKs, backup and restore | dedicated worktree |
| 1.3 | `rendering` | Isolate the RenderCV service: subprocess timeout, concurrency cap, `to_thread`, canonical YAML schema | dedicated worktree |
| 1.4 | `design-system` | The approved Letterpress system: tokens, Tailwind v4, Geist, Phosphor, primitives, both themes. `docs/design/DESIGN-SYSTEM.md` is binding, including its §7 pre-flight checklist | dedicated worktree |
| 1.5 | `qa-unit` | Hermetic test harness: ephemeral DB per test, deterministic LLM stub, dynamic ports | shared |
| 1.6 | `docs` | `ARCHITECTURE.md`, `DEPLOYMENT.md`, `CONTRIBUTING.md`, ADR 0001-0005; archive stale planning docs | shared |

**Integration point I1.** `orchestrator` merges 1.1 → 1.2 → 1.3 (backend order matters), then 1.4,
1.5, 1.6 in any order. Runs full `make check`. Blocks wave 2 on green.

### Wave 2 — Product surfaces (5 parallel)

| Task | Role | Summary | Depends on |
|---|---|---|---|
| 2.1 | `llm` | Provider abstraction, timeouts, retry with backoff, streaming lifecycle, token accounting | 1.1 |
| 2.2 | `api-contract` | OpenAPI export, generated TS types, zod validation, typed client with abort handling | 1.1 |
| 2.3 | `frontend-shell` | New IA: nav, document region, inspector; theme toggle; TanStack Query | 1.4 |
| 2.4 | `security` | Auth, rate limiting, upload limits, CORS, secret handling | 1.1, 1.2 |
| 2.5 | `backend-domain` | Tailoring and evaluation pipelines extracted from route handlers into services | 1.1, 1.3 |

**Integration point I2.**

### Wave 3 — Features and hardening (5 parallel)

| Task | Role | Summary | Depends on |
|---|---|---|---|
| 3.1 | `frontend-features` | Tailor + Evaluate on shared JD state | 2.2, 2.3 |
| 3.2 | `frontend-features` | Assistant tab and Library | 2.2, 2.3 |
| 3.3 | `backend-core` | Observability: structured logs, metrics, health/readiness split, graceful shutdown | 2.1 |
| 3.4 | `platform` | Multi-stage Docker, compose profiles, volume/backup strategy, release workflow | 1.1, 2.4 |
| 3.5 | `qa-unit` | Coverage to target on every module touched in waves 1-2 | all of wave 2 |

**Integration point I3.**

### Wave 4 — Verification (4 parallel, no feature work)

| Task | Role | Summary |
|---|---|---|
| 4.1 | `qa-e2e` | Rebuild the e2e suite against the new UI, hermetic, `data-testid` only |
| 4.2 | `qa-e2e` | Accessibility regression (axe) and visual regression baselines |
| 4.3 | `security` | Full security review of the diff since `main` |
| 4.4 | `reviewer` | Adversarial review of every wave; findings ranked, verified before reporting |

**Release gate.** Every wave-4 finding is triaged. P0 and P1 fixed. P2 recorded in `PLAN.md` as
accepted debt with a reason.

---

## 5. Parallelism and isolation

**Worktrees.** Any task that restructures directories runs in a dedicated git worktree so a
half-finished move never breaks a sibling agent. Tasks that only add files run in the shared tree.

**Sandbox note for this project (2026-09-18):** the orchestrating session's sandbox denies writes to
`.claude/commands/agents/` and to `.git/config`, even under the repo root's normal write allowance.
Plain `git worktree add` therefore fails checking out `.claude/`, and `git sparse-checkout init` fails
because it needs to set `extensions.worktreeConfig` in the shared `.git/config`. Working pattern:

```bash
mkdir -p .worktrees   # gitignored
git worktree add -q --no-checkout .worktrees/<name> -b wave<N>/<name> <base-branch>
git -C .worktrees/<name> checkout -q wave<N>/<name> -- . ':!.claude'
```

This checks out everything except `.claude/`, touches no shared git config, and each agent's own tool
permissions inside its worktree are unaffected — only the orchestrating session's sandbox is stricter
about that specific path. `.worktrees/` is gitignored; remove finished worktrees with
`git worktree remove --force .worktrees/<name>` before deleting the directory.

**Merge order within a wave** is declared at the integration point, not negotiated by agents. Backend
structural changes land before anything that imports them.

**Conflict protocol.** An agent that finds it needs a file it does not own:
1. Stops. Does not edit.
2. Writes the need to `docs/reports/<wave>-<id>.md` under `## Blockers`.
3. Reports the blocker to the orchestrator with the exact path and the exact change needed.
4. Continues with any unblocked part of its task.

**Concurrency ceiling.** Six concurrent agents per wave. Beyond that, integration cost exceeds the
parallelism win on a codebase this size, and review quality drops.

---

## 6. Plan update protocol

This implements Rule 1. Every agent does this, every time.

On **task completion**, in the same change as the code:
1. Flip the task's checkbox in `PLAN.md`.
2. Append a line to the `## Change log` table: date, task id, role, one-line summary.
3. If reality diverged from the plan, edit the plan text itself so it describes what was actually
   built. A plan that documents an intention nobody followed is worse than no plan.
4. If the task revealed new work, add it to the appropriate wave as a new task with an id, rather
   than doing it silently.

On **blocker**: add the blocker to `## Open blockers` in `PLAN.md` with task id, path, and what is
needed to unblock.

On **decision**: any choice that future contributors would otherwise have to reverse-engineer becomes
an ADR at `docs/adr/NNNN-title.md`, and the decision row in `PLAN.md` links to it.

---

## 7. Definition of done

A task is done when **all** of these hold. There is no partial credit.

- [ ] Acceptance criteria all met
- [ ] Only owned files modified (`git diff --name-only` verified against the Owns list)
- [ ] `make check` green: ruff, mypy, eslint, tsc, pytest, jest
- [ ] New code has tests; changed behaviour has changed tests
- [ ] No new `TODO` without a task id in `PLAN.md`
- [ ] No secrets, keys, or tokens in the diff
- [ ] Public functions and modules documented where intent is not obvious from the name
- [ ] `PLAN.md` updated per section 6
- [ ] Report written to `docs/reports/` if the task produced findings

---

## 8. Quality gates

`make check` runs all of these except the one noted below. CI runs the same targets, so local green
means CI green. A sandboxed or read-only home directory needs `UV_CACHE_DIR` and `npm_config_cache`
exported; uv's cache is global by design and the Makefile deliberately does not override it.

| Gate | Tool | Threshold |
|---|---|---|
| Python lint | `ruff check` | zero findings |
| Python format | `ruff format --check` | clean |
| Python types | `mypy --strict` on `backend/src/` | zero errors |
| Python tests | `pytest` | all pass, coverage ≥ 85% on `domain/`, `services/`, `db/` |
| TS lint | `eslint` | zero errors |
| TS types | `tsc --noEmit` with `strict: true` | zero errors |
| Frontend tests | `jest` | all pass |
| E2E | `playwright test` | all pass, hermetic, no live API key |
| Accessibility | `axe` on every route | zero serious or critical |
| Contract | OpenAPI ↔ generated TS types | in sync, checked in CI |
| Secrets | `gitleaks` via `make secrets` | zero findings. **Deliberately not part of `make check`**, so `check` stays runnable offline: pre-commit has to fetch and build the gitleaks hook environment on first use. It runs in CI on every push and in the pre-commit hook on every commit, so nothing reaches a branch unscanned. |

---

## 9. Conventions

**Python.** `from __future__ import annotations` in every module. Absolute imports from
`resumetailor.*`. Pydantic models for every request and response body; no bare `dict` crossing a
route boundary. Errors raise domain exceptions; only the middleware translates them to HTTP.

**TypeScript.** `strict: true`. No `any`. API responses validated at the boundary, not trusted.
Server state in TanStack Query; UI state in component state. One feature per folder, colocated tests.

**Testing.** Test behaviour, not implementation. Every test runs without network and without an API
key. E2E selects on `data-testid` only, never on visible copy.

**Commits.** Conventional commits with the task id: `feat(rendering): add subprocess timeout [1.3]`.

**Copy.** Everything user-visible follows `docs/design/DESIGN-SYSTEM.md` section 7. No em-dash
characters in any user-facing string.

---

## 10. Escalation

An agent stops and asks rather than guessing when:

- The change would alter an API contract another wave depends on
- The change would drop or transform user data
- The task as written conflicts with `PLAN.md` or the design system
- A dependency needs to be added that is not already in the plan
- Two acceptance criteria cannot both be satisfied

Everything else is a judgment call the agent makes and records.
