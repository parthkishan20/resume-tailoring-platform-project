# backend/src/resumetailor/api/routers/health.py
"""Liveness and readiness (PLAN.md D-58). See `api/schemas/health.py`.

**D-79.** `_check_database` and `_check_pdfs_dir` used to put `str(exc)` and an
absolute filesystem path straight into `CheckResult.detail`, reaching any
unauthenticated caller of `/api/health/ready`. Same disclosure category D-53
closed everywhere else: the client now gets a fixed, check-specific message,
and the real detail is logged server-side at ERROR with the request id
`core/logging.py` attaches, the same split `core/errors.py` uses for
`BackendError.client_message` versus `.detail`.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from resumetailor.api.schemas.health import (
    CheckResult,
    HealthResponse,
    ReadinessResponse,
)
from resumetailor.core.config import get_settings
from resumetailor.db.engine import session

logger = logging.getLogger(__name__)

router = APIRouter()

_DATABASE_CHECK_FAILED = "The database check failed."
_PDFS_DIR_CHECK_FAILED = "The PDFs directory check failed."


@router.get("/api/health", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """The process is up and can answer HTTP. Touches nothing else.

    Deliberately does not check the database: an orchestrator that restarts a
    process on a *liveness* failure is trying to recover from a stuck or
    deadlocked process, and a database outage is not that — restarting this
    process fixes nothing and produces a restart loop instead. See
    `/api/health/ready` for the check that does look at dependencies.
    """
    return {"status": "ok"}


def _check_database(db_path: str) -> CheckResult:
    try:
        with session(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        logger.exception(
            "readiness check failed: database",
            extra={"check": "database", "error_detail": str(exc)},
        )
        return CheckResult(ok=False, detail=_DATABASE_CHECK_FAILED)
    return CheckResult(ok=True)


def _check_pdfs_dir(pdfs_dir: str) -> CheckResult:
    directory = Path(pdfs_dir)
    if not directory.is_dir():
        logger.error(
            "readiness check failed: pdfs_dir",
            extra={"check": "pdfs_dir", "error_detail": f"{directory} does not exist"},
        )
        return CheckResult(ok=False, detail=_PDFS_DIR_CHECK_FAILED)
    if not os.access(directory, os.W_OK):
        logger.error(
            "readiness check failed: pdfs_dir",
            extra={"check": "pdfs_dir", "error_detail": f"{directory} is not writable"},
        )
        return CheckResult(ok=False, detail=_PDFS_DIR_CHECK_FAILED)
    return CheckResult(ok=True)


@router.get(
    "/api/health/ready",
    response_model=ReadinessResponse,
    responses={
        503: {
            "model": ReadinessResponse,
            "description": (
                "At least one dependency check failed. Same body shape as "
                "the 200, with the failing entries' `ok` false."
            ),
        }
    },
)
async def ready() -> JSONResponse:
    """Can this process serve a real request right now.

    Checks the database (a real query, not "is the file present" — D-58's
    motivating case is a *corrupt* database, which opens fine and fails on the
    first statement) and `PDFS_DIR` (present and writable, since every
    generation ends in a write there). Both run inline rather than through
    `asyncio.to_thread`: each is a handful of milliseconds and a readiness
    probe that itself spawns a thread per poll is not simpler than one that
    blocks the loop for a few milliseconds every few seconds.
    """
    settings = get_settings()
    checks = {
        "database": _check_database(settings.DB_PATH),
        "pdfs_dir": _check_pdfs_dir(settings.PDFS_DIR),
    }
    healthy = all(check.ok for check in checks.values())
    body = ReadinessResponse(status="ok" if healthy else "unavailable", checks=checks)
    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())
