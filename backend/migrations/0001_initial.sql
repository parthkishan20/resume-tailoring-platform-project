-- 0001 — the schema as it stood before migrations existed.
--
-- This reproduces backend/db/schema.sql byte-for-byte in effect: same columns,
-- same types, same defaults, same constraints. It is deliberately NOT improved.
-- An existing database created by the old `init_db` is already at this shape,
-- so `IF NOT EXISTS` makes 0001 a no-op there and the later migrations carry
-- every change from here.

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
