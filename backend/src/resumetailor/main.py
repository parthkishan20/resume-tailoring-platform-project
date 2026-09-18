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
5. mount the frontend export last, because it claims ``/``.

Startup work that can fail on a misconfigured host — a missing API key, an
unwritable volume — happens in the lifespan, not at import, so a broken
configuration fails the boot with a legible error instead of failing the user's
first generation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from resumetailor.api.routers import (
    chat,
    evaluate,
    health,
    master_resume,
    resumes,
    rules,
    system_prompt,
)
from resumetailor.core.config import (
    STATIC_DIR,
    Settings,
    get_settings,
    validate_startup_settings,
)
from resumetailor.core.errors import install_error_handlers
from resumetailor.core.logging import configure_logging
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
)


def _ensure_directories(settings: Settings) -> None:
    """Create the SQLite and PDF directories. Blocking; call in a thread."""
    Path(settings.PDFS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate configuration, lay out storage, migrate, seed.

    Migration replaces the old `init_db`, which re-ran a
    `CREATE TABLE IF NOT EXISTS` script on every boot and so applied no schema
    change to an existing database at all (D-02). A failure here fails the
    boot: a process that cannot bring its database to a known version has no
    business serving requests against it.
    """
    from resumetailor.db.migrate import migrate
    from resumetailor.db.seed import seed_defaults

    settings = get_settings()
    validate_startup_settings(settings)
    await asyncio.to_thread(_ensure_directories, settings)
    await asyncio.to_thread(migrate, settings.DB_PATH)
    await asyncio.to_thread(seed_defaults, settings.DB_PATH)
    logger.info(
        "application ready",
        extra={"db_path": settings.DB_PATH, "llm_mock": settings.LLM_MOCK},
    )
    yield


def create_app() -> FastAPI:
    """Build the application. One call per process; see ``app`` below."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(title="ResumeTailor API", lifespan=lifespan)
    # Order is load-bearing. `add_middleware` inserts at the front of the
    # stack, so the *last* one added is the outermost: the rate limiter and the
    # body cap go on first precisely so that the request-context middleware
    # ends up outside them and a 429 or 413 still carries a request id.
    install_security_middleware(app)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    for module in _ROUTER_MODULES:
        app.include_router(module.router)

    # Mounted last: `/` with html=True matches everything the routers did not.
    # Absent in a source checkout that has never built the frontend.
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()
