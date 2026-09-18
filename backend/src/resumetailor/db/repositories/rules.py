"""Generation rules: the per-section limits applied when tailoring."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session
from resumetailor.db.models import GenerationRule
from resumetailor.db.seed import DEFAULT_RULES

_SELECT = (
    "SELECT section, rule_key, rule_value FROM generation_rules "
    "WHERE user_id = ? ORDER BY section, rule_key"
)

# The upsert every other repository now copies: one statement, resolved by the
# database against a unique constraint, with no read-then-write window.
_UPSERT = (
    "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(user_id, section, rule_key) DO UPDATE SET "
    "rule_value = excluded.rule_value"
)


def _to_model(row: sqlite3.Row) -> GenerationRule:
    return GenerationRule(
        section=row["section"],
        rule_key=row["rule_key"],
        rule_value=row["rule_value"],
    )


def _read(conn: sqlite3.Connection, user_id: str) -> list[GenerationRule]:
    return [_to_model(row) for row in conn.execute(_SELECT, (user_id,)).fetchall()]


def get_rules(db_path: str, user_id: str = DEFAULT_USER_ID) -> list[GenerationRule]:
    with session(db_path) as conn:
        return _read(conn, user_id)


def upsert_rules(
    db_path: str,
    rules: Sequence[Mapping[str, str]],
    user_id: str = DEFAULT_USER_ID,
) -> list[GenerationRule]:
    """Set the given rules, leaving every other rule alone."""
    with session(db_path) as conn:
        conn.executemany(
            _UPSERT,
            [
                (user_id, rule["section"], rule["rule_key"], rule["rule_value"])
                for rule in rules
            ],
        )
        return _read(conn, user_id)


def reset_rules(db_path: str, user_id: str = DEFAULT_USER_ID) -> list[GenerationRule]:
    """Discard every rule the user set and put the defaults back."""
    with session(db_path) as conn:
        conn.execute("DELETE FROM generation_rules WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) "
            "VALUES (?, ?, ?, ?)",
            [(user_id, section, key, value) for section, key, value in DEFAULT_RULES],
        )
        return _read(conn, user_id)
