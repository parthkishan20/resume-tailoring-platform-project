"""Connection lifecycle and pragmas."""

from __future__ import annotations

import sqlite3

import pytest

from resumetailor.db.engine import connect, session


def test_pragmas_are_set(tmp_path):
    conn = connect(str(tmp_path / "x.db"))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_foreign_keys_can_be_turned_off_for_migrations(tmp_path):
    conn = connect(str(tmp_path / "x.db"), foreign_keys=False)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    finally:
        conn.close()


def test_rows_are_addressable_by_column_name(tmp_path):
    with session(str(tmp_path / "x.db")) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('value')")
        assert conn.execute("SELECT a FROM t").fetchone()["a"] == "value"


def test_session_closes_the_connection(tmp_path):
    """D-13: `with sqlite3.connect(...)` commits and then leaks the descriptor."""
    with session(str(tmp_path / "x.db")) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT 1")


def test_session_commits_on_success(tmp_path):
    path = str(tmp_path / "x.db")
    with session(path) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('kept')")
    with session(path) as conn:
        assert conn.execute("SELECT a FROM t").fetchone()["a"] == "kept"


def test_session_rolls_back_and_still_closes_on_failure(tmp_path):
    path = str(tmp_path / "x.db")
    with session(path) as conn:
        conn.execute("CREATE TABLE t (a TEXT)")

    used: list[sqlite3.Connection] = []
    failure = RuntimeError("boom")

    def insert_then_fail() -> None:
        with session(path) as conn:
            used.append(conn)
            conn.execute("INSERT INTO t VALUES ('discarded')")
            raise failure

    with pytest.raises(RuntimeError, match="boom"):
        insert_then_fail()

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        used[0].execute("SELECT 1")
    with session(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
