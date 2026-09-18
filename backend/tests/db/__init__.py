"""Tests for the persistence layer.

`raw` is here because these tests deliberately go around the repositories to
check what is actually on disk, and a test that leaks connections while
asserting that production code does not would be a poor advertisement.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def raw(db_path: str) -> Iterator[sqlite3.Connection]:
    """A plain connection, outside the repository layer, that closes itself."""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
