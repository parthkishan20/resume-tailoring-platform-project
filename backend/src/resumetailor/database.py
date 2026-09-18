# MOVED BY TASK 1.2. This module becomes db/engine.py, db/migrate.py,
# db/models.py, db/seed.py and db/repositories/*. See PLAN.md section 3.3.
# Nothing here was changed by the src-layout move except the schema.sql path,
# which now comes from core.config because `__file__.parent.parent` no longer
# resolves to `backend/`.
import sqlite3

from resumetailor.core.config import SCHEMA_SQL_PATH

DEFAULT_USER_ID = "default"
HISTORY_LIMIT = 10

DEFAULT_RULES: list[tuple[str, str, str]] = [
    ("experience",      "max_entries", "2"),
    ("projects",        "max_entries", "3"),
    ("education",       "max_entries", "5"),
    ("extracurricular", "max_entries", "1"),
    ("certifications",  "max_entries", "2"),
    ("skills",          "max_entries", "20"),
    ("experience",      "max_bullets", "4"),
    ("projects",        "max_bullets", "3"),
    ("extracurricular", "max_bullets", "3"),
    ("experience",      "max_chars",   "120"),
    ("projects",        "max_chars",   "120"),
    ("extracurricular", "max_chars",   "120"),
]

DEFAULT_SYSTEM_PROMPT = (
    "You are ResumeTailor, an AI assistant specialized in resume creation and optimization. "
    "You can help users create and edit their master resume, generate tailored resumes for "
    "specific job descriptions, and evaluate resumes against job postings. "
    "Be concise, professional, and action-oriented in your responses."
)


def _schema_sql() -> str:
    return SCHEMA_SQL_PATH.read_text()


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_schema_sql())
        if conn.execute(
            "SELECT COUNT(*) FROM generation_rules WHERE user_id = ?", (DEFAULT_USER_ID,)
        ).fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) "
                "VALUES (?, ?, ?, ?)",
                [(DEFAULT_USER_ID, s, k, v) for s, k, v in DEFAULT_RULES],
            )
        if conn.execute(
            "SELECT COUNT(*) FROM system_prompt WHERE user_id = ?", (DEFAULT_USER_ID,)
        ).fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO system_prompt (user_id, content) VALUES (?, ?)",
                (DEFAULT_USER_ID, DEFAULT_SYSTEM_PROMPT),
            )
        conn.commit()


# --- Master Resume CRUD ---

def get_master_resume(db_path: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, user_id, yaml_content, updated_at FROM master_resume WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def upsert_master_resume(
    db_path: str, yaml_content: str, user_id: str = DEFAULT_USER_ID
) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT yaml_content FROM master_resume WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "INSERT INTO master_resume_history (user_id, yaml_content) VALUES (?, ?)",
                (user_id, existing["yaml_content"]),
            )
            conn.execute(
                """DELETE FROM master_resume_history WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM master_resume_history WHERE user_id = ?
                    ORDER BY id DESC LIMIT ?
                )""",
                (user_id, user_id, HISTORY_LIMIT),
            )
            conn.execute(
                "UPDATE master_resume SET yaml_content = ?, updated_at = datetime('now') "
                "WHERE user_id = ?",
                (yaml_content, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO master_resume (user_id, yaml_content) VALUES (?, ?)",
                (user_id, yaml_content),
            )
        conn.commit()
        return dict(conn.execute(
            "SELECT id, user_id, yaml_content, updated_at FROM master_resume WHERE user_id = ?",
            (user_id,),
        ).fetchone())


def delete_master_resume(db_path: str, user_id: str = DEFAULT_USER_ID) -> bool:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM master_resume WHERE user_id = ?", (user_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


# --- Generated Resumes CRUD ---

def list_resumes(
    db_path: str,
    user_id: str = DEFAULT_USER_ID,
    sort: str = "date",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> dict:
    sort_col = "created_at" if sort == "date" else "job_description"
    order_dir = "DESC" if order.lower() == "desc" else "ASC"
    offset = (page - 1) * limit
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(
            "SELECT COUNT(*) FROM generated_resumes WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, user_id, name, job_description, pdf_path, created_at, updated_at "
            f"FROM generated_resumes WHERE user_id = ? "
            f"ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page, "limit": limit}


def create_resume(
    db_path: str,
    name: str,
    job_description: str,
    yaml_content: str,
    pdf_path: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO generated_resumes (user_id, name, job_description, yaml_content, pdf_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, name, job_description, yaml_content, pdf_path),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM generated_resumes WHERE id = ?", (cursor.lastrowid,)
        ).fetchone())


def get_resume(
    db_path: str, resume_id: int, user_id: str = DEFAULT_USER_ID
) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM generated_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def update_resume(
    db_path: str,
    resume_id: int,
    name: str | None = None,
    yaml_content: str | None = None,
    pdf_path: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict | None:
    fields: list[str] = []
    values: list = []
    if name is not None:
        fields.append("name = ?"); values.append(name)
    if yaml_content is not None:
        fields.append("yaml_content = ?"); values.append(yaml_content)
    if pdf_path is not None:
        fields.append("pdf_path = ?"); values.append(pdf_path)
    if not fields:
        return get_resume(db_path, resume_id, user_id)
    fields.append("updated_at = datetime('now')")
    values.extend([resume_id, user_id])
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            f"UPDATE generated_resumes SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM generated_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def delete_resume(
    db_path: str, resume_id: int, user_id: str = DEFAULT_USER_ID
) -> bool:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM generated_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# --- Chat ---

def get_chat_messages(db_path: str, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, user_id, role, content, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_chat_message(
    db_path: str, role: str, content: str, user_id: str = DEFAULT_USER_ID
) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM chat_messages WHERE id = ?", (cursor.lastrowid,)
        ).fetchone())


def clear_chat(db_path: str, user_id: str = DEFAULT_USER_ID) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.commit()


# --- Generation Rules ---

def get_rules(db_path: str, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT section, rule_key, rule_value FROM generation_rules WHERE user_id = ? "
            "ORDER BY section, rule_key",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_rules(
    db_path: str, rules: list[dict], user_id: str = DEFAULT_USER_ID
) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        for rule in rules:
            conn.execute(
                "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, section, rule_key) DO UPDATE SET rule_value = excluded.rule_value",
                (user_id, rule["section"], rule["rule_key"], rule["rule_value"]),
            )
        conn.commit()
    return get_rules(db_path, user_id)


def reset_rules(db_path: str, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM generation_rules WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) VALUES (?, ?, ?, ?)",
            [(user_id, s, k, v) for s, k, v in DEFAULT_RULES],
        )
        conn.commit()
    return get_rules(db_path, user_id)


# --- System Prompt ---

def get_system_prompt(db_path: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, user_id, content, updated_at FROM system_prompt WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def upsert_system_prompt(
    db_path: str, content: str, user_id: str = DEFAULT_USER_ID
) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute(
            "SELECT 1 FROM system_prompt WHERE user_id = ?", (user_id,)
        ).fetchone():
            conn.execute(
                "UPDATE system_prompt SET content = ?, updated_at = datetime('now') WHERE user_id = ?",
                (content, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO system_prompt (user_id, content) VALUES (?, ?)",
                (user_id, content),
            )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM system_prompt WHERE user_id = ?", (user_id,)
        ).fetchone())


def reset_system_prompt(db_path: str, user_id: str = DEFAULT_USER_ID) -> dict:
    return upsert_system_prompt(db_path, DEFAULT_SYSTEM_PROMPT, user_id)
