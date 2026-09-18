import json
import pytest
from resumetailor.ports import LLMAuthError


@pytest.mark.anyio
async def test_evaluate_stream_returns_done(client, sim):
    sim.sim_llm.set_complete_response(json.dumps({
        "match_score": 72,
        "critique": "Missing Kubernetes.",
        "matched_keywords": ["Python"],
        "missing_keywords": ["Kubernetes"],
    }))
    response = await client.post("/api/evaluate/stream", json={
        "yaml_content": "cv:\n  name: Test",
        "job_description": "We need Python and Kubernetes devs.",
    })
    assert response.status_code == 200
    event_types = [
        l.replace("event: ", "").strip()
        for l in response.text.split("\n")
        if l.startswith("event:")
    ]
    assert "done" in event_types
    done_data = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:") and "match_score" in l
    )
    assert done_data["result"]["match_score"] == 72


@pytest.mark.anyio
async def test_evaluate_stream_error_llm_auth(client, sim):
    sim.sim_llm.set_complete_error(LLMAuthError("Invalid API key"))

    response = await client.post("/api/evaluate/stream", json={
        "yaml_content": "cv:\n  name: Test",
        "job_description": "We need Python and Kubernetes devs.",
    })
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
        if l.startswith("data:") and "LLM_AUTH_ERROR" in l
    )
    assert error_data["code"] == "LLM_AUTH_ERROR"
