"""Request id, request timing, and the access log.

Written as raw ASGI rather than as a Starlette ``BaseHTTPMiddleware``. Three of
this application's routes are SSE generators that stay open for the length of a
generation; ``BaseHTTPMiddleware`` runs the downstream app in a task group and
pumps the body through a memory stream, which changes when a chunk reaches the
client and how cancellation propagates. This middleware only wraps ``send``, so
a token still leaves the process the moment the route yields it.

PLAN.md D-52 asked for logs that can be attributed. The id chain is:

    client / proxy sets X-Request-Id
        -> middleware puts it in the contextvar and echoes it on the response
        -> every log line emitted while handling the request carries it
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.datastructures import MutableHeaders

from resumetailor.core.logging import request_id_var

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("resumetailor.access")

REQUEST_ID_HEADER = "x-request-id"

#: Paths that would otherwise fill the log with one line every few seconds.
#: The container healthcheck hits /api/health on a 30s interval.
_QUIET_PATHS = frozenset({"/api/health"})


class RequestContextMiddleware:
    """Assign a request id, time the request, and log one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _inbound_request_id(scope) or uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            path = scope.get("path", "")
            level = logging.DEBUG if path in _QUIET_PATHS else logging.INFO
            logger.log(
                level,
                "%s %s %s",
                scope.get("method", "-"),
                path,
                status,
                extra={
                    "http_method": scope.get("method", "-"),
                    "http_path": path,
                    "http_status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(token)


def _inbound_request_id(scope: Scope) -> str | None:
    """Return a caller-supplied request id, if it looks like one.

    An id from outside is only useful for correlating with whatever sent it, so
    it is length-capped and stripped rather than trusted: it ends up in every
    log line this request writes.
    """
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.decode("latin-1").lower() != REQUEST_ID_HEADER:
            continue
        value = raw_value.decode("latin-1").strip()[:128]
        return value or None
    return None
