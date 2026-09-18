import json
import pytest
from resumetailor.llm.stub import MOCK_GENERATION_RESULT_YAML, MOCK_GENERATION_PROGRESS
from resumetailor.core.errors import LLMAuthError


@pytest.mark.anyio
async def test_list_resumes_empty(client):
    response = await client.get("/api/resumes")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.anyio
async def test_generate_resume_sse_stream(client, sim, db_path):
    from resumetailor.database import upsert_master_resume
    import asyncio
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    lines = response.text.split("\n")
    event_types = [l.replace("event: ", "").strip() for l in lines if l.startswith("event:")]
    assert "done" in event_types
    assert sim.sim_llm.complete_call_count == 2


@pytest.mark.anyio
async def test_generate_resume_sse_error_llm_auth(client, sim, db_path):
    from resumetailor.database import upsert_master_resume
    import asyncio
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    sim.sim_llm.set_complete_error(LLMAuthError("Invalid API key"))

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    events = []
    for line in response.text.split("\n"):
        if line.startswith("event:"):
            events.append(line.replace("event: ", "").strip())
    assert "error" in events
    data_lines = [l for l in response.text.split("\n") if l.startswith("data:")]
    error_data = next(
        json.loads(l.replace("data: ", ""))
        for l in data_lines
        if "LLM_AUTH_ERROR" in l
    )
    assert error_data["code"] == "LLM_AUTH_ERROR"


@pytest.mark.anyio
async def test_generate_injects_rules_into_prompts(client, sim, db_path):
    from resumetailor.database import upsert_master_resume, upsert_rules
    import asyncio
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)
    await asyncio.to_thread(
        upsert_rules, db_path,
        [{"section": "experience", "rule_key": "max_entries", "rule_value": "7"}],
    )

    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    # last_complete_messages holds the critique (pass 2) call; both passes get the block
    system_content = sim.sim_llm.last_complete_messages[0]["content"]
    assert "USER-CONFIGURED LIMITS" in system_content
    assert "experience.max_entries = 7" in system_content


@pytest.mark.anyio
async def test_get_resume_404(client):
    response = await client.get("/api/resumes/9999")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_delete_resume(client, sim, db_path):
    from resumetailor.database import create_resume
    import asyncio
    r = await asyncio.to_thread(create_resume, db_path, "Test", "JD", "cv:\n  name: X")
    response = await client.delete(f"/api/resumes/{r['id']}")
    assert response.status_code == 204
