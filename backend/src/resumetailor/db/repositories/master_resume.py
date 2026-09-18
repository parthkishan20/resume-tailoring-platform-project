"""The master resume and its version history."""

from __future__ import annotations

import sqlite3

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session
from resumetailor.db.models import MasterResume

#: Superseded versions kept per user. The eleventh push drops the oldest.
HISTORY_LIMIT = 10

_SELECT = (
    "SELECT id, user_id, yaml_content, updated_at FROM master_resume WHERE user_id = ?"
)


def _to_model(row: sqlite3.Row) -> MasterResume:
    return MasterResume(
        id=row["id"],
        user_id=row["user_id"],
        yaml_content=row["yaml_content"],
        updated_at=row["updated_at"],
    )


def get_master_resume(
    db_path: str, user_id: str = DEFAULT_USER_ID
) -> MasterResume | None:
    """The user's master resume, or None if they have not saved one."""
    with session(db_path) as conn:
        row = conn.execute(_SELECT, (user_id,)).fetchone()
        return _to_model(row) if row else None


def upsert_master_resume(
    db_path: str, yaml_content: str, user_id: str = DEFAULT_USER_ID
) -> MasterResume:
    """Save the master resume, pushing the previous content into history.

    The write is a single ``ON CONFLICT`` upsert against ``UNIQUE(user_id)``
    (migration 0002), so two concurrent saves can no longer each insert a row
    and leave reads returning an arbitrary one of them (D-06). The whole
    sequence -- read the outgoing version, archive it, prune, write -- runs in
    one transaction.
    """
    with session(db_path) as conn:
        previous = conn.execute(
            "SELECT yaml_content FROM master_resume WHERE user_id = ?", (user_id,)
        ).fetchone()
        if previous is not None:
            conn.execute(
                "INSERT INTO master_resume_history (user_id, yaml_content) "
                "VALUES (?, ?)",
                (user_id, previous["yaml_content"]),
            )
            conn.execute(
                "DELETE FROM master_resume_history WHERE user_id = ? AND id NOT IN ("
                "  SELECT id FROM master_resume_history WHERE user_id = ?"
                "  ORDER BY id DESC LIMIT ?"
                ")",
                (user_id, user_id, HISTORY_LIMIT),
            )
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  yaml_content = excluded.yaml_content, "
            "  updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
            (user_id, yaml_content),
        )
        return _to_model(conn.execute(_SELECT, (user_id,)).fetchone())


def delete_master_resume(db_path: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Delete the master resume. Its history cascades away with it (D-14)."""
    with session(db_path) as conn:
        cursor = conn.execute("DELETE FROM master_resume WHERE user_id = ?", (user_id,))
        return cursor.rowcount > 0
