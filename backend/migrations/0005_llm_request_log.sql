-- 0005 — a row per outbound LLM provider call, for the free-tier rate-limit
-- counter shown in the UI next to the assistant.
--
-- No `user_id`: unlike every other table here, this one is not a per-user
-- record. OpenRouter's free-tier limit (20 requests/minute, 50/day, as of
-- 2026-09) is scoped to the API key, globally, regardless of which "user" of
-- this single-user app triggered the call. Adding `user_id` would imply a
-- per-user quota that does not exist.
--
-- No foreign keys, nothing else references this table, and rows are pruned
-- opportunistically by the repository on every insert (`llm_requests.py`), so
-- there is no unbounded-growth concern (D-14) worth a reaper for.
CREATE TABLE IF NOT EXISTS llm_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_requests_created_at ON llm_requests(created_at);
