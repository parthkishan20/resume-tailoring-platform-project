import pytest

from resumetailor.api.routers.health import (
    _DATABASE_CHECK_FAILED,
    _PDFS_DIR_CHECK_FAILED,
    _check_database,
    _check_pdfs_dir,
)


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
    """D-79: the client gets the fixed, opaque message, never `str(exc)`."""
    bad_path = str(tmp_path / "does-not-exist" / "db.sqlite3")
    result = _check_database(bad_path)
    assert result.ok is False
    assert result.detail == _DATABASE_CHECK_FAILED
    assert bad_path not in (result.detail or "")


def test_check_pdfs_dir_ok_when_present_and_writable(pdfs_dir: str):
    result = _check_pdfs_dir(pdfs_dir)
    assert result.ok is True
    assert result.detail is None


def test_check_pdfs_dir_fails_when_missing(tmp_path):
    """D-79: the client gets the fixed, opaque message, never the raw path."""
    missing_dir = str(tmp_path / "never-created")
    result = _check_pdfs_dir(missing_dir)
    assert result.ok is False
    assert result.detail == _PDFS_DIR_CHECK_FAILED
    assert missing_dir not in (result.detail or "")


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


@pytest.mark.anyio
async def test_ready_response_omits_the_raw_path_on_a_real_pdfs_dir_failure(
    client, db_path, pdfs_dir
):
    """D-79 end to end: a real, unmocked failure still reaches the client opaque.

    Removes the harness's actual `PDFS_DIR` rather than monkeypatching the
    check function, so this exercises the same code path production hits, not
    a canned substitute.
    """
    import shutil

    shutil.rmtree(pdfs_dir)

    response = await client.get("/api/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["pdfs_dir"] == {"ok": False, "detail": _PDFS_DIR_CHECK_FAILED}
    assert pdfs_dir not in response.text
