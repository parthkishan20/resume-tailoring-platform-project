"""Numbered SQL migrations, applied in order, exactly once (D-02, decision D3).

What this replaces: ``init_db`` ran ``backend/db/schema.sql`` -- a file of
``CREATE TABLE IF NOT EXISTS`` -- on every boot. Against a fresh database that
built the schema. Against an existing one it did nothing at all, silently, so
any schema change deployed cleanly, changed nothing, and turned into
``no such column`` on the next query. There was no way to tell the two cases
apart and no record anywhere of what shape a given database was in.

What replaces it: a ``schema_version`` table, and ``backend/migrations/NNNN_*.sql``
applied in numeric order. Each file runs inside one transaction together with
the row that records it, so a migration either applies and is recorded or does
neither. Applying twice is impossible; applying out of order is impossible;
and the version is a number anyone can read out of the database.

Alembic was the alternative (decision D3, ADR 0002). It is a large dependency
and a migration-authoring DSL for an application whose entire persistence layer
is raw ``sqlite3``. Numbered SQL is proportionate, and the repository boundary
in :mod:`resumetailor.db.repositories` is what makes swapping it later
mechanical.

Two pragmas matter while migrating and nowhere else:

* ``foreign_keys = OFF`` -- SQLite cannot add a constraint to an existing
  table, so 0002 through 0004 rebuild tables by copy-drop-rename. Dropping a
  table whose children still point at it needs the enforcement off.
* ``legacy_alter_table = ON`` -- without it, ``ALTER TABLE ... RENAME`` also
  rewrites references to that name inside other tables' definitions, which is
  the opposite of what the rebuild idiom wants.

Integrity is verified rather than assumed: every run ends with
``PRAGMA foreign_key_check`` and fails the boot if anything is dangling.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from resumetailor.core.config import BACKEND_ROOT
from resumetailor.core.errors import BackendError
from resumetailor.db.engine import connect

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = BACKEND_ROOT / "migrations"

_FILENAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
)
"""


class MigrationError(BackendError):
    """A migration could not be applied. Raised at startup, never per request.

    Lives here rather than in ``core.errors`` because it never becomes an HTTP
    response: a database this process cannot migrate is a boot failure.
    """

    code = "MIGRATION_FAILED"


def discover(migrations_dir: Path | None = None) -> list[tuple[int, Path]]:
    """Every migration on disk, as ``(version, path)``, lowest version first.

    Raises:
        MigrationError: if a ``.sql`` file is not named ``NNNN_name.sql``, or
            if two files claim the same version. Both mean the ordering is
            ambiguous, which is not something to guess at.
    """
    directory = migrations_dir or MIGRATIONS_DIR
    found: dict[int, Path] = {}
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME_RE.match(path.name)
        if match is None:
            msg = f"migration file is not named NNNN_name.sql: {path.name}"
            raise MigrationError(msg)
        version = int(match.group(1))
        if version in found:
            msg = (
                f"two migrations claim version {version}: "
                f"{found[version].name}, {path.name}"
            )
            raise MigrationError(msg)
        found[version] = path
    return sorted(found.items())


def current_version(db_path: str) -> int:
    """The highest applied migration version, or 0 for an unmigrated database."""
    conn = connect(db_path, foreign_keys=False)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone()
        if table is None:
            return 0
        return _max_version(conn)
    finally:
        conn.close()


def _max_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_version"
    ).fetchone()
    return int(row[0])


def _script(sql: str, version: int) -> str:
    """Wrap a migration and its version row in one transaction.

    ``version`` is an int parsed from the filename by ``_FILENAME_RE``, so the
    interpolation below cannot carry anything but digits. ``executescript``
    takes no parameters, which is why it is interpolated at all.
    """
    return (
        "BEGIN;\n"
        f"{sql}\n"
        f"INSERT INTO schema_version (version) VALUES ({version});\n"
        "COMMIT;\n"
    )


def migrate(db_path: str, migrations_dir: Path | None = None) -> list[int]:
    """Bring ``db_path`` up to the newest migration. Returns what it applied.

    Idempotent: a database already at the newest version is opened, checked and
    left alone. Blocking; callers reach it through ``asyncio.to_thread``.

    Raises:
        MigrationError: if a migration fails, if it does not record its own
            version, or if the result violates a foreign key.
    """
    pending: list[int] = []
    conn = connect(db_path, foreign_keys=False)
    try:
        conn.execute("PRAGMA legacy_alter_table = ON")
        conn.executescript(_SCHEMA_VERSION_DDL)
        applied = _max_version(conn)

        for version, path in discover(migrations_dir):
            if version <= applied:
                continue
            try:
                conn.executescript(_script(path.read_text(encoding="utf-8"), version))
            except Exception as exc:
                msg = f"migration {path.name} failed and was rolled back: {exc}"
                raise MigrationError(msg) from exc
            if _max_version(conn) != version:
                msg = f"migration {path.name} did not record version {version}"
                raise MigrationError(msg)
            pending.append(version)
            logger.info("migration applied", extra={"migration": path.name})

        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            msg = (
                f"schema is at version {_max_version(conn)} but "
                f"{len(violations)} row(s) violate a foreign key"
            )
            raise MigrationError(msg)
    finally:
        conn.close()

    logger.info(
        "database schema ready",
        extra={"schema_version": current_version(db_path), "applied": pending},
    )
    return pending
