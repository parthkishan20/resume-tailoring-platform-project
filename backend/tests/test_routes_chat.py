import json
import pytest
from resumetailor.core.errors import LLMUnavailableError


@pytest.mark.anyio
async def test_get_chat_history_empty(client):
    response = await client.get("/api/chat")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_chat_stream_returns_token_events(client, sim):
    sim.sim_llm.set_stream_chunks(["Hello ", "world!"])

    response = await client.post("/api/chat/stream", json={"message": "Hi"})
    assert response.status_code == 200
    lines = response.text.split("\n")
    event_types = [l.replace("event: ", "").strip() for l in lines if l.startswith("event:")]
    assert "token" in event_types
    assert "done" in event_types


@pytest.mark.anyio
async def test_chat_stream_error_llm_unavailable(client, sim):
    sim.sim_llm.set_stream_error(LLMUnavailableError("Service unavailable"))

    response = await client.post("/api/chat/stream", json={"message": "Hi"})
    assert response.status_code == 200
    events = [
        l.replace("event: ", "").strip()
        for l in response.text.split("\n")
        if l.startswith("event:")
    ]
    assert "error" in events
    error_data = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:") and "LLM_UNAVAILABLE" in l
    )
    assert error_data["code"] == "LLM_UNAVAILABLE"


@pytest.mark.anyio
async def test_clear_chat(client):
    response = await client.delete("/api/chat")
    assert response.status_code == 204
