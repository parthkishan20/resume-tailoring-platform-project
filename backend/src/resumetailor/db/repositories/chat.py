"""The assistant transcript."""

from __future__ import annotations

import sqlite3

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session
from resumetailor.db.models import ChatMessage

_ALL = (
    "SELECT id, user_id, role, content, created_at FROM chat_messages "
    "WHERE user_id = ? ORDER BY id ASC"
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


def _to_model(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        user_id=row["user_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
    )


def get_chat_messages(
    db_path: str, user_id: str = DEFAULT_USER_ID, limit: int | None = None
) -> list[ChatMessage]:
    """The transcript, oldest first.

    Args:
        limit: return only the most recent ``limit`` messages. ``None`` returns
            the whole transcript, which is what ``GET /api/chat`` still asks
            for.
    """
    with session(db_path) as conn:
        if limit is None:
            rows = conn.execute(_ALL, (user_id,)).fetchall()
        else:
            rows = conn.execute(_RECENT, (user_id, max(limit, 1))).fetchall()
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
