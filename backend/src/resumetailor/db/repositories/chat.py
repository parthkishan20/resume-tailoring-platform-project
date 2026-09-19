"""The assistant transcript."""

from __future__ import annotations

import sqlite3

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session
from resumetailor.db.models import ChatMessage

#: The largest page this repository will ever return, whatever it is asked
#: for. Mirrors `resumes.py`'s `MAX_PAGE_SIZE` (D-10): clamping here means no
#: caller, present or future, can turn a bad `limit` into an unbounded read.
MAX_PAGE_SIZE = 100

_ALL = (
    "SELECT id, user_id, role, content, created_at FROM chat_messages "
    "WHERE user_id = ? ORDER BY id ASC"
)

# Everything older than `before_id`, oldest first. The unbounded half of
# backward paging: `before_id` with no `limit`.
_ALL_BEFORE = (
    "SELECT id, user_id, role, content, created_at FROM chat_messages "
    "WHERE user_id = ? AND id < ? ORDER BY id ASC"
)

# The newest `limit` messages, handed back oldest-first so the caller sees a
# transcript in reading order. The chat route used to fetch every message ever
# sent and then slice the last thirty in Python (D-21); the inner query is that
# slice, done where the index is.
_RECENT = (
    "SELECT id, user_id, role, content, created_at FROM ("
    "  SELECT id, user_id, role, content, created_at FROM chat_messages"
    "   WHERE user_id = ? ORDER BY id DESC LIMIT ?"
    ") ORDER BY id ASC"
)

# The `limit` messages immediately before `before_id`, oldest first. This is
# what `GET /api/chat`'s "Load earlier" cursor runs: the page before the page
# the caller already has (B-07).
_RECENT_BEFORE = (
    "SELECT id, user_id, role, content, created_at FROM ("
    "  SELECT id, user_id, role, content, created_at FROM chat_messages"
    "   WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT ?"
    ") ORDER BY id ASC"
)


def _to_model(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        user_id=row["user_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
    )


def get_chat_messages(
    db_path: str,
    user_id: str = DEFAULT_USER_ID,
    limit: int | None = None,
    before_id: int | None = None,
) -> list[ChatMessage]:
    """The transcript, oldest first.

    Args:
        limit: return only the most recent ``limit`` messages (or the most
            recent ``limit`` before ``before_id``, if given). Clamped to
            1..:data:`MAX_PAGE_SIZE`. ``None`` returns everything that
            matches, which is what ``GET /api/chat`` still does when no query
            parameters are passed (B-07).
        before_id: page backward. Only messages with ``id < before_id`` are
            considered, so passing the oldest id already held fetches the
            page before it.
    """
    clamped_limit = min(max(limit, 1), MAX_PAGE_SIZE) if limit is not None else None
    with session(db_path) as conn:
        if before_id is None and clamped_limit is None:
            rows = conn.execute(_ALL, (user_id,)).fetchall()
        elif before_id is None:
            rows = conn.execute(_RECENT, (user_id, clamped_limit)).fetchall()
        elif clamped_limit is None:
            rows = conn.execute(_ALL_BEFORE, (user_id, before_id)).fetchall()
        else:
            rows = conn.execute(
                _RECENT_BEFORE, (user_id, before_id, clamped_limit)
            ).fetchall()
        return [_to_model(row) for row in rows]


def add_chat_message(
    db_path: str, role: str, content: str, user_id: str = DEFAULT_USER_ID
) -> ChatMessage:
    with session(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        row = conn.execute(
            "SELECT id, user_id, role, content, created_at FROM chat_messages "
            "WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return _to_model(row)


def clear_chat(db_path: str, user_id: str = DEFAULT_USER_ID) -> None:
    with session(db_path) as conn:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
