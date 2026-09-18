# backend/src/resumetailor/api/schemas/health.py
"""The liveness and readiness probes' bodies (PLAN.md D-58).

Two models, not one, because they answer two different questions. Before task
3.5 there was one static `{"status": "ok"}` that answered neither: it "touches
nothing, so a container with a corrupt database reports itself healthy."

* :class:`HealthResponse` — liveness. "Is the process able to answer HTTP at
  all." Unconditional: it cannot depend on the database, because a database
  outage is exactly the condition an orchestrator needs liveness to survive
  (restarting a process whose own database is down does not fix the database
  and creates a restart loop).
* :class:`ReadinessResponse` — readiness. "Can this process actually do its
  job right now." Checks the dependencies liveness deliberately does not.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

__all__ = ["CheckResult", "HealthResponse", "ReadinessResponse"]


class HealthResponse(BaseModel):
    """The process is up and serving. Says nothing about its dependencies."""

    status: Literal["ok"]


class CheckResult(BaseModel):
    """One dependency's readiness check."""

    ok: bool
    #: Present only when `ok` is false. Operator-facing, like `BackendError`'s
    #: `.detail`: short enough to log inline, never sensitive, since it is
    #: about a filesystem path or a SQLite error, not a request the process is
    #: handling.
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Whether this process can currently serve a real request.

    `checks` is always both keys, whether or not they passed, so a caller can
    tell "the database check failed" from "the database check never ran."
    """

    status: Literal["ok", "unavailable"]
    checks: dict[str, CheckResult]
