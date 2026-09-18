-- 0004 — ISO-8601 UTC timestamps, in the data and in the defaults (D-09).
--
-- Every timestamp column defaulted to `datetime('now')`, which produces
-- "2026-09-18 07:41:03": UTC, but space-separated and with no zone marker.
-- `new Date("2026-09-18 07:41:03")` in a browser reads that as LOCAL time, so
-- every timestamp the UI showed was wrong by the host's offset. The value is
-- right, the format lies about it.
--
-- A schema change is genuinely required. SQLite has no ALTER COLUMN, so a
-- column default can only be changed by rebuilding the table -- and the rows
-- already written need converting whatever the default becomes, which no
-- amount of care in the write layer can do retroactively. So this migration
-- does both at once: the rebuild's SELECT converts each stored value, and the
-- new table carries the ISO default. The repository layer writes the same form
-- explicitly wherever it sets a timestamp on UPDATE, where defaults do not
-- apply.
--
-- COALESCE guards the conversion: strftime returns NULL on a value it cannot
-- parse, and these columns are NOT NULL. A value that is already ISO with a Z
-- parses fine and converts to itself, so re-running against converted data
-- would be harmless.
--
-- Rebuilding restates the UNIQUE constraint from 0002, the foreign key from
-- 0003 and the indexes from 0003. That is not duplication for its own sake:
-- DROP TABLE takes the table's indexes with it, and the rebuilt definition has
-- to carry every constraint the table had. What this file creates is the final
-- schema.

CREATE TABLE master_resume_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default' UNIQUE,
    yaml_content TEXT NOT NULL,
    updated_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO master_resume_new (id, user_id, yaml_content, updated_at)
SELECT id, user_id, yaml_content,
       COALESCE(strftime('%Y-%m-%dT%H:%M:%SZ', updated_at), updated_at)
  FROM master_resume;

DROP TABLE master_resume;
ALTER TABLE master_resume_new RENAME TO master_resume;

CREATE TABLE master_resume_history_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES master_resume(user_id) ON DELETE CASCADE,
    yaml_content TEXT NOT NULL,
    saved_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO master_resume_history_new (id, user_id, yaml_content, saved_at)
SELECT id, user_id, yaml_content,
       COALESCE(strftime('%Y-%m-%dT%H:%M:%SZ', saved_at), saved_at)
  FROM master_resume_history;

DROP TABLE master_resume_history;
ALTER TABLE master_resume_history_new RENAME TO master_resume_history;

CREATE TABLE generated_resumes_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'Untitled',
    job_description TEXT NOT NULL DEFAULT '',
    yaml_content TEXT NOT NULL,
    pdf_path TEXT,
    created_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO generated_resumes_new
    (id, user_id, name, job_description, yaml_content, pdf_path,
     created_at, updated_at)
SELECT id, user_id, name, job_description, yaml_content, pdf_path,
       COALESCE(strftime('%Y-%m-%dT%H:%M:%SZ', created_at), created_at),
       COALESCE(strftime('%Y-%m-%dT%H:%M:%SZ', updated_at), updated_at)
  FROM generated_resumes;

DROP TABLE generated_resumes;
ALTER TABLE generated_resumes_new RENAME TO generated_resumes;

CREATE TABLE chat_messages_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO chat_messages_new (id, user_id, role, content, created_at)
SELECT id, user_id, role, content,
       COALESCE(strftime('%Y-%m-%dT%H:%M:%SZ', created_at), created_at)
  FROM chat_messages;

DROP TABLE chat_messages;
ALTER TABLE chat_messages_new RENAME TO chat_messages;

CREATE TABLE system_prompt_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default' UNIQUE,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO system_prompt_new (id, user_id, content, updated_at)
SELECT id, user_id, content,
       COALESCE(strftime('%Y-%m-%dT%H:%M:%SZ', updated_at), updated_at)
  FROM system_prompt;

DROP TABLE system_prompt;
ALTER TABLE system_prompt_new RENAME TO system_prompt;

-- Recreated because DROP TABLE took them.
CREATE INDEX IF NOT EXISTS idx_master_resume_history_user
    ON master_resume_history(user_id, id);
CREATE INDEX IF NOT EXISTS idx_generated_resumes_user_created
    ON generated_resumes(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_generated_resumes_user_jd
    ON generated_resumes(user_id, job_description);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id
    ON chat_messages(user_id, id);
