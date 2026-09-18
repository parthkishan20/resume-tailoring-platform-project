import pytest
from resumetailor.llm.stub import MOCK_IMPORT_YAML


@pytest.mark.anyio
async def test_get_master_resume_404_when_empty(client):
    response = await client.get("/api/master-resume")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_put_master_resume_creates(client):
    response = await client.put(
        "/api/master-resume",
        json={"yaml_content": "cv:\n  name: Test"}
    )
    assert response.status_code == 200
    assert response.json()["yaml_content"] == "cv:\n  name: Test"


@pytest.mark.anyio
async def test_put_master_resume_refuses_a_document_that_will_not_render(client):
    """Regression for D-04's PUT half.

    `PATCH /api/resumes/{id}` already refused an invalid document (task 2.5);
    this route stored one first and only failed later, at
    `GET /api/master-resume/preview` or the next `POST /api/resumes/stream`.
    """
    response = await client.put(
        "/api/master-resume",
        json={"yaml_content": "cv:\n  name: [not, a, mapping]"},
    )
    assert response.status_code == 422
    assert "not valid" in response.json()["detail"]

    # And the row is not silently stored anyway.
    get_response = await client.get("/api/master-resume")
    assert get_response.status_code == 404


@pytest.mark.anyio
async def test_delete_master_resume(client):
    await client.put("/api/master-resume", json={"yaml_content": "cv:\n  name: Test"})
    response = await client.delete("/api/master-resume")
    assert response.status_code == 204


@pytest.mark.anyio
async def test_preview_master_resume(client, sim):
    # First save a master resume
    await client.put("/api/master-resume", json={"yaml_content": "cv:\n  name: Test"})
    # Then preview it
    response = await client.get("/api/master-resume/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


@pytest.mark.anyio
async def test_preview_master_resume_not_found(client):
    response = await client.get("/api/master-resume/preview")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_import_pdf_returns_yaml(client, sim):
    sim.sim_pdf_extract.set_response("John Doe\nEngineer at Corp")
    sim.sim_llm.set_complete_response(
        '{"yaml_content": "cv:\\n  name: John Doe"}'
    )
    import io
    fake_pdf = b"%PDF-1.4 test"
    response = await client.post(
        "/api/master-resume/import",
        files={"file": ("resume.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "yaml_content" in data
