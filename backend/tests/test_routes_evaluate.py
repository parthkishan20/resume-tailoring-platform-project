import json
import pytest
from resumetailor.core.errors import LLMAuthError


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
async def test_evaluate_stream_wire_shape_is_unchanged(client, sim):
    """Task 2.5 parses into a model; the frame the frontend reads is the same.

    The progress string and the four `result` keys are the contract, whether
    the service hands the route a `dict` or an `EvaluationResult`.
    """
    scored = {
        "match_score": 72,
        "critique": "Missing Kubernetes.",
        "matched_keywords": ["Python"],
        "missing_keywords": ["Kubernetes"],
    }
    sim.sim_llm.set_complete_response(json.dumps(scored))
    response = await client.post("/api/evaluate/stream", json={
        "yaml_content": "cv:\n  name: Test",
        "job_description": "We need Python and Kubernetes devs.",
    })
    frames = [
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:")
    ]
    assert frames[0] == {"message": "Analyzing resume and job description..."}
    assert frames[1] == {"result": scored}


@pytest.mark.anyio
async def test_evaluate_stream_off_schema_response_is_an_error_frame(client, sim):
    """A provider that ignores the schema used to reach the panel half-filled."""
    sim.sim_llm.set_complete_response(json.dumps({"match_score": 50}))
    response = await client.post("/api/evaluate/stream", json={
        "yaml_content": "cv:\n  name: Test",
        "job_description": "jd",
    })
    assert response.status_code == 200
    error_data = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:") and "EVALUATION_FAILED" in l
    )
    assert error_data["code"] == "EVALUATION_FAILED"
    assert "match_score" not in error_data["error"], "the parse failure is not the user's business"


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
