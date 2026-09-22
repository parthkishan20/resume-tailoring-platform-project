"""`GET /api/llm/usage` — the rate-limit counter next to the assistant."""

from __future__ import annotations

import pytest

from resumetailor.db.repositories.llm_requests import record_llm_request


@pytest.mark.anyio
async def test_llm_usage_starts_at_zero_with_default_limits(client):
    response = await client.get("/api/llm/usage")
    assert response.status_code == 200
    assert response.json() == {
        "minute_count": 0,
        "minute_limit": 20,
        "day_count": 0,
        "day_limit": 50,
    }


@pytest.mark.anyio
async def test_llm_usage_reflects_recorded_calls(client, db_path):
    record_llm_request(db_path)
    record_llm_request(db_path)

    response = await client.get("/api/llm/usage")
    body = response.json()
    assert body["minute_count"] == 2
    assert body["day_count"] == 2
