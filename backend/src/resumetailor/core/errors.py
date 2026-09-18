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

Note for whoever picks up D-53: the message still reaches the client verbatim,
including subprocess stderr. Splitting the operator-facing detail from the
client-facing message is task 2.4, not this one.
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

    Subclasses carry their own HTTP status and machine-readable code. Anything
    that is not a ``BackendError`` is a bug and becomes a 500.
    """

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "INTERNAL_ERROR"


class ConfigurationError(BackendError):
    """The process is misconfigured. Raised at startup, never per request."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "CONFIGURATION_ERROR"


class LLMAuthError(BackendError):
    """Invalid or missing API key."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "LLM_AUTH_ERROR"


class LLMUnavailableError(BackendError):
    """Rate limit, service down, or network failure."""

    status_code: ClassVar[int] = 503
    code: ClassVar[str] = "LLM_UNAVAILABLE"


class RenderError(BackendError):
    """render-cv PDF generation failed."""

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "RENDER_FAILED"


class PDFExtractError(BackendError):
    """PyMuPDF could not open or read the PDF."""

    status_code: ClassVar[int] = 422
    code: ClassVar[str] = "PDF_EXTRACT_FAILED"


#: The errors that reach the client as an HTTP response. `BackendError` and
#: `ConfigurationError` are deliberately absent: neither is raised inside a
#: request, and registering the base class would silently start catching every
#: future subclass at 500.
HTTP_MAPPED_ERRORS: tuple[type[BackendError], ...] = (
    LLMAuthError,
    LLMUnavailableError,
    RenderError,
    PDFExtractError,
)


def error_response(exc: BackendError) -> JSONResponse:
    """Render a domain error as the application's error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc), "code": exc.code},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register one handler per HTTP-mapped domain error.

    Unlike the four handlers this replaces, the handler logs before it
    serialises, so a failure that the user sees is also a failure the operator
    can find by request id (PLAN.md D-52).
    """

    async def handle(request: Request, exc: Exception) -> JSONResponse:
        # Starlette types every handler against bare `Exception`; registration
        # below guarantees the concrete type.
        error = cast("BackendError", exc)
        logger.warning(
            "domain error: %s",
            error.code,
            exc_info=error,
            extra={"error_code": error.code, "path": request.url.path},
        )
        return error_response(error)

    for error_type in HTTP_MAPPED_ERRORS:
        app.add_exception_handler(error_type, handle)
