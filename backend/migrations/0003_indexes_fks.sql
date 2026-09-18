-- 0003 — indexes and the one real foreign key (D-14).
--
-- Every query in the repository layer filters on user_id and most of them then
-- order by created_at or job_description. None of that was indexed, so each one
-- was a full scan plus a sort.
--
-- `master_resume_history` rows are children of the master resume: deleting the
-- master resume used to leave them behind forever, invisible and unreachable.
-- The FK below makes that cascade. It needs UNIQUE(user_id) on the parent,
-- which is why it follows 0002 rather than shipping with it.
--
-- `generated_resumes` gets indexes but NO foreign key, deliberately. It has no
-- parent row anywhere in this schema: there is no `users` table, and the only
-- candidate parent is `master_resume`, which would mean DELETE /api/master-resume
-- silently destroys the user's entire generated library. Inventing a `users`
-- table to hang the constraint on would collide with whatever task 2.4 decides
-- about identity. Both options are worse than the missing constraint, so the
-- constraint stays missing and this comment records why.

-- Orphans first: rows whose parent master resume no longer exists cannot be
-- carried across, and they are exactly the leak this FK closes.
DELETE FROM master_resume_history
 WHERE user_id NOT IN (SELECT user_id FROM master_resume);

CREATE TABLE master_resume_history_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES master_resume(user_id) ON DELETE CASCADE,
    yaml_content TEXT NOT NULL,
    saved_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO master_resume_history_new (id, user_id, yaml_content, saved_at)
SELECT id, user_id, yaml_content, saved_at FROM master_resume_history;

DROP TABLE master_resume_history;
ALTER TABLE master_resume_history_new RENAME TO master_resume_history;

CREATE INDEX IF NOT EXISTS idx_master_resume_history_user
    ON master_resume_history(user_id, id);

-- The two orderings `list_resumes` offers, each with user_id as the prefix.
CREATE INDEX IF NOT EXISTS idx_generated_resumes_user_created
    ON generated_resumes(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_generated_resumes_user_jd
    ON generated_resumes(user_id, job_description);

-- Chat is always read in id order for one user.
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id
    ON chat_messages(user_id, id);

-- master_resume, system_prompt and generation_rules are already covered by the
-- UNIQUE constraints on (user_id) and (user_id, section, rule_key).
