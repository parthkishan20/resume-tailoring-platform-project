"""The rows a usable database needs before the user has written anything.

Seeding is separate from migration on purpose. A migration changes the shape of
the database and runs once; seeding puts default *content* in it and has to be
safe to run on every boot, because a user who deletes every rule still needs
the defaults back on the next start.

Both inserts are guarded by ``ON CONFLICT DO NOTHING`` against the existing
unique constraints, so a boot against a populated database writes nothing and
never overwrites an edit.
"""

from __future__ import annotations

import logging

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session

logger = logging.getLogger(__name__)

#: ``(section, rule_key, rule_value)``. Section names are the ones the
#: generation prompt uses. Note that ``extracurricular`` does not match the
#: YAML schema's ``extra_curricular_activities`` -- that is D-23, and it is
#: task 1.3's to fix along with the rest of the schema contract. Reproduced
#: here exactly as it was so this task changes no behaviour.
DEFAULT_RULES: list[tuple[str, str, str]] = [
    ("experience", "max_entries", "2"),
    ("projects", "max_entries", "3"),
    ("education", "max_entries", "5"),
    ("extracurricular", "max_entries", "1"),
    ("certifications", "max_entries", "2"),
    ("skills", "max_entries", "20"),
    ("experience", "max_bullets", "4"),
    ("projects", "max_bullets", "3"),
    ("extracurricular", "max_bullets", "3"),
    ("experience", "max_chars", "120"),
    ("projects", "max_chars", "120"),
    ("extracurricular", "max_chars", "120"),
]

DEFAULT_SYSTEM_PROMPT = (
    "You are ResumeTailor, an AI assistant specialized in resume creation and "
    "optimization. You can help users create and edit their master resume, "
    "generate tailored resumes for specific job descriptions, and evaluate "
    "resumes against job postings. Be concise, professional, and "
    "action-oriented in your responses."
)


def seed_defaults(db_path: str, user_id: str = DEFAULT_USER_ID) -> None:
    """Insert the default rules and system prompt if they are not there.

    Blocking; callers reach it through ``asyncio.to_thread``.
    """
    with session(db_path) as conn:
        conn.executemany(
            "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, section, rule_key) DO NOTHING",
            [(user_id, section, key, value) for section, key, value in DEFAULT_RULES],
        )
        conn.execute(
            "INSERT INTO system_prompt (user_id, content) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id, DEFAULT_SYSTEM_PROMPT),
        )
