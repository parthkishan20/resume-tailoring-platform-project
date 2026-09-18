-- 0002 — UNIQUE(user_id) on the two single-row-per-user tables (D-06).
--
-- `master_resume` and `system_prompt` are, by contract, one row per user, but
-- nothing in the schema said so. Their upserts read-then-wrote, so two
-- concurrent writes could both miss the existing row and both INSERT. Reads
-- then returned whichever row SQLite happened to hand back first, which is how
-- an edit appears to revert at random.
--
-- SQLite cannot add a constraint to an existing table, so both tables are
-- rebuilt. The migration runs with foreign_keys OFF and legacy_alter_table ON
-- (see db/migrate.py), which is the documented procedure for this rebuild.
--
-- This migration is written to be safe against a database that ALREADY holds
-- duplicate rows from the bug above. It cannot keep both, so it picks a winner
-- per user_id -- the row with the greatest (updated_at, id), i.e. the most
-- recently written -- and for `master_resume` it preserves every loser in
-- `master_resume_history` rather than dropping it on the floor. Nothing the
-- user wrote is destroyed; at worst a superseded version moves into history.

-- Losing master_resume duplicates become history entries, newest-last, keeping
-- their original timestamp. Runs before the rebuild, while the rows still
-- exist. On a database with no duplicates this inserts nothing.
INSERT INTO master_resume_history (user_id, yaml_content, saved_at)
SELECT m.user_id, m.yaml_content, m.updated_at
  FROM master_resume AS m
 WHERE m.id <> (
        SELECT m2.id
          FROM master_resume AS m2
         WHERE m2.user_id = m.user_id
         ORDER BY m2.updated_at DESC, m2.id DESC
         LIMIT 1
       );

CREATE TABLE master_resume_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default' UNIQUE,
    yaml_content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO master_resume_new (id, user_id, yaml_content, updated_at)
SELECT m.id, m.user_id, m.yaml_content, m.updated_at
  FROM master_resume AS m
 WHERE m.id = (
        SELECT m2.id
          FROM master_resume AS m2
         WHERE m2.user_id = m.user_id
         ORDER BY m2.updated_at DESC, m2.id DESC
         LIMIT 1
       );

DROP TABLE master_resume;
ALTER TABLE master_resume_new RENAME TO master_resume;

-- system_prompt has no history table, so a losing duplicate here is discarded.
-- The content is a single prompt paragraph and the surviving row is the most
-- recently written one, which is what every read after the bug would have been
-- trying to return anyway.
CREATE TABLE system_prompt_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default' UNIQUE,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO system_prompt_new (id, user_id, content, updated_at)
SELECT s.id, s.user_id, s.content, s.updated_at
  FROM system_prompt AS s
 WHERE s.id = (
        SELECT s2.id
          FROM system_prompt AS s2
         WHERE s2.user_id = s.user_id
         ORDER BY s2.updated_at DESC, s2.id DESC
         LIMIT 1
       );

DROP TABLE system_prompt;
ALTER TABLE system_prompt_new RENAME TO system_prompt;
