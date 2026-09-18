"""The hermetic test harness.

A test suite is only worth the trust you put in it, and a suite that can reach
the network, read a developer's ``.env``, or inherit the previous test's
database can pass for reasons that have nothing to do with the code. This file
removes every one of those routes, for every test, without any test having to
opt in.

What every test gets, automatically
-----------------------------------
Four autouse fixtures run around each test, in this order:

1. ``pristine_env`` — snapshots ``os.environ`` and restores it afterwards, key
   by key. Production code that writes to the environment (``LiteLLMAdapter``
   sets ``OPENAI_API_KEY`` in its constructor) cannot leak into the next test,
   or out of the session.
2. ``isolated_settings`` — pins **every** field of ``Settings`` to a test value
   and clears the ``lru_cache`` on ``get_settings`` and ``deps._backend`` on the
   way in *and* on the way out. Pinning all of them is what makes ``backend/.env``
   irrelevant: environment variables win over the dotenv file, so a developer
   with a real key on disk runs the same suite CI does.
3. ``no_network`` — replaces ``socket.connect`` and friends with a guard that
   raises. Any test that reaches for the network fails loudly and names the
   address it wanted, instead of passing slowly on a good day and flaking on a
   bad one.
4. ``clean_dependency_overrides`` — restores FastAPI's override table, so a test
   that installs a dependency override cannot change what the next test sees.

There is no opt-out, and none is needed: nothing in this project legitimately
requires the network or a shared database.

No ports are bound
------------------
Route tests run the ASGI application in-process through
``httpx.ASGITransport``. No socket is opened, no port is claimed, and any
number of test sessions can run concurrently on one machine. If a future test
genuinely needs to bind — a subprocess server, say — it must ask the OS for a
free port (``socket.bind(("127.0.0.1", 0))``) rather than hardcoding one, and
the ``no_network`` guard above will need an explicit, documented exemption.

Writing a new test against this harness
---------------------------------------
Pick the smallest fixture that does the job.

* **Pure function, no I/O** — ask for nothing. The autouse fixtures still run.
* **Needs a database** — ask for ``db_path``. It is a ``str`` path to this
  test's own SQLite file under ``tmp_path``, schema applied and defaults
  seeded. It is deleted with the temp directory; there is no shared database
  and no reset step to remember.
* **Needs to call the API** — ask for ``client`` (an ``httpx.AsyncClient``) and
  mark the test ``@pytest.mark.anyio``. The application's real lifespan runs,
  so the test boots the way production does.
* **Needs to control what the LLM said** — ask for ``sim`` alongside ``client``
  and pin the ports:
  ``sim.sim_llm.set_complete_response(...)``, ``set_complete_error(...)``,
  ``set_stream_chunks([...])``, ``sim.sim_pdf_render.set_response(b"...")``.
  Leave a port unset and it answers from the canned table in
  ``tests.helpers.llm_stub``, deterministically.
* **Needs real PDF bytes** — ask for ``mock_pdf_bytes``.
* **Needs the LLM stub on its own**, outside the API — ask for
  ``deterministic_llm``.

Assert on what was *asked*, not only on what came back:
``sim.sim_llm.complete_call_count`` and ``sim.sim_llm.last_complete_messages``
are what pin the two-pass pipeline and the rules injection.

Concurrent-restructure note
---------------------------
Written against the post-1.1 src layout. Tasks 1.2 and 1.3 are moving
``resumetailor.database``, ``resumetailor.deps`` and ``resumetailor.simulator``
in parallel worktrees, so the imports below are deferred into the fixture
bodies: an import inside a function is one line to re-point, and it keeps a
module move from breaking collection of the entire suite at once. The precise
list of what will need re-pointing is in the 1.5 report.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest
from httpx import ASGITransport, AsyncClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Every field of `Settings`, pinned. Anything absent here would fall through to
# `backend/.env` on a developer machine and to the field default in CI, which
# are two different test runs wearing the same name.
TEST_ENV: dict[str, str] = {
    # Never a real key. `validate_startup_settings` only checks that a key is
    # present, and nothing in the suite may reach a provider, so a sentinel is
    # both sufficient and self-documenting in a traceback.
    "OPENAI_API_KEY": "test-key-not-a-real-credential",
    "LLM_MODEL": "test/model",
    "LLM_MOCK": "true",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "text",
}


class NetworkAccessError(RuntimeError):
    """Raised when a test tries to open a connection off this machine."""


class IsolatedSettings(NamedTuple):
    db_path: Path
    pdfs_dir: Path


# ── Autouse: environment ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def pristine_env() -> Iterator[None]:
    """Restore ``os.environ`` exactly as it was, after every test.

    ``monkeypatch.setenv`` covers what the *test* sets. This covers what the
    *code under test* sets: ``LiteLLMAdapter.__init__`` assigns
    ``os.environ["OPENAI_API_KEY"]``, which before this fixture existed
    overwrote the variable for the rest of the session.
    """
    snapshot = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


@pytest.fixture(autouse=True)
def isolated_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[IsolatedSettings]:
    """This test's own configuration, and nobody else's.

    ``get_settings`` and ``deps._backend`` are both ``lru_cache``d, so a
    ``Settings`` object built inside one test would otherwise stay live for
    every test that follows — the defect behind D-37, where the suite passed in
    file order and failed under any other. Clearing on the way *out* as well as
    on the way in is the half that fixes it: no test can inherit configuration,
    and no test has to remember to clear anything.
    """
    from resumetailor.core.config import get_settings
    from resumetailor.deps import _backend

    db_path = tmp_path / "test.db"
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("PDFS_DIR", str(pdfs_dir))

    get_settings.cache_clear()
    _backend.cache_clear()
    try:
        yield IsolatedSettings(db_path=db_path, pdfs_dir=pdfs_dir)
    finally:
        get_settings.cache_clear()
        _backend.cache_clear()


# ── Autouse: no network ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make an outbound connection impossible, and loud when attempted.

    AF_UNIX sockets are left alone: the asyncio event loop uses a socket pair
    for its self-pipe, and blocking that would break the loop rather than the
    test. Only IP connections are refused, which is the whole of "the network"
    for this suite's purposes.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    blocked_families = {socket.AF_INET, socket.AF_INET6}

    def _refuse(where: str, address: object) -> NetworkAccessError:
        msg = (
            f"Test tried to reach {address!r} via {where}. Tests run without "
            "network access. Stub the call at the port boundary instead - see "
            "the `sim` fixture in tests/conftest.py."
        )
        return NetworkAccessError(msg)

    def guarded_connect(self: socket.socket, address: object) -> None:
        if self.family in blocked_families:
            error = _refuse("socket.connect", address)
            raise error
        real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: object) -> int:
        if self.family in blocked_families:
            error = _refuse("socket.connect_ex", address)
            raise error
        return real_connect_ex(self, address)

    def guarded_create_connection(address: object, *args: object, **kw: object) -> None:
        error = _refuse("socket.create_connection", address)
        raise error

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


# ── Storage ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(isolated_settings: IsolatedSettings) -> str:
    """This test's own SQLite database, schema applied and defaults seeded.

    A file rather than ``:memory:`` on purpose: the code under test opens the
    database by path, on a worker thread, more than once per request. An
    in-memory database would be a different database on each connection.
    """
    from resumetailor.database import init_db

    path = str(isolated_settings.db_path)
    init_db(path)
    return path


@pytest.fixture
def pdfs_dir(isolated_settings: IsolatedSettings) -> str:
    """This test's own PDF output directory."""
    return str(isolated_settings.pdfs_dir)


# ── Deterministic LLM ───────────────────────────────────────────────────────


@pytest.fixture
def deterministic_llm():
    """The canned-response LLM stub, standalone.

    Use this to exercise something that takes an ``LLMPort`` directly. For a
    test that goes through the API, use ``sim`` instead — it wraps this same
    canned table and adds per-port error injection.
    """
    from tests.helpers.llm_stub import DeterministicLLM

    return DeterministicLLM()


@pytest.fixture
def sim():
    """The backend facade with every port stubbed and pinnable. See ``client``."""
    from tests.helpers.simulator import ConfigurableBackendAPI

    return ConfigurableBackendAPI()


@pytest.fixture
def mock_pdf_bytes() -> bytes:
    """The committed fixture PDF, as bytes.

    Note for whoever picks this up: the file is a single blank page (P1-6 in
    ``docs/reports/audit-tests.md``), so an assertion on its *content* will not
    hold until it is regenerated from a real render. Task 1.3 owns moving this
    file into the package; regenerating it belongs with that move.
    """
    return (FIXTURES_DIR / "mock.pdf").read_bytes()


# ── API ─────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_dependency_overrides() -> Iterator[None]:
    """Leave FastAPI's override table the way we found it."""
    from resumetailor.main import app

    saved = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


@pytest.fixture
async def client(sim, db_path: str):
    """An HTTP client against the application, in-process, with a stub backend.

    The real lifespan runs, so the test exercises the same startup path
    production does: configuration is validated, the storage layout is created,
    and the schema is applied. ``httpx.ASGITransport`` does not do this on its
    own, which is why every route test used to hand-roll ``init_db`` and why one
    of them forgot (P0-1).
    """
    from resumetailor.main import app, get_backend, lifespan

    app.dependency_overrides[get_backend] = lambda: sim
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
