import pytest

from resumetailor.api.routers.health import _check_database, _check_pdfs_dir


@pytest.mark.anyio
async def test_health_returns_200(client):
    """Liveness: unconditional, unaffected by the database or PDFS_DIR."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_ready_returns_200_when_dependencies_are_up(client, db_path, pdfs_dir):
    """Readiness (D-58): both checks pass against the test harness's real
    database and PDFS_DIR, the same as production."""
    response = await client.get("/api/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == {"ok": True, "detail": None}
    assert body["checks"]["pdfs_dir"] == {"ok": True, "detail": None}


def test_check_database_ok_against_a_real_database(db_path: str):
    result = _check_database(db_path)
    assert result.ok is True
    assert result.detail is None


def test_check_database_fails_against_a_path_with_no_database(tmp_path):
    result = _check_database(str(tmp_path / "does-not-exist" / "db.sqlite3"))
    assert result.ok is False
    assert result.detail is not None


def test_check_pdfs_dir_ok_when_present_and_writable(pdfs_dir: str):
    result = _check_pdfs_dir(pdfs_dir)
    assert result.ok is True
    assert result.detail is None


def test_check_pdfs_dir_fails_when_missing(tmp_path):
    result = _check_pdfs_dir(str(tmp_path / "never-created"))
    assert result.ok is False
    assert result.detail is not None
    assert "does not exist" in result.detail


@pytest.mark.anyio
async def test_ready_returns_503_when_a_dependency_check_fails(
    client, monkeypatch: pytest.MonkeyPatch
):
    """A corrupt or unreachable dependency is unavailable, with detail per check.

    Monkeypatches the route's own check function rather than the database
    file, since corrupting a live SQLite file mid-suite is exactly the kind of
    shared, order-sensitive state the harness in `conftest.py` exists to rule
    out. What is under test is the route's response shape, not SQLite's
    corruption behaviour.
    """
    import resumetailor.api.routers.health as health_module
    from resumetailor.api.schemas.health import CheckResult

    monkeypatch.setattr(
        health_module,
        "_check_database",
        lambda _db_path: CheckResult(ok=False, detail="disk I/O error"),
    )

    response = await client.get("/api/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == {"ok": False, "detail": "disk I/O error"}
    assert body["checks"]["pdfs_dir"]["ok"] is True
