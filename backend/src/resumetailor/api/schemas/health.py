"""The liveness probe's body.

One field, and it still earns a model: without one the OpenAPI document
described this response as ``{}`` like every other route (D-54), and the
generated client had no way to know the key is called ``status``.

``Literal["ok"]`` rather than ``str`` because that is the whole of the current
contract: the route is unconditional and cannot answer anything else. Task 3.3
splits liveness from readiness and will widen this; until it does, a wider type
would document a state the server cannot reach.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

__all__ = ["HealthResponse"]


class HealthResponse(BaseModel):
    """The process is up and serving. Says nothing about its dependencies."""

    status: Literal["ok"]
