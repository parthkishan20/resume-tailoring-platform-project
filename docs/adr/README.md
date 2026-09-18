# Architecture decision records

Short, dated records of the choices a future contributor would otherwise have to
reverse-engineer from the code. One decision per file, numbered, never edited after acceptance:
a decision that changes gets a **new** ADR that supersedes the old one, and the old one is marked
superseded rather than rewritten.

Format is fixed and deliberately small: **context, decision, consequences**, plus a status line.

| # | Title | Status |
|---|---|---|
| [0001](./0001-ports-and-adapters.md) | Ports and adapters for the LLM, the renderer and the PDF extractor | Accepted |
| [0002](./0002-numbered-sql-migrations.md) | Numbered SQL migrations with a `schema_version` table, not Alembic | Accepted |
| [0003](./0003-sqlite.md) | SQLite as the datastore, and what it costs | Accepted |
| [0004](./0004-no-auth-loopback-only.md) | No authentication yet; loopback-only publishing as the interim | Accepted as interim |
| [0005](./0005-assistant-fixed-tool-set.md) | Assistant tool calling limited to a fixed four-tool action set | Accepted |

Each of these corresponds to a row in [`PLAN.md`](../../PLAN.md) §5 or to a property
[`PLAN.md`](../../PLAN.md) §2 records as deliberately kept. Adding a decision at this level means
adding the next number here and linking it from the decision row.
