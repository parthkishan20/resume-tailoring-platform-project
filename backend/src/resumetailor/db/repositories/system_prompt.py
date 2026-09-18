"""The system prompt placed in front of every assistant turn."""

from __future__ import annotations

import sqlite3

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session
from resumetailor.db.models import SystemPrompt
from resumetailor.db.seed import DEFAULT_SYSTEM_PROMPT

_SELECT = "SELECT id, user_id, content, updated_at FROM system_prompt WHERE user_id = ?"


def _to_model(row: sqlite3.Row) -> SystemPrompt:
    return SystemPrompt(
        id=row["id"],
        user_id=row["user_id"],
        content=row["content"],
        updated_at=row["updated_at"],
    )


def get_system_prompt(
    db_path: str, user_id: str = DEFAULT_USER_ID
) -> SystemPrompt | None:
    with session(db_path) as conn:
        row = conn.execute(_SELECT, (user_id,)).fetchone()
        return _to_model(row) if row else None


def upsert_system_prompt(
    db_path: str, content: str, user_id: str = DEFAULT_USER_ID
) -> SystemPrompt:
    """Save the prompt.

    One ``ON CONFLICT`` upsert against ``UNIQUE(user_id)`` (migration 0002),
    replacing a read-then-write that could leave two rows behind and make the
    prompt appear to revert at random (D-06).
    """
    with session(db_path) as conn:
        conn.execute(
            "INSERT INTO system_prompt (user_id, content) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  content = excluded.content, "
            "  updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
            (user_id, content),
        )
        return _to_model(conn.execute(_SELECT, (user_id,)).fetchone())


def reset_system_prompt(db_path: str, user_id: str = DEFAULT_USER_ID) -> SystemPrompt:
    """Put the shipped default back."""
    return upsert_system_prompt(db_path, DEFAULT_SYSTEM_PROMPT, user_id)
