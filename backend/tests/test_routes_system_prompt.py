import pytest


@pytest.mark.anyio
async def test_get_system_prompt(client):
    response = await client.get("/api/system-prompt")
    assert response.status_code == 200
    assert "content" in response.json()


@pytest.mark.anyio
async def test_put_system_prompt(client):
    response = await client.put("/api/system-prompt", json={"content": "Custom prompt"})
    assert response.status_code == 200
    assert response.json()["content"] == "Custom prompt"
