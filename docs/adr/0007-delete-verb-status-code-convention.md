# 0007. `DELETE`: 204 for a true delete, 200 with a body for a reset

- **Status:** Accepted
- **Date:** 2026-09-18
- **Addresses:** defect D-58 (task 3.5)

## Context

Five routes use the `DELETE` verb. Three remove a row (or every row) outright:
`DELETE /api/master-resume`, `DELETE /api/resumes/{id}`, `DELETE /api/chat`. Two restore a
singleton row to its seeded default: `DELETE /api/rules`, `DELETE /api/system-prompt` — the row
still exists afterwards, with new values, because `generation_rules` and `system_prompt` are
rows the application always expects to find one of, not rows that can be absent.

D-58 named this "inconsistent DELETE semantics: three routes return 204, two return 200 with a
body." Read as a bug, the fix would be forcing all five to 204. Read as a naming problem — the
status codes were already, accidentally, doing the right thing — the fix is deciding and writing
down which shape each *kind* of `DELETE` gets, so the split is a stated convention the next route
follows on purpose rather than a pattern a future PR "fixes" into uniformity.

## Decision

**Two request shapes exist under one HTTP verb, and each gets its own status code:**

- **A true delete** — the resource does not exist afterwards — answers **204 No Content**. There
  is nothing to describe in the body, because there is nothing left.
- **A reset-to-default** — the resource still exists afterwards, with a new value — answers
  **200 OK** with the resulting resource in the body, exactly like a `PUT`. The caller needs the
  new state (what are the default rules now?) and a `DELETE`-shaped request for a "reset" action
  is intentional REST pragmatism here: it reads better at the call site than inventing a sixth verb
  or a `POST /api/rules:reset`-style RPC path for something this small, and the frontend already
  depends on both routes' current paths and methods.

No endpoint's path, verb or status code changes as a result of this ADR — task 2.4/frontend
already built the client against this exact split (see `PLAN.md`'s 0.1 change log entry: "API
client returns early on 204 and on any empty body"). What changes is that each of the five routes
now says which kind it is, in its own docstring, rather than the split being an artifact nobody
could point to.

## Consequences

- `rules.py::reset` and `system_prompt.py::reset` are documented as resets, not deletes, at the
  route.
- `master_resume.py::remove_resume`, `resumes.py::delete_generated` and `chat.py::clear_history`
  are documented as true deletes.
- A future `DELETE` route picks one of these two shapes deliberately, instead of copying whichever
  neighbour happens to be nearest in the file.
- This ADR does not touch `api/openapi.py` (owned by the `api-contract` role): the documented
  status codes were already correct in the generated schema before this task, since FastAPI reads
  them off each route's `status_code=`/response model. Only the prose explaining *why* was
  missing, and prose lives at the route, not in the OpenAPI builder.
