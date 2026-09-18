# Database Engineer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the SQLite schema and all synchronous database functions the FastAPI routes will call.

**Architecture:** Pure stdlib `sqlite3` (synchronous). Route handlers in Wave 2 call these functions via `asyncio.to_thread()`. Schema is created lazily on first call to `init_db()`. All functions take `db_path: str` as first argument so they are easily testable with temp files.

**Tech Stack:** Python 3.12 stdlib only (`sqlite3`, `pathlib`, `tempfile`). Tests use `pytest`.

## Global Constraints

- `user_id` defaults to `"default"` in every function — hardcoded single-user app
- History pruning: keep only the 10 most recent master resume versions
- `pdf_path` column stores filename only (e.g. `"42.pdf"`), not full path
- Timestamps stored as ISO-8601 strings via SQLite `datetime('now')`
- Schema lives in `backend/db/schema.sql`; `database.py` reads it at runtime via `Path(__file__)`
- Tests use in-memory SQLite (pass `":memory:"` as `db_path`)

---

## File Structure

```
backend/
├── app/
│   ├── __init__.py          CREATE — empty package marker
│   └── database.py          CREATE — all DB functions
├── db/
│   └── schema.sql           CREATE — DDL for all 6 tables
└── tests/
    ├── __init__.py          CREATE — empty package marker
    └── test_database.py     CREATE — pytest unit tests
```

---

## Task 1: Schema SQL + `init_db()`

**Files:**
- Create: `backend/db/schema.sql`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/app/database.py` (partial — `init_db` + constants only)
- Test: `backend/tests/test_database.py` (partial)

**Interfaces:**
- Produces: `init_db(db_path: str) -> None` — called by FastAPI on startup

- [ ] **Step 1: Create the schema file**

```sql
-- backend/db/schema.sql
CREATE TABLE IF NOT EXISTS master_resume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    yaml_content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS master_resume_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    yaml_content TEXT NOT NULL,
    saved_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS generated_resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'Untitled',
    job_description TEXT NOT NULL DEFAULT '',
    yaml_content TEXT NOT NULL,
    pdf_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS generation_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    section TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    rule_value TEXT NOT NULL,
    UNIQUE(user_id, section, rule_key)
);

CREATE TABLE IF NOT EXISTS system_prompt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: Create package markers**

`backend/app/__init__.py` — empty file.
`backend/tests/__init__.py` — empty file.

- [ ] **Step 3: Write failing test for `init_db`**

```python
# backend/tests/test_database.py
import sqlite3
from app.database import init_db, DEFAULT_RULES, DEFAULT_SYSTEM_PROMPT


def test_init_db_creates_all_tables():
    db = ":memory:"
    init_db(db)
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    expected = {
        "master_resume", "master_resume_history", "generated_resumes",
        "chat_messages", "generation_rules", "system_prompt",
    }
    assert expected == tables


def test_init_db_seeds_default_rules():
    db = ":memory:"
    init_db(db)
    with sqlite3.connect(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM generation_rules WHERE user_id = 'default'"
        ).fetchone()[0]
    assert count == len(DEFAULT_RULES)


def test_init_db_seeds_default_system_prompt():
    db = ":memory:"
    init_db(db)
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT content FROM system_prompt WHERE user_id = 'default'"
        ).fetchone()
    assert row is not None
    assert row[0] == DEFAULT_SYSTEM_PROMPT


def test_init_db_is_idempotent():
    db = ":memory:"
    init_db(db)
    init_db(db)  # second call must not raise or duplicate data
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM system_prompt").fetchone()[0]
    assert count == 1
```

- [ ] **Step 4: Run test — expect failure**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/backend
pip install pytest --quiet
python -m pytest tests/test_database.py::test_init_db_creates_all_tables -v
```

Expected: `ModuleNotFoundError: No module named 'app.database'`

- [ ] **Step 5: Implement `init_db` in `database.py`**

```python
# backend/app/database.py
import sqlite3
from pathlib import Path

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
    return (Path(__file__).parent.parent / "db" / "schema.sql").read_text()


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
```

- [ ] **Step 6: Run tests — expect pass**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/backend
python -m pytest tests/test_database.py -v -k "init_db"
```

Expected: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/db/schema.sql backend/app/__init__.py backend/app/database.py \
        backend/tests/__init__.py backend/tests/test_database.py
git commit -m "feat(db): schema and init_db with seeded defaults"
```

---

## Task 2: Master Resume CRUD

**Files:**
- Modify: `backend/app/database.py` — add master resume functions
- Modify: `backend/tests/test_database.py` — add master resume tests

**Interfaces:**
- Produces:
  - `get_master_resume(db_path, user_id="default") -> dict | None`
  - `upsert_master_resume(db_path, yaml_content, user_id="default") -> dict`
  - `delete_master_resume(db_path, user_id="default") -> bool`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_database.py`:

```python
from app.database import (
    get_master_resume, upsert_master_resume, delete_master_resume,
)


def test_get_master_resume_returns_none_when_empty():
    db = ":memory:"
    init_db(db)
    assert get_master_resume(db) is None


def test_upsert_master_resume_creates_and_returns():
    db = ":memory:"
    init_db(db)
    result = upsert_master_resume(db, "cv:\n  name: Test")
    assert result["yaml_content"] == "cv:\n  name: Test"
    assert result["user_id"] == "default"
    assert "id" in result
    assert "updated_at" in result


def test_upsert_master_resume_updates_existing():
    db = ":memory:"
    init_db(db)
    upsert_master_resume(db, "cv:\n  name: First")
    result = upsert_master_resume(db, "cv:\n  name: Second")
    assert result["yaml_content"] == "cv:\n  name: Second"
    # Only one row should exist
    import sqlite3 as _s
    with _s.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume").fetchone()[0]
    assert count == 1


def test_upsert_saves_to_history():
    db = ":memory:"
    init_db(db)
    upsert_master_resume(db, "cv:\n  name: First")
    upsert_master_resume(db, "cv:\n  name: Second")
    import sqlite3 as _s
    with _s.connect(db) as conn:
        history = conn.execute(
            "SELECT yaml_content FROM master_resume_history ORDER BY saved_at ASC"
        ).fetchall()
    assert len(history) == 1
    assert history[0][0] == "cv:\n  name: First"


def test_history_pruned_to_10():
    db = ":memory:"
    init_db(db)
    for i in range(12):
        upsert_master_resume(db, f"cv:\n  name: Version{i}")
    import sqlite3 as _s
    with _s.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume_history").fetchone()[0]
    assert count == 10


def test_delete_master_resume():
    db = ":memory:"
    init_db(db)
    upsert_master_resume(db, "cv:\n  name: Test")
    assert delete_master_resume(db) is True
    assert get_master_resume(db) is None


def test_delete_master_resume_returns_false_when_not_exist():
    db = ":memory:"
    init_db(db)
    assert delete_master_resume(db) is False
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest tests/test_database.py -v -k "master_resume" 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError`

- [ ] **Step 3: Implement master resume functions**

Add to `backend/app/database.py`:

```python
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
                    ORDER BY saved_at DESC LIMIT ?
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_database.py -v -k "master_resume"
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/tests/test_database.py
git commit -m "feat(db): master resume CRUD with history pruning"
```

---

## Task 3: Generated Resumes CRUD

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/tests/test_database.py`

**Interfaces:**
- Produces:
  - `list_resumes(db_path, user_id, sort, order, page, limit) -> dict` — `{"items": [...], "total": int, "page": int, "limit": int}`
  - `create_resume(db_path, name, job_description, yaml_content, pdf_path, user_id) -> dict`
  - `get_resume(db_path, resume_id, user_id) -> dict | None`
  - `update_resume(db_path, resume_id, name, yaml_content, pdf_path, user_id) -> dict | None`
  - `delete_resume(db_path, resume_id, user_id) -> bool`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_database.py`:

```python
from app.database import (
    list_resumes, create_resume, get_resume, update_resume, delete_resume,
)


def test_create_and_get_resume():
    db = ":memory:"
    init_db(db)
    r = create_resume(db, "SWE @ Acme", "We need Python devs", "cv:\n  name: Test")
    assert r["name"] == "SWE @ Acme"
    assert r["job_description"] == "We need Python devs"
    assert r["pdf_path"] is None
    fetched = get_resume(db, r["id"])
    assert fetched["id"] == r["id"]


def test_get_resume_returns_none_for_missing():
    db = ":memory:"
    init_db(db)
    assert get_resume(db, 9999) is None


def test_list_resumes_pagination():
    db = ":memory:"
    init_db(db)
    for i in range(5):
        create_resume(db, f"Resume {i}", f"JD {i}", "cv:\n  name: X")
    result = list_resumes(db, page=1, limit=3)
    assert result["total"] == 5
    assert len(result["items"]) == 3
    assert result["page"] == 1


def test_list_resumes_sort_by_jd():
    db = ":memory:"
    init_db(db)
    create_resume(db, "B", "Zebra Corp", "cv:\n  name: B")
    create_resume(db, "A", "Apple Inc", "cv:\n  name: A")
    result = list_resumes(db, sort="jd", order="asc")
    assert result["items"][0]["name"] == "A"


def test_update_resume_name():
    db = ":memory:"
    init_db(db)
    r = create_resume(db, "Old Name", "JD", "cv:\n  name: X")
    updated = update_resume(db, r["id"], name="New Name")
    assert updated["name"] == "New Name"


def test_update_resume_pdf_path():
    db = ":memory:"
    init_db(db)
    r = create_resume(db, "Test", "JD", "cv:\n  name: X")
    updated = update_resume(db, r["id"], pdf_path="42.pdf")
    assert updated["pdf_path"] == "42.pdf"


def test_delete_resume():
    db = ":memory:"
    init_db(db)
    r = create_resume(db, "Test", "JD", "cv:\n  name: X")
    assert delete_resume(db, r["id"]) is True
    assert get_resume(db, r["id"]) is None


def test_delete_resume_returns_false_for_missing():
    db = ":memory:"
    init_db(db)
    assert delete_resume(db, 9999) is False
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_database.py -v -k "resume" --ignore-glob="*master*" 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Implement**

Add to `backend/app/database.py`:

```python
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
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_database.py -v -k "resume"
```

Expected: 15+ PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/tests/test_database.py
git commit -m "feat(db): generated resumes CRUD"
```

---

## Task 4: Chat, Rules, and System Prompt

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/tests/test_database.py`

**Interfaces:**
- Produces:
  - `get_chat_messages(db_path, user_id) -> list[dict]`
  - `add_chat_message(db_path, role, content, user_id) -> dict`
  - `clear_chat(db_path, user_id) -> None`
  - `get_rules(db_path, user_id) -> list[dict]` — each `{"section", "rule_key", "rule_value"}`
  - `upsert_rules(db_path, rules: list[dict], user_id) -> list[dict]`
  - `reset_rules(db_path, user_id) -> list[dict]`
  - `get_system_prompt(db_path, user_id) -> dict | None`
  - `upsert_system_prompt(db_path, content, user_id) -> dict`
  - `reset_system_prompt(db_path, user_id) -> dict`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_database.py`:

```python
from app.database import (
    get_chat_messages, add_chat_message, clear_chat,
    get_rules, upsert_rules, reset_rules,
    get_system_prompt, upsert_system_prompt, reset_system_prompt,
)


def test_add_and_get_chat_messages():
    db = ":memory:"
    init_db(db)
    add_chat_message(db, "user", "Hello")
    add_chat_message(db, "assistant", "Hi there!")
    msgs = get_chat_messages(db)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_clear_chat():
    db = ":memory:"
    init_db(db)
    add_chat_message(db, "user", "Hello")
    clear_chat(db)
    assert get_chat_messages(db) == []


def test_get_rules_returns_seeded_defaults():
    db = ":memory:"
    init_db(db)
    rules = get_rules(db)
    assert len(rules) == len(DEFAULT_RULES)
    keys = {(r["section"], r["rule_key"]) for r in rules}
    assert ("experience", "max_entries") in keys


def test_upsert_rules_updates_value():
    db = ":memory:"
    init_db(db)
    upsert_rules(db, [{"section": "experience", "rule_key": "max_entries", "rule_value": "3"}])
    rules = get_rules(db)
    exp_max = next(r for r in rules if r["section"] == "experience" and r["rule_key"] == "max_entries")
    assert exp_max["rule_value"] == "3"


def test_reset_rules_restores_defaults():
    db = ":memory:"
    init_db(db)
    upsert_rules(db, [{"section": "experience", "rule_key": "max_entries", "rule_value": "99"}])
    reset_rules(db)
    rules = get_rules(db)
    exp_max = next(r for r in rules if r["section"] == "experience" and r["rule_key"] == "max_entries")
    assert exp_max["rule_value"] == "2"


def test_get_system_prompt_returns_seeded_default():
    db = ":memory:"
    init_db(db)
    sp = get_system_prompt(db)
    assert sp is not None
    assert DEFAULT_SYSTEM_PROMPT in sp["content"]


def test_upsert_and_reset_system_prompt():
    db = ":memory:"
    init_db(db)
    upsert_system_prompt(db, "Custom prompt")
    assert get_system_prompt(db)["content"] == "Custom prompt"
    reset_system_prompt(db)
    assert get_system_prompt(db)["content"] == DEFAULT_SYSTEM_PROMPT
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_database.py -v -k "chat or rule or prompt" 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Implement**

Add to `backend/app/database.py`:

```python
# --- Chat ---

def get_chat_messages(db_path: str, user_id: str = DEFAULT_USER_ID) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, user_id, role, content, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY created_at ASC",
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
```

- [ ] **Step 4: Run all tests — expect all pass**

```bash
python -m pytest tests/test_database.py -v
```

Expected: all PASSED (no failures)

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/tests/test_database.py
git commit -m "feat(db): chat, rules, system prompt CRUD — Wave 1 database complete"
```

---

**Definition of done:** `python -m pytest backend/tests/test_database.py -v` — all green.
