import json
import pytest
from resumetailor.core.errors import LLMUnavailableError
from resumetailor.llm.port import ToolCall


def _events(body: str) -> list[tuple[str, dict]]:
    """The `(event, payload)` pairs of an SSE response body."""
    parsed = []
    event = "message"
    for line in body.split("\n"):
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            parsed.append((event, json.loads(line.removeprefix("data:").strip())))
    return parsed


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


# ── Pagination (B-07, D-21) ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_chat_history_limit_bounds_the_page(client):
    for i in range(10):
        await client.post("/api/chat/stream", json={"message": f"m{i}"})

    response = await client.get("/api/chat", params={"limit": 4})
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 4


@pytest.mark.anyio
async def test_get_chat_history_before_id_pages_backward(client, sim):
    sim.sim_llm.set_stream_chunks(["ok"])
    for i in range(6):
        await client.post("/api/chat/stream", json={"message": f"m{i}"})

    first_page = (await client.get("/api/chat", params={"limit": 4})).json()
    assert len(first_page) == 4

    second_page = (
        await client.get("/api/chat", params={"limit": 4, "before_id": first_page[0]["id"]})
    ).json()
    assert len(second_page) == 4
    assert second_page[-1]["id"] < first_page[0]["id"]
    # Each page is itself oldest-first.
    assert [m["id"] for m in second_page] == sorted(m["id"] for m in second_page)


@pytest.mark.anyio
async def test_get_chat_history_limit_out_of_range_is_422(client):
    response = await client.get("/api/chat", params={"limit": 0})
    assert response.status_code == 422

    response = await client.get("/api/chat", params={"limit": 1000})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_get_chat_history_with_no_params_is_unchanged(client, sim):
    sim.sim_llm.set_stream_chunks(["ok"])
    for i in range(3):
        await client.post("/api/chat/stream", json={"message": f"m{i}"})

    response = await client.get("/api/chat")
    assert response.status_code == 200
    assert len(response.json()) == 6  # every user + assistant turn, unbounded


# ── Tool calling (task 3.3, D-33) ───────────────────────────────────────────


@pytest.mark.anyio
async def test_chat_stream_executes_a_tool_call_and_reports_the_action(client, sim):
    """The end-to-end path: a tool call is real, not `"action": None`."""
    new_yaml = "cv:\n  name: Tool Written\n  email: tool@example.com\n"
    sim.sim_llm.set_stream_events(
        [
            [
                ToolCall(
                    id="call-1",
                    name="edit_master_resume",
                    arguments=json.dumps({"yaml_content": new_yaml}),
                )
            ],
            ["Your master resume is updated."],
        ]
    )

    response = await client.post("/api/chat/stream", json={"message": "Update my resume"})
    assert response.status_code == 200

    frames = _events(response.text)
    done = next(payload for event, payload in frames if event == "done")
    assert done["result"]["action"] == {
        "type": "master_resume_updated",
        "resume_id": None,
    }
    assert done["result"]["text"] == "Your master resume is updated."

    stored = await client.get("/api/master-resume")
    assert stored.json()["yaml_content"] == new_yaml


@pytest.mark.anyio
async def test_chat_stream_with_no_tool_call_still_reports_no_action(client, sim):
    """The non-tool-calling path is unchanged: `action` is `None`, not omitted."""
    sim.sim_llm.set_stream_chunks(["Sure, ", "I can help with that."])

    response = await client.post("/api/chat/stream", json={"message": "hi"})

    done = next(
        payload for event, payload in _events(response.text) if event == "done"
    )
    assert done["result"]["action"] is None
    assert done["result"]["text"] == "Sure, I can help with that."


@pytest.mark.anyio
async def test_a_failed_tool_call_reports_no_action_and_keeps_the_stream_alive(
    client, sim
):
    """A validation failure inside a tool is not a stream-ending error (D-53)."""
    sim.sim_llm.set_stream_events(
        [
            [
                ToolCall(
                    id="call-1",
                    name="edit_master_resume",
                    arguments=json.dumps({"yaml_content": "cv:\n  name: [bad]\n"}),
                )
            ],
            ["That document would not render, so I left your resume alone."],
        ]
    )

    response = await client.post("/api/chat/stream", json={"message": "break it"})
    assert response.status_code == 200

    frames = _events(response.text)
    assert not any(event == "error" for event, _ in frames)
    done = next(payload for event, payload in frames if event == "done")
    assert done["result"]["action"] is None

    stored = await client.get("/api/master-resume")
    assert stored.status_code == 404  # never written


@pytest.mark.anyio
async def test_chat_history_does_not_persist_tool_call_round_trips(client, sim):
    """`GET /api/chat` shows the transcript, not the working state of one turn."""
    sim.sim_llm.set_stream_events(
        [
            [
                ToolCall(
                    id="call-1",
                    name="update_generation_rules",
                    arguments=json.dumps(
                        {
                            "rules": [
                                {
                                    "section": "experience",
                                    "rule_key": "max_bullets",
                                    "rule_value": "3",
                                }
                            ]
                        }
                    ),
                )
            ],
            ["Done."],
        ]
    )

    await client.post("/api/chat/stream", json={"message": "limit bullets to 3"})

    history = (await client.get("/api/chat")).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[-1]["content"] == "Done."
