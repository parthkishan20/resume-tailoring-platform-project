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
    from resumetailor.db.repositories import upsert_master_resume
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
async def test_generate_stream_progress_messages_are_the_wire_contract(client, sim, db_path):
    """The three strings the frontend matches on, in order.

    Task 2.5 moved the pipeline into `domain.tailoring`, which yields `Stage`
    members; the message text is mapped back here, in the route. This pins that
    the mapping still produces exactly what it produced before the move.
    """
    from resumetailor.db.repositories import upsert_master_resume
    import asyncio
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    progress = [
        json.loads(l.replace("data: ", ""))["message"]
        for l in response.text.split("\n")
        if l.startswith("data:") and "message" in l
    ]
    assert progress == MOCK_GENERATION_PROGRESS


@pytest.mark.anyio
async def test_generate_stream_stores_the_document_that_was_rendered(client, sim, db_path):
    """D-04 on the generation path: the stored YAML is the rendered YAML."""
    from resumetailor.db.repositories import upsert_master_resume, get_resume
    import asyncio
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    done = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:") and "result" in l
    )
    resume_id = done["result"]["id"]
    row = await asyncio.to_thread(get_resume, db_path, resume_id)
    assert row.yaml_content == sim.sim_pdf_render.last_yaml_content
    assert row.pdf_path == f"{resume_id}.pdf"


@pytest.mark.anyio
async def test_generate_resume_sse_error_llm_auth(client, sim, db_path):
    from resumetailor.db.repositories import upsert_master_resume
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
    from resumetailor.db.repositories import upsert_master_resume, upsert_rules
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
async def test_generate_stream_without_a_master_resume(client, sim, db_path):
    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    error_data = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:")
    )
    assert error_data == {"error": "No master resume found", "code": "NO_MASTER_RESUME"}
    assert sim.sim_llm.complete_call_count == 0


@pytest.mark.anyio
async def test_generate_stream_yaml_content_overrides_saved_master(client, sim, db_path):
    """B-06: an explicit `yaml_content` tailors that document, not the saved master."""
    from resumetailor.db.repositories import upsert_master_resume
    import asyncio
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    override_yaml = MOCK_GENERATION_RESULT_YAML.replace(
        "Mock User", "Override User"
    ).replace("mock@example.com", "override@example.com")

    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(
        "/api/resumes/stream",
        json={
            "job_description": "Software Engineer at Mock Corp",
            "yaml_content": override_yaml,
        },
    )
    assert response.status_code == 200
    event_types = [
        l.replace("event: ", "").strip() for l in response.text.split("\n") if l.startswith("event:")
    ]
    assert "done" in event_types

    # The critique pass's user content is "Draft:\n...\n\nMaster:\n...\n\nJD:\n...";
    # the draft always echoes the mocked LLM response (Mock User), so only the
    # master section is checked for the override taking effect.
    user_content = sim.sim_llm.last_complete_messages[1]["content"]
    master_section = user_content.split("Master:\n", 1)[1].split("\n\nJD:", 1)[0]
    assert "Override User" in master_section
    assert "Mock User" not in master_section


@pytest.mark.anyio
async def test_generate_stream_yaml_content_override_needs_no_saved_master(client, sim, db_path):
    """B-06: the override makes the saved master resume optional."""
    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(
        "/api/resumes/stream",
        json={
            "job_description": "Software Engineer at Mock Corp",
            "yaml_content": MOCK_GENERATION_RESULT_YAML,
        },
    )
    assert response.status_code == 200
    event_types = [
        l.replace("event: ", "").strip() for l in response.text.split("\n") if l.startswith("event:")
    ]
    assert "done" in event_types
    assert "error" not in event_types


@pytest.mark.anyio
async def test_generate_stream_render_failure_is_opaque(client, sim, db_path):
    """D-53: a render failure carries the subprocess's whole output."""
    from resumetailor.db.repositories import upsert_master_resume
    import asyncio
    from resumetailor.core.errors import RenderError
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    leak = "rendercv failed (exit 1): Typst error at /app/backend/.venv/x.typ"
    sim.sim_llm.set_complete_response(json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML}))
    sim.sim_pdf_render.set_error(RenderError(leak))

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    error_data = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:") and "RENDER_FAILED" in l
    )
    assert error_data == {"error": RenderError.client_message, "code": "RENDER_FAILED"}
    assert leak not in response.text


@pytest.mark.anyio
async def test_generate_stream_unexpected_failure_says_nothing(client, sim, db_path):
    """An exception that is not a domain error has no vetted message to send."""
    from resumetailor.db.repositories import upsert_master_resume
    import asyncio
    from resumetailor.core.errors import BackendError
    await asyncio.to_thread(upsert_master_resume, db_path, MOCK_GENERATION_RESULT_YAML)

    sim.sim_llm.set_complete_error(ValueError("sqlite3.OperationalError: /app/db/app.db"))

    response = await client.post(
        "/api/resumes/stream",
        json={"job_description": "Software Engineer at Mock Corp"},
    )
    assert response.status_code == 200
    error_data = next(
        json.loads(l.replace("data: ", ""))
        for l in response.text.split("\n")
        if l.startswith("data:") and "GENERATION_FAILED" in l
    )
    assert error_data == {
        "error": BackendError.client_message,
        "code": "GENERATION_FAILED",
    }
    assert "/app/db/app.db" not in response.text


@pytest.mark.anyio
async def test_get_resume_404(client):
    response = await client.get("/api/resumes/9999")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_render_route_normalizes_first(client, sim, db_path):
    """D-57: the render-only path normalizes, like every other render path.

    Before this, `POST /api/resumes/{id}/render` handed the stored YAML to the
    renderer untouched, so a document that renders through the generation
    pipeline or through `/api/master-resume/preview` could fail here.
    """
    from resumetailor.db.repositories import create_resume
    import asyncio
    stored = "cv:\n  name: Tester\n  contact:\n    email: tester@example.com\n"
    r = await asyncio.to_thread(create_resume, db_path, "Test", "JD", stored)
    sim.sim_pdf_render.set_response(b"%PDF-1.4 test")

    response = await client.post(f"/api/resumes/{r.id}/render")
    assert response.status_code == 200
    rendered = sim.sim_pdf_render.last_yaml_content
    assert rendered != stored
    assert "contact:" not in rendered
    assert "email: tester@example.com" in rendered


@pytest.mark.anyio
async def test_patch_refuses_yaml_that_will_not_render(client, db_path):
    """D-04: a write path validates instead of storing and hoping."""
    from resumetailor.db.repositories import create_resume, get_resume
    import asyncio
    r = await asyncio.to_thread(create_resume, db_path, "Test", "JD", "cv:\n  name: X\n")

    response = await client.patch(
        f"/api/resumes/{r.id}", json={"yaml_content": "cv:\n  name: X\n  email: nope\n"}
    )
    assert response.status_code == 422
    assert "@-sign" in response.json()["detail"]
    row = await asyncio.to_thread(get_resume, db_path, r.id)
    assert row.yaml_content == "cv:\n  name: X\n", "the bad document was not stored"


@pytest.mark.anyio
async def test_patch_stores_valid_yaml_and_renames(client, db_path):
    from resumetailor.db.repositories import create_resume
    import asyncio
    r = await asyncio.to_thread(create_resume, db_path, "Test", "JD", "cv:\n  name: X\n")

    response = await client.patch(
        f"/api/resumes/{r.id}",
        json={"name": "Renamed", "yaml_content": "cv:\n  name: Y\n"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["yaml_content"] == "cv:\n  name: Y\n"


@pytest.mark.anyio
async def test_patch_a_name_alone_does_not_touch_the_document(client, db_path):
    from resumetailor.db.repositories import create_resume
    import asyncio
    stored = "cv:\n  name: X\n  bogus_key: stored before D-04\n"
    r = await asyncio.to_thread(create_resume, db_path, "Test", "JD", stored)

    response = await client.patch(f"/api/resumes/{r.id}", json={"name": "Renamed"})
    assert response.status_code == 200, "validation runs on the document, not the name"
    assert response.json()["yaml_content"] == stored


@pytest.mark.anyio
async def test_delete_resume(client, sim, db_path):
    from resumetailor.db.repositories import create_resume
    import asyncio
    r = await asyncio.to_thread(create_resume, db_path, "Test", "JD", "cv:\n  name: X")
    response = await client.delete(f"/api/resumes/{r.id}")
    assert response.status_code == 204
