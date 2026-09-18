"""The ASGI application: factory, lifespan, wiring.

The module-level ``app`` is what uvicorn serves (``resumetailor.main:app``) and
what the test client mounts. It is built by :func:`create_app`, which is the
only place that knows the assembly order:

1. configure logging, before anything else can fail silently;
2. install the rate limiter and the body-size cap, then the request-context
   middleware, so every line logged below them carries a request id and so
   does a refusal from either limiter (see ``install_security_middleware``);
3. install the domain error handlers;
4. register the routers;
5. replace the generated OpenAPI document with the corrected one, which needs
   every router already registered (see ``api/openapi.py``);
6. gate ``/docs``, ``/redoc`` and ``/openapi.json`` behind
   ``Settings.API_DOCS_ENABLED`` (PLAN.md D-58; see
   ``docs/adr/0006-docs-gated-by-setting.md``) — after step 5, since gating
   only removes the three routes FastAPI itself registers and does not touch
   the corrected document step 5 installed;
7. mount the frontend export last, because it claims ``/``.

Startup work that can fail on a misconfigured host — a missing API key, an
unwritable volume — happens in the lifespan, not at import, so a broken
configuration fails the boot with a legible error instead of failing the user's
first generation.

**Graceful shutdown and the orphan reaper (task 3.5)** are also wired from
here: see the ``lifespan`` docstring below.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from resumetailor.api.openapi import API_TITLE, install_openapi
from resumetailor.api.routers import (
    chat,
    evaluate,
    health,
    master_resume,
    metrics,
    resumes,
    rules,
    system_prompt,
)
from resumetailor.core import reaper
from resumetailor.core.config import (
    STATIC_DIR,
    Settings,
    get_settings,
    validate_startup_settings,
)
from resumetailor.core.errors import install_error_handlers
from resumetailor.core.logging import configure_logging
from resumetailor.core.metrics import sse_stream_tracker
from resumetailor.core.middleware import RequestContextMiddleware
from resumetailor.core.security import install_security_middleware
from resumetailor.deps import get_backend

# `get_backend` is re-exported: the route tests override it as a FastAPI
# dependency and have always imported it from here.
__all__ = ["app", "create_app", "get_backend", "lifespan"]

logger = logging.getLogger(__name__)

_ROUTER_MODULES = (
    health,
    master_resume,
    resumes,
    chat,
    rules,
    system_prompt,
    evaluate,
    metrics,
)


def _ensure_directories(settings: Settings) -> None:
    """Create the SQLite and PDF directories. Blocking; call in a thread."""
    Path(settings.PDFS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate configuration, lay out storage, migrate, seed, reap, serve.

    Migration replaces the old `init_db`, which re-ran a
    `CREATE TABLE IF NOT EXISTS` script on every boot and so applied no schema
    change to an existing database at all (D-02). A failure here fails the
    boot: a process that cannot bring its database to a known version has no
    business serving requests against it.

    **The orphan reaper (D-20)** runs once here, synchronously, before the
    process starts accepting requests — a corrupt or duplicated PDF from a
    previous crash should not be visible to the first request this boot
    serves — and then again on a timer (`Settings.REAPER_INTERVAL_S`) as a
    background task, for orphans a running process accumulates without
    crashing (a caller that disconnects mid-write, a full disk). See
    `core/reaper.py`.

    **Graceful shutdown.** After `yield`, in order: stop asking the periodic
    reaper to run again, then wait up to `Settings.GRACEFUL_SHUTDOWN_TIMEOUT_S`
    for every tracked SSE stream (`core/metrics.sse_stream_tracker`) to finish
    on its own. uvicorn has already stopped accepting new connections by the
    time this runs; without the wait, a generation mid-stream would be cut off
    the instant this function returns, because returning is what lets uvicorn
    close the remaining connections. A timeout is logged, not raised: the
    process is shutting down either way, and the alternative — blocking
    shutdown indefinitely on a client that will never read the rest of the
    stream — is worse than the connection drop this exists to avoid.
    """
    from resumetailor.db.migrate import migrate
    from resumetailor.db.seed import seed_defaults

    settings = get_settings()
    validate_startup_settings(settings)
    await asyncio.to_thread(_ensure_directories, settings)
    await asyncio.to_thread(migrate, settings.DB_PATH)
    await asyncio.to_thread(seed_defaults, settings.DB_PATH)
    await reaper.run_once(settings.DB_PATH, settings.PDFS_DIR, trigger="startup")
    reaper_task = reaper.start_background_task(
        settings.DB_PATH, settings.PDFS_DIR, settings.REAPER_INTERVAL_S
    )
    logger.info(
        "application ready",
        extra={"db_path": settings.DB_PATH, "llm_mock": settings.LLM_MOCK},
    )
    try:
        yield
    finally:
        await reaper.stop_background_task(reaper_task)
        if sse_stream_tracker.active:
            logger.info(
                "graceful shutdown: draining in-flight SSE streams",
                extra={"streams_active": sse_stream_tracker.active},
            )
        drained = await sse_stream_tracker.wait_drained(
            settings.GRACEFUL_SHUTDOWN_TIMEOUT_S
        )
        if not drained:
            logger.warning(
                "graceful shutdown: timed out waiting for SSE streams to drain",
                extra={"streams_active": sse_stream_tracker.active},
            )


def create_app() -> FastAPI:
    """Build the application. One call per process; see ``app`` below."""
    settings = get_settings()
    configure_logging(settings)

    # D-58 / ADR 0006: `/docs`, `/redoc` and `/openapi.json` are on by default
    # (`Settings.API_DOCS_ENABLED`) and off together when it is false. FastAPI
    # takes this as three constructor arguments, not a post-hoc toggle, so it
    # has to happen here rather than after the document is built below.
    docs_url = "/docs" if settings.API_DOCS_ENABLED else None
    redoc_url = "/redoc" if settings.API_DOCS_ENABLED else None
    openapi_url = "/openapi.json" if settings.API_DOCS_ENABLED else None
    app = FastAPI(
        title=API_TITLE,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    # Order is load-bearing. `add_middleware` inserts at the front of the
    # stack, so the *last* one added is the outermost: the rate limiter and the
    # body cap go on first precisely so that the request-context middleware
    # ends up outside them and a 429 or 413 still carries a request id.
    install_security_middleware(app)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    for module in _ROUTER_MODULES:
        app.include_router(module.router)

    # After the routers, because it reads `app.routes`: the three streaming
    # routes have no `response_model` to generate a 200 from, so their bodies
    # are described from `api/schemas/sse.py` instead (D-54, D-55).
    install_openapi(app)

    # Mounted last: `/` with html=True matches everything the routers did not.
    # Absent in a source checkout that has never built the frontend.
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()
