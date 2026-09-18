"""Request id, request timing, the access log, and the two per-request limits.

Every middleware here is written as raw ASGI rather than as a Starlette
``BaseHTTPMiddleware``. Three of this application's routes are SSE generators
that stay open for the length of a generation; ``BaseHTTPMiddleware`` runs the
downstream app in a task group and pumps the body through a memory stream,
which changes when a chunk reaches the client and how cancellation propagates.
:class:`RequestContextMiddleware` only wraps ``send``, so a token still leaves
the process the moment the route yields it, and the two limiters below wrap
``receive`` or answer before the app is called at all.

PLAN.md D-52 asked for logs that can be attributed. The id chain is:

    client / proxy sets X-Request-Id
        -> middleware puts it in the contextvar and echoes it on the response
        -> every log line emitted while handling the request carries it

Task 2.4 added :class:`RateLimitMiddleware` (D-28's cost half) and
:class:`BodySizeLimitMiddleware` (D-47). The policy they enforce — which paths,
what limits, read from where — lives in ``core/security.py``; only the
enforcement is here. They are installed by
``security.install_security_middleware``, which documents the stack order and
why it matters.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.datastructures import MutableHeaders

from resumetailor.core.errors import (
    RateLimitedError,
    RequestTooLargeError,
    error_response,
)
from resumetailor.core.logging import request_id_var
from resumetailor.core.metrics import record_request
from resumetailor.core.security import (
    RATE_LIMITED_PATHS,
    UPLOAD_PATHS,
    client_key,
    get_rate_limiter,
    get_security_policy,
    retry_after_seconds,
)

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("resumetailor.access")

#: Separate from the access log: a refusal is an event an operator wants to
#: find on its own, not a line to grep out of every request ever served.
security_logger = logging.getLogger("resumetailor.security")

REQUEST_ID_HEADER = "x-request-id"

#: Paths that would otherwise fill the log with one line every few seconds.
#: The container healthcheck hits /api/health on a 30s interval; a readiness
#: probe and a metrics scraper poll on a similar cadence (PLAN.md D-58).
_QUIET_PATHS = frozenset({"/api/health", "/api/health/ready", "/api/metrics"})


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
            method = scope.get("method", "-")
            duration_s = time.perf_counter() - started
            level = logging.DEBUG if path in _QUIET_PATHS else logging.INFO
            logger.log(
                level,
                "%s %s %s",
                method,
                path,
                status,
                extra={
                    "http_method": method,
                    "http_path": path,
                    "http_status": status,
                    "duration_ms": round(duration_s * 1000, 2),
                },
            )
            # The *route template* (`/api/resumes/{resume_id}`), not `path`:
            # a metrics label is a low-cardinality dimension, and one series
            # per resume id would not be. `scope["route"]` is set in place by
            # Starlette's router, deeper in the chain `self.app` just
            # returned from, so it is populated here whenever a route
            # matched; a 404 with no match falls back to "unmatched" rather
            # than the raw path, for the same cardinality reason.
            route = scope.get("route")
            path_label = route.path if route is not None else "unmatched"
            record_request(
                method=method, path=path_label, status=status, duration_s=duration_s
            )
            request_id_var.reset(token)


class RateLimitMiddleware:
    """Refuse a client that is spending the owner's provider credits too fast.

    Applies to the four paths in ``security.RATE_LIMITED_PATHS`` and to nothing
    else: reading a resume or listing the library costs a SQLite query, and
    rate-limiting those would only make the UI worse. The bill comes from the
    endpoints that call a provider.

    The check happens before the app is called, so a refused request never
    reaches the route, never opens an SSE stream, and never has its body read.
    On refusal the client gets the normal error envelope with code
    ``RATE_LIMITED``, a 429, and a ``Retry-After`` in whole seconds.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in RATE_LIMITED_PATHS:
            await self.app(scope, receive, send)
            return

        policy = get_security_policy()
        if not policy.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        key = client_key(scope.get("client"))
        wait = get_rate_limiter().check(key)
        if wait <= 0.0:
            await self.app(scope, receive, send)
            return

        retry_after = retry_after_seconds(wait)
        error = RateLimitedError(
            f"rate limit exceeded for {key} on {scope.get('path')}; "
            f"retry after {retry_after}s"
        )
        security_logger.warning(
            "rate limited: %s",
            scope.get("path"),
            extra={
                "error_code": error.code,
                "http_path": scope.get("path"),
                "client": key,
                "retry_after_s": retry_after,
            },
        )
        response = error_response(error)
        response.headers["Retry-After"] = str(retry_after)
        await response(scope, receive, send)


class BodySizeLimitMiddleware:
    """Cap the request body, before it is buffered anywhere.

    Starlette applies no body size limit of its own, so until this existed a
    50 MB POST was read, parsed and persisted (PLAN.md D-47), and a 2 GB upload
    to ``/api/master-resume/import`` could exhaust the container's memory
    (D-48). Two checks, both on the wrapped ``receive``:

    1. the declared ``Content-Length``, before the app is called at all, which
       rejects an honest oversized request without reading a byte of it;
    2. a running total over what ``receive`` actually yields, which rejects a
       chunked request (no ``Content-Length`` to check) or a lying one after at
       most one chunk past the cap.

    Both refusals are written here rather than raised, which is not the obvious
    choice and is load-bearing. A body is read during FastAPI's dependency
    solving, and ``get_request_handler`` wraps that in
    ``except Exception: raise HTTPException(400, "There was an error parsing
    the body")`` — so an exception raised from inside ``receive`` reaches the
    client as a 400 with FastAPI's own envelope, not as this application's 413.
    The second check therefore reports a disconnect to the app, lets it unwind,
    and replaces whatever response it produced with the 413.

    ``RequestTooLargeError`` is still raised *and* handled normally from
    :func:`~resumetailor.core.security.read_upload_capped`, which runs in the
    endpoint body, outside that ``try``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        policy = get_security_policy()
        path = scope.get("path", "")
        limit = (
            policy.max_upload_body_bytes
            if path in UPLOAD_PATHS
            else policy.max_json_body_bytes
        )

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_too_large(
                scope,
                receive,
                send,
                _TooLarge(limit, path, f"Content-Length declared {declared} bytes"),
            )
            return

        overflow = _Overflow()

        async def capped_receive() -> Message:
            message = await receive()
            if message["type"] != "http.request":
                return message
            overflow.total += len(message.get("body", b""))
            if overflow.total > limit:
                overflow.tripped = True
                return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not overflow.tripped:
                await send(message)
                return
            # The app is unwinding from the disconnect above. Swallow its
            # response and answer with the 413 instead, once.
            if overflow.answered or message["type"] != "http.response.start":
                return
            overflow.answered = True
            await _send_too_large(
                scope,
                receive,
                send,
                _TooLarge(limit, path, f"body reached {overflow.total} bytes"),
            )

        await self.app(scope, capped_receive, guarded_send)


@dataclass(slots=True)
class _Overflow:
    """Mutable state shared between one request's wrapped receive and send."""

    total: int = 0
    tripped: bool = False
    answered: bool = False


async def _send_too_large(
    scope: Scope, receive: Receive, send: Send, detail: _TooLarge
) -> None:
    """Answer with the 413 envelope, and log the detail the client never sees."""
    error = RequestTooLargeError(
        f"request body exceeds the {detail.limit} byte cap "
        f"on {detail.path}: {detail.what}"
    )
    security_logger.warning(
        "request body too large: %s",
        detail.path,
        extra={
            "error_code": error.code,
            "http_path": detail.path,
            "limit_bytes": detail.limit,
            "error_detail": error.detail,
        },
    )
    await error_response(error)(scope, receive, send)


@dataclass(slots=True)
class _TooLarge:
    """Why one request was refused: the cap, the route, and what tripped it."""

    limit: int
    path: str
    what: str


def _declared_length(scope: Scope) -> int | None:
    """The request's ``Content-Length``, if it declared a usable one."""
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.decode("latin-1").lower() != "content-length":
            continue
        try:
            return int(raw_value.decode("latin-1"))
        except ValueError:
            return None
    return None


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
