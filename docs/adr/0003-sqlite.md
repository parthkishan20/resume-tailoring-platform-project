# 0003. SQLite as the datastore, and what it costs

- **Status:** Accepted. Inherited from the original 2026-07 build and reaffirmed by
  [`PLAN.md`](../../PLAN.md) §1, whose explicit non-goals include multi-tenancy beyond the
  existing single-user model and a hosted offering.
- **Date:** 2026-09-18 (records a decision taken during the original build)
- **Original rationale:** preserved in
  [`../archive/planning/PLAN.md`](../archive/planning/PLAN.md), which recorded it as "SQLite over
  Postgres: no auth means no multi-user, which means no need for a database server;
  self-contained, zero config"

## Context

ResumeTailor is a single-user workstation that runs as one container on one machine. There is one
master resume, a handful of generated resumes, a chat transcript and a dozen configuration rows.
The whole dataset is small enough to fit in memory.

The alternative is a database server, which means a second container, a connection string, a
health dependency, credentials to manage, and a backup story that involves `pg_dump` rather than
copying a file.

## Decision

**SQLite, one file, on a Docker named volume.** Raw `sqlite3` from the standard library, no ORM.
Every synchronous call is wrapped in `asyncio.to_thread` so it does not block the event loop.

## Consequences

**What this bought.** The quick start really is three commands. There is no second service to
run, nothing to provision, no credential to rotate, and the entire application state is two
directories. For a single-user tool that is the right trade and it is not being revisited.

**What it costs, and every one of these is a live defect today:**

- **Writers block readers, and the app does long writes.** With no WAL journal mode and no
  `busy_timeout` tuning, two concurrent generations raise `database is locked`, which the route's
  catch-all flattens to a generic `GENERATION_FAILED` (D-56). See
  [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md) §1.
- **Worker count is pinned at one.** `--workers 1` in the Dockerfile is a direct consequence of
  the point above. That in turn makes every blocking-on-the-event-loop defect a whole-service
  stall rather than a per-worker one, most visibly the ~5 second first-render freeze (D-05).
- **No horizontal scale.** The volume is not shareable across hosts. More than one replica is not
  a configuration change; it is a different datastore.
- **`sqlite3.connect` used as a context manager never closes the connection.** The stdlib's
  `__exit__` commits or rolls back; it does not close. All 17 database functions leak the
  connection to the garbage collector, and with it the WAL and shm handles (D-13).
- **The schema shipped without indexes, foreign keys or the `foreign_keys` pragma.** History rows
  orphan on delete and `list_resumes` full-scans and sorts (D-14). None of that is inherent to
  SQLite; it is what happens when a file-based database makes schema discipline feel optional.
- **Backups are a copy, which is easy and therefore was never written.** There is no backup
  mechanism and no restore procedure, so a single `docker compose down -v` is total unrecoverable
  loss (D-03, a P0). A live SQLite file must be copied with the online backup API rather than
  `cp`, or the copy can be torn. See [`DEPLOYMENT.md`](../DEPLOYMENT.md) §5.

**What is being fixed rather than reconsidered.** Task 1.2 enables WAL, sets `busy_timeout` and
`foreign_keys`, adds indexes and foreign keys with `ON DELETE CASCADE`, closes connections
properly, moves to ISO-8601 timestamps, and writes backup and restore scripts. Those close the
costs that are avoidable. The two that are inherent, single-writer concurrency and no horizontal
scale, stay, and they are acceptable for the stated scope.

**When to revisit.** If the product ever grows real multi-tenancy, the datastore choice is the
first thing to reopen, not the last. The data layer is already parameterized by `user_id`, so the
schema is not the obstacle; the obstacle would be concurrency. Note that the filesystem layout is
*not* forward-compatible either: PDFs are written flat as `{PDFS_DIR}/{resume_id}.pdf` with no
`user_id` in the path. See [`ARCHITECTURE.md`](../ARCHITECTURE.md) §10.

**A constraint worth recording alongside this one**, because it is the other reason the container
stays small and self-contained: RenderCV 2.x compiles with **Typst, not LaTeX**, shipped as a pip
wheel by `rendercv[full]`. There is no `apt-get` layer and no TeX Live anywhere in the image. A
naive "just add texlive-full" would add roughly 4 GB to a ~430 MB image. Do not regress it.
