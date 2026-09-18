"""
Shared pytest configuration and fixtures.

Sets up sys.modules stubs for litellm (not installed until Wave 2 adds
pyproject.toml) so that adapters.py compiles and adapter error-mapping
tests work without the real library present.

Also provides the per-test settings isolation (`isolated_settings`) plus the
`db_path`, `sim` and `client` fixtures used by the route unit tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Stub out litellm with real exception classes so adapters.py compiles and
# exception-mapping tests can raise/catch properly.
# ---------------------------------------------------------------------------

class _AuthenticationError(Exception):
    def __init__(self, message: str = "", *, llm_provider: str = "", model: str = "", **kw: object) -> None:
        super().__init__(message)


class _RateLimitError(Exception):
    def __init__(self, message: str = "", *, llm_provider: str = "", model: str = "", **kw: object) -> None:
        super().__init__(message)


class _ServiceUnavailableError(Exception):
    def __init__(self, message: str = "", **kw: object) -> None:
        super().__init__(message)


class _APIConnectionError(Exception):
    def __init__(self, message: str = "", **kw: object) -> None:
        super().__init__(message)


# Build the fake litellm.exceptions sub-module.
_exc_module = ModuleType("litellm.exceptions")
_exc_module.AuthenticationError = _AuthenticationError  # type: ignore[attr-defined]
_exc_module.RateLimitError = _RateLimitError  # type: ignore[attr-defined]
_exc_module.ServiceUnavailableError = _ServiceUnavailableError  # type: ignore[attr-defined]
_exc_module.APIConnectionError = _APIConnectionError  # type: ignore[attr-defined]

# Build the fake litellm top-level module.
_litellm_module = ModuleType("litellm")
_litellm_module.exceptions = _exc_module  # type: ignore[attr-defined]
_litellm_module.acompletion = MagicMock()  # replaced per-test via patch()

sys.modules.setdefault("litellm", _litellm_module)
sys.modules.setdefault("litellm.exceptions", _exc_module)


# ---------------------------------------------------------------------------
# Per-test settings isolation
#
# `resumetailor.core.config.get_settings` and `resumetailor.deps._backend` are both `lru_cache`d, so a
# Settings object built inside one test stays live for every test that follows.
# Tests used to paper over that by calling `cache_clear()` on entry, which still
# leaked a Settings pointing at a deleted `tmp_path` into the *next* test and
# made the suite order-dependent (D-37).
#
# This autouse fixture is the only place that touches those caches: it points
# every test at its own temp DB and PDF directory and clears both caches on the
# way in AND on the way out, so no test can inherit or leak configuration and no
# test has to remember to clear anything.
# ---------------------------------------------------------------------------

class IsolatedSettings(NamedTuple):
    db_path: Path
    pdfs_dir: Path


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    from resumetailor.core.config import get_settings
    from resumetailor.deps import _backend

    db_path = tmp_path / "test.db"
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("PDFS_DIR", str(pdfs_dir))

    get_settings.cache_clear()
    _backend.cache_clear()
    try:
        yield IsolatedSettings(db_path=db_path, pdfs_dir=pdfs_dir)
    finally:
        get_settings.cache_clear()
        _backend.cache_clear()


@pytest.fixture
def db_path(isolated_settings) -> str:
    """This test's own SQLite database, schema applied and defaults seeded."""
    from resumetailor.database import init_db

    path = str(isolated_settings.db_path)
    init_db(path)
    return path


@pytest.fixture
def pdfs_dir(isolated_settings) -> str:
    """This test's own PDF output directory."""
    return str(isolated_settings.pdfs_dir)


# ---------------------------------------------------------------------------
# Wave 2: Route unit test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sim():
    from tests.helpers.simulator import ConfigurableBackendAPI
    return ConfigurableBackendAPI()


@pytest.fixture
async def client(sim, db_path):
    # `db_path` is requested (not just autouse-ordered) so that the app under
    # test always has an initialised database behind it: httpx's ASGITransport
    # does not run the FastAPI lifespan that would otherwise create one.
    from resumetailor.main import app, get_backend
    app.dependency_overrides[get_backend] = lambda: sim
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
