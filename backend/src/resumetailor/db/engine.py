"""Connection lifecycle: one place that opens a connection, and closes it.

Every function that touched the database used to write::

    with sqlite3.connect(db_path) as conn:
        ...

which reads like a resource manager and is not one. ``sqlite3.Connection``'s
``__exit__`` commits or rolls back the transaction and then leaves the
connection, its file descriptor and its WAL handle open (D-13). Under the
``asyncio.to_thread`` executor that is a new leaked descriptor per request.

:func:`session` is the replacement: same commit-on-success, rollback-on-error
behaviour, plus the close.

The pragmas are set on every connection because SQLite scopes them per
connection, not per database -- with the single exception of ``journal_mode``,
which is persistent once set but costs nothing to reassert.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

# How long a writer waits for another writer's lock before raising
# "database is locked". Two concurrent generations used to collide instantly
# and surface as a generic GENERATION_FAILED (D-56).
BUSY_TIMEOUT_MS = 5_000

# Timestamps are written in this form everywhere: UTC, ISO-8601, second
# precision, explicit Z. Column defaults carry the same expression (migration
# 0004); this constant is for the UPDATE paths, where a default cannot apply.
# It is a SQL expression, not a format string -- SQLite computes it, so the
# process clock's timezone cannot leak into the value (D-09).
UTC_NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def connect(db_path: str, *, foreign_keys: bool = True) -> sqlite3.Connection:
    """Open a configured connection. The caller closes it; see :func:`session`.

    Args:
        db_path: path to the SQLite file.
        foreign_keys: enforce foreign keys. Only the migration runner passes
            ``False``, because rebuilding a table means dropping it while its
            children still reference it.
    """
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    # WAL lets one writer and many readers coexist; the default rollback
    # journal makes every reader wait behind the writer.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(
        "PRAGMA foreign_keys = ON" if foreign_keys else "PRAGMA foreign_keys = OFF"
    )
    return conn


@contextmanager
def session(db_path: str) -> Iterator[sqlite3.Connection]:
    """A connection that commits on success, rolls back on failure, and closes.

    Blocking. Every caller reaches it through ``asyncio.to_thread``.
    """
    conn = connect(db_path)
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()
