import pytest


@pytest.mark.anyio
async def test_get_rules_returns_defaults(client):
    response = await client.get("/api/rules")
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) > 0
    assert any(
        r["section"] == "experience" and r["rule_key"] == "max_entries" for r in rules
    )


@pytest.mark.anyio
async def test_put_rules_updates(client):
    response = await client.put(
        "/api/rules",
        json={
            "rules": [
                {"section": "experience", "rule_key": "max_entries", "rule_value": "3"}
            ]
        },
    )
    assert response.status_code == 200
    rules = response.json()
    exp = next(
        r
        for r in rules
        if r["section"] == "experience" and r["rule_key"] == "max_entries"
    )
    assert exp["rule_value"] == "3"


@pytest.mark.anyio
async def test_put_rules_rejects_malformed_payload(client):
    response = await client.put(
        "/api/rules",
        json={
            "rules": [{"section": "experience"}]  # missing rule_key / rule_value
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_put_rules_rejects_oversized_field(client):
    response = await client.put(
        "/api/rules",
        json={
            "rules": [
                {
                    "section": "experience",
                    "rule_key": "max_entries",
                    "rule_value": "x" * 201,
                }
            ]
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_put_rules_rejects_oversized_list(client):
    response = await client.put(
        "/api/rules",
        json={
            "rules": [
                {"section": "experience", "rule_key": f"rule_{i}", "rule_value": "1"}
                for i in range(51)
            ]
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_delete_rules_resets(client):
    await client.put(
        "/api/rules",
        json={
            "rules": [
                {"section": "experience", "rule_key": "max_entries", "rule_value": "99"}
            ]
        },
    )
    response = await client.delete("/api/rules")
    assert response.status_code == 200
    rules = response.json()
    exp = next(
        r
        for r in rules
        if r["section"] == "experience" and r["rule_key"] == "max_entries"
    )
    assert exp["rule_value"] == "2"
