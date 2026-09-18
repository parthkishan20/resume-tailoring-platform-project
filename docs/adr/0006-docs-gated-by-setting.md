# 0006. `/docs`, `/redoc` and `/openapi.json`: gated by a setting, on by default

- **Status:** Accepted
- **Date:** 2026-09-18
- **Addresses:** defect D-58 (task 3.5)

## Context

FastAPI serves `/docs` (Swagger UI), `/redoc` and `/openapi.json` unconditionally by default.
`docs/reports/audit-backend.md` (P2-9) flagged this as publicly served in every environment, and
D-58 asked whether that should stay true.

Two things narrow the decision:

- **The build tooling does not depend on the served route at all.** `frontend/package.json`'s
  `api:export` script runs `python -m resumetailor.api.openapi <path>`
  (`api/openapi.py::main`), which imports the application object directly and calls
  `render_openapi(app)` — it never makes an HTTP request. Gating the served `/openapi.json` has
  zero effect on `npm run api:generate` in CI or in a developer's shell, in either direction.
- **There is no authentication model yet** (ADR 0004, D4, open blocker B-03). Every route this
  application has is already invokable by anyone who can reach the published port; `/docs` adds a
  browsable index and a "Try it out" button over routes that were already callable, not a new
  capability. On the loopback-only interim (ADR 0004) the practical exposure is close to zero
  either way.

Given that, gating unconditionally would be solving a problem the deployment already mitigates
(loopback-only publishing), and leaving it permanently on would foreclose the choice once D4 lands
and an authenticated deployment target exists.

## Decision

**Add `Settings.API_DOCS_ENABLED: bool = True`.** When true (the default, preserving current
behaviour), `create_app` constructs `FastAPI()` with no override and all three routes are served as
before. When false, it passes `docs_url=None, redoc_url=None, openapi_url=None` to the constructor,
which removes all three from `app.routes` entirely — not a 404 handler standing in front of them,
an absence.

This is a lever, not a resolution: it exists so that disabling these routes for a deployment beyond
this machine is an environment variable, `API_DOCS_ENABLED=false`, rather than a code change made
under time pressure once the target is finally known.

## Consequences

- No behaviour change today: the default is `true`, matching what the application already does.
- `frontend/package.json`'s `api:export`/`api:generate` are unaffected regardless of this setting,
  for the reason given in Context — they never touch the network.
- The Docker `HEALTHCHECK` (`Dockerfile`, task 3.4's file) hits `/api/health`, not `/docs` or
  `/openapi.json`, so this setting does not interact with it.
- Revisit alongside D4/B-03: once a deployment target and an auth model exist, whether
  `API_DOCS_ENABLED` should default to `false` outside local development is part of that decision,
  not this one.
