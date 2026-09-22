"""How many provider calls have gone out, for the rate-limit counter in the UI.

OpenRouter's free tier caps usage per API key at a fixed number of requests
per rolling minute and per calendar day (UTC). This only counts calls this
process made through :class:`resumetailor.llm.litellm_adapter.LiteLLMAdapter`
(wired through its ``on_request`` hook) — a key shared with another caller
outside this process would run ahead of what this counter shows.

The "day" window is calendar-UTC (since 00:00:00Z today), not a rolling 24
hours: simpler to reason about and to show in the UI ("resets at midnight
UTC"), and close enough to whatever OpenRouter's own reset actually does for
a counter that only has to keep the user from being surprised, not enforce
anything.
"""

from __future__ import annotations

from resumetailor.db.engine import session

#: How long a row is kept before `record_llm_request` prunes it. Only the
#: last day's rows are ever queried (the day window never looks back further
#: than 00:00:00Z today), so this is a generous margin, not a tuned value.
_RETENTION = "-2 days"


def record_llm_request(db_path: str) -> None:
    """Log one outbound provider call, and sweep anything old enough to be dead weight."""
    with session(db_path) as conn:
        conn.execute("INSERT INTO llm_requests DEFAULT VALUES")
        conn.execute(
            "DELETE FROM llm_requests WHERE created_at < "
            f"strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '{_RETENTION}')"
        )


def get_llm_request_counts(db_path: str) -> tuple[int, int]:
    """``(calls in the last 60 seconds, calls since 00:00:00Z today)``."""
    with session(db_path) as conn:
        row = conn.execute(
            "SELECT "
            "  COUNT(*) FILTER ("
            "    WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-60 seconds')"
            "  ) AS minute_count, "
            "  COUNT(*) FILTER ("
            "    WHERE created_at >= strftime('%Y-%m-%dT00:00:00Z', 'now')"
            "  ) AS day_count "
            "FROM llm_requests"
        ).fetchone()
        return row["minute_count"], row["day_count"]
