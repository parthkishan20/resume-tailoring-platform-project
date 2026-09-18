"""The domain exception hierarchy, and the one place it becomes HTTP.

Two things used to be spread across the codebase and are now here:

* the exception taxonomy, which lived in ``ports.py`` next to three unrelated
  ``Protocol`` declarations. ``ports.py`` now re-exports these names so the
  adapters keep importing from where they always have, until task 1.3 moves
  the ports themselves into ``llm/``, ``rendering/`` and ``pdf/``.
* the HTTP mapping, which was four near-identical ``@app.exception_handler``
  functions in ``main.py``. Status code and error code are now attributes of
  the exception class, so adding an error is one class, not one class plus one
  handler.

The wire shape is unchanged: ``{"error": "<message>", "code": "<CODE>"}``.

**What changed in task 2.4 (D-53).** The ``error`` field used to be ``str(exc)``,
which for a :class:`RenderError` is the whole of ``rendercv``'s stdout and
stderr — absolute container paths, Python tracebacks, Typst diagnostics — and
for an :class:`LLMUnavailableError` is raw provider exception text, which can
carry request URLs, model routing detail and provider names. Both went to the
client verbatim.

Now every error class carries two messages:

* ``str(exc)``, unchanged, is the **operator-facing detail**. It is what the
  exception was raised with, it is what gets logged, and it is what a developer
  sees in a traceback or a ``pytest.raises(match=...)``.
* ``client_message``, a class attribute, is the **only thing that reaches the
  client**. It is generic, fixed per error class, and says nothing about the
  inside of the process.

``code`` is untouched — same field, same values. It is what the frontend
branches on, and the human-readable half was never the contract.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar, cast

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


class BackendError(Exception):
    """Base for every error this application raises deliberately.

    Subclasses carry their own HTTP status, machine-readable code, and the one
    sentence a client is allowed to see. Anything that is not a
    ``BackendError`` is a bug and becomes a 500.
    """

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "INTERNAL_ERROR"
    #: Returned to the client in place of ``str(exc)``. Fixed per class, so it
    #: cannot accidentally come to contain something from inside the process.
    client_message: ClassVar[str] = "The server could not complete the request."

    @property
    def detail(self) -> str:
        """The operator-facing text: logged, never returned to a client."""
        return str(self)


class ConfigurationError(BackendError):
    """The process is misconfigured. Raised at startup, never per request."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "CONFIGURATION_ERROR"
    client_message: ClassVar[str] = "The server is misconfigured."


class LLMAuthError(BackendError):
    """Invalid or missing API key."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "LLM_AUTH_ERROR"
    client_message: ClassVar[str] = (
        "The language model provider rejected this server's credentials."
    )


class LLMUnavailableError(BackendError):
    """Rate limit, service down, or network failure."""

    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "LLM_UNAVAILABLE"
    client_message: ClassVar[str] = (
        "The language model provider is unavailable. Try again in a moment."
    )


class RenderError(BackendError):
    """render-cv PDF generation failed."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "RENDER_FAILED"
    client_message: ClassVar[str] = "The resume could not be rendered to a PDF."


class PDFExtractError(BackendError):
    """PyMuPDF could not open or read the PDF."""

    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "PDF_EXTRACT_FAILED"
    client_message: ClassVar[str] = (
        "The PDF could not be read. It may be corrupt, password protected, "
        "larger than 10 MB, or longer than 50 pages."
    )


class RequestTooLargeError(BackendError):
    """The request body, or an upload inside it, exceeded its cap.

    Raised from inside the request — by the wrapped ``receive`` in
    ``BodySizeLimitMiddleware`` and by
    :func:`resumetailor.core.security.read_upload_capped` — so it goes through
    the handler below like any other domain error (PLAN.md D-47, D-48).
    """

    status_code: ClassVar[int] = 413
    code: ClassVar[str] = "REQUEST_TOO_LARGE"
    client_message: ClassVar[str] = "The request is larger than this endpoint accepts."


class RateLimitedError(BackendError):
    """The client has spent its request budget for now (PLAN.md D-28).

    Deliberately absent from :data:`HTTP_MAPPED_ERRORS`: it is never raised.
    ``RateLimitMiddleware`` sits outside Starlette's exception middleware, so
    it builds the response with :func:`error_response` directly and adds a
    ``Retry-After`` header. The class exists so that the envelope and the code
    are declared here with every other error rather than inline in middleware.
    """

    status_code: ClassVar[int] = 429
    code: ClassVar[str] = "RATE_LIMITED"
    client_message: ClassVar[str] = (
        "Too many requests. Wait a moment before trying again."
    )


#: The errors that reach the client as an HTTP response. `BackendError` and
#: `ConfigurationError` are deliberately absent: neither is raised inside a
#: request, and registering the base class would silently start catching every
#: future subclass at 500.
HTTP_MAPPED_ERRORS: tuple[type[BackendError], ...] = (
    LLMAuthError,
    LLMUnavailableError,
    RenderError,
    PDFExtractError,
    RequestTooLargeError,
)


def error_response(exc: BackendError) -> JSONResponse:
    """Render a domain error as the application's error envelope.

    ``error`` is the class's ``client_message``, never ``str(exc)``. The detail
    is logged by the handler below instead (D-53).
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.client_message, "code": exc.code},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register one handler per HTTP-mapped domain error.

    Unlike the four handlers this replaces, the handler logs before it
    serialises, so a failure that the user sees is also a failure the operator
    can find by request id (PLAN.md D-52). Since D-53 the log line is the
    *only* place the detail exists: it is emitted at ERROR with the full
    message in ``error_detail``, the traceback in ``exception``, and the
    request id that ``core/logging.py`` puts on every record.
    """

    async def handle(request: Request, exc: Exception) -> JSONResponse:
        # Starlette types every handler against bare `Exception`; registration
        # below guarantees the concrete type.
        error = cast("BackendError", exc)
        logger.error(
            "domain error: %s",
            error.code,
            exc_info=error,
            extra={
                "error_code": error.code,
                "path": request.url.path,
                "error_detail": error.detail,
            },
        )
        return error_response(error)

    for error_type in HTTP_MAPPED_ERRORS:
        app.add_exception_handler(error_type, handle)
