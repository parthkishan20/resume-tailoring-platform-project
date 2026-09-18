# 0002. Numbered SQL migrations with a `schema_version` table, not Alembic

- **Status:** Accepted. Recorded from [`PLAN.md`](../../PLAN.md) §5 decision **D3**. The decision
  row there is still marked Open pending the orchestrator's update, while
  [`AGENTS.md`](../../AGENTS.md) §4 already sequences task 1.2 against this choice.
- **Date:** 2026-09-18
- **Implements:** defect D-02, a P0

## Context

There is no migration mechanism at all. `init_db` runs `backend/db/schema.sql` through
`executescript` on every boot, and every statement in that file is `CREATE TABLE IF NOT EXISTS`.

Against an existing database the entire script is a **no-op**. Adding a column to `schema.sql`
and deploying therefore looks like a clean deploy, changes nothing, and the next query that
references the new column raises `sqlite3.OperationalError: no such column`. There is no version
table, no `ALTER` path, no warning at startup, and no log line, because there is no logging
configuration either.

The existing test `test_init_db_is_idempotent` proves only that re-running an **unchanged** schema
is safe. It does not cover drift, which is the failure that actually occurs.

The persistence layer is raw `sqlite3`: 17 free functions, no ORM, no SQLAlchemy models. The two
realistic options are Alembic or a small hand-rolled runner.

## Decision

**Numbered `.sql` files plus a `schema_version` table, applied in order at startup.**

- Migrations live in `backend/migrations/`, named `NNNN_description.sql`, applied in lexical
  order.
- `0001_initial.sql` reproduces today's schema **exactly**, so an existing database converges on
  the same state as a fresh one.
- A `schema_version` table records which migrations have been applied. Each runs inside a
  transaction.
- A backup is taken automatically before the first migration of any run.
- CI gates it: apply `0001` to an empty database, then apply every later migration to a
  **populated** database and assert the data survives. That is the test that would have caught
  D-02.

Alembic is rejected. It is built around SQLAlchemy metadata and autogenerate, neither of which
exists here, so adopting it means adopting an ORM or hand-writing every `op.*` call anyway, at
which point it is a heavier way to write the same SQL.

## Consequences

- The P0 goes away: a schema change either applies or fails loudly at startup, never silently.
- The migration files are plain SQL, which is the same language the schema is already written in.
  No new abstraction to learn.
- SQLite's `ALTER TABLE` is limited, so several of the fixes already queued require the
  dedupe-then-rebuild pattern rather than a one-line alter. Adding `UNIQUE(user_id)` to
  `master_resume` and `system_prompt` (D-06) is exactly that: create the new table, copy the
  surviving row, drop, rename. Writing those by hand is more work than Alembic's batch mode would
  have been, and it is work that has to be correct.
- Migrations are forward-only. There is no `downgrade`. Recovery is restore-from-backup, which is
  why the automatic pre-migration backup is part of this decision rather than a separate one.
- `backend/db/schema.sql` stops being the source of truth and becomes a derived artifact, or is
  deleted. Two places describing the schema is how drift starts.
- **The swap is cheap if this turns out to be wrong.** The repository boundary landing in the
  same task means the migration runner is called from exactly one place. Moving to Alembic later
  is mechanical: the existing numbered files become the initial revision.

## References

- [`ARCHITECTURE.md`](../ARCHITECTURE.md) §9 for the current schema and its defects
- [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md) §3 for what the failure looks like today
- `reports/audit-data-pipeline.md` P0 #1 for the original finding
