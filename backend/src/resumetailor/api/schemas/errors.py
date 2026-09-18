"""The error shapes this API can put on the wire, and the ``responses=`` tables.

D-42's back half. The frontend needed one place that knows what an error body
looks like; that place cannot exist until the backend declares it, and until
task 2.2 nothing did: the OpenAPI document described every failure as an
untyped 200-or-422 and the client guessed.

**There are three shapes, not one.** This is the honest state of the API and
the reason the client has to branch:

* :class:`ErrorEnvelope` -- ``{"error", "code"}``. Every
  :class:`~resumetailor.core.errors.BackendError` that reaches
  :func:`~resumetailor.core.errors.error_response`, plus the rate limiter,
  which builds the same body by hand because it sits outside Starlette's
  exception middleware. ``code`` is the machine-readable half and the only
  part a caller should branch on.
* :class:`ErrorDetail` -- ``{"detail": "<sentence>"}``. Every
  ``HTTPException`` a router raises: the four 404s, the 400 on a non-PDF
  upload, and the 422 that reports RenderCV's located issues.
* :class:`RequestValidationDetail` -- ``{"detail": [{"loc", "msg", "type"}]}``.
  FastAPI's own 422, when the request body or a query parameter fails
  validation before a handler runs.

:data:`ApiErrorBody` is the union, and it is what every declared error status
documents. Declaring the union on every error status rather than guessing one
shape per status is deliberate: 422 alone can arrive as any of the three (a
``PDFExtractError`` envelope from the import route, a located-issues sentence
from ``PATCH /api/resumes/{id}``, or FastAPI's array from a malformed body), so
a per-status shape would be a documented contract the server does not keep.

**Why not migrate the ``HTTPException`` paths onto the envelope.** It would
collapse three shapes into one and is the right end state, but it changes what
every 404 body looks like, and ``core/errors.py`` is not this task's file. The
recommendation is recorded in the 2.2 report; the client handles all three
until then, which is what :data:`ApiErrorBody` says out loud.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from resumetailor.core.errors import BackendError, ConfigurationError

# Every error class declared outside `core.errors`, imported here by name.
#
# `ERROR_CODES` below walks `BackendError.__subclasses__()`, and a class is
# only in that list once the module declaring it has been imported. Without
# these two lines the vocabulary depended on what the process happened to have
# loaded: `db.migrate` is imported lazily inside the application's lifespan, so
# the document exported by a build step and the document served by a running
# process listed different codes. Both modules import nothing but
# `core.errors` and the standard library.
from resumetailor.db.migrate import MigrationError
from resumetailor.llm.errors import LLMEmptyResponseError

__all__ = [
    "ERROR_CODES",
    "MRO_MAPPED_ERRORS",
    "SSE_ONLY_ERROR_CODES",
    "UNREACHABLE_ERRORS",
    "ApiErrorBody",
    "ErrorDetail",
    "ErrorEnvelope",
    "RequestValidationDetail",
    "ValidationIssue",
    "error_responses",
    "pdf_response",
]


def _subclass_codes(root: type[BackendError]) -> set[str]:
    """Every ``code`` declared on ``root`` or anything deriving from it.

    Walks the tree rather than reading one tuple because an error class can be
    HTTP-mapped through its base class's MRO without appearing in
    ``HTTP_MAPPED_ERRORS`` -- which is exactly how ``LLMEmptyResponseError``
    is wired, deliberately, so that task 2.1 did not have to edit the table
    task 2.4 was rewriting at the same time.
    """
    codes = {root.code}
    for subclass in root.__subclasses__():
        codes |= _subclass_codes(subclass)
    return codes


#: Codes that only ever appear inside an SSE ``event: error`` frame, never on
#: an HTTP error response, because the three streaming routes catch their own
#: failures (see D-55). They are not attributes of any exception class:
#: ``NO_MASTER_RESUME`` is a precondition the generation route checks itself,
#: and the other three are what each route's ``except Exception`` branch emits
#: when the cause is not a domain error at all.
SSE_ONLY_ERROR_CODES: Final[tuple[str, ...]] = (
    "CHAT_FAILED",
    "EVALUATION_FAILED",
    "GENERATION_FAILED",
    "NO_MASTER_RESUME",
)

#: Error classes whose code can never reach a client, and so are left out of
#: the published vocabulary below. Both are raised while the process is
#: starting, where there is no request to answer: a misconfigured host or a
#: database that cannot be brought to a known version fails the boot instead,
#: which is what each class's own docstring says. Publishing their codes would
#: put two members in the frontend's ``ErrorCode`` union that no response can
#: ever carry.
UNREACHABLE_ERRORS: Final[tuple[type[BackendError], ...]] = (
    ConfigurationError,
    MigrationError,
)

#: Every ``code`` a client can receive, HTTP or SSE, sorted.
#:
#: Derived, not typed out: the HTTP half is read off the exception classes
#: themselves, so adding an error class adds its code here, to the OpenAPI
#: document and to the generated TypeScript with nobody remembering to.
#: ``HTTP_MAPPED_ERRORS`` is deliberately not the source -- it is the handler
#: registration table, and it misses anything mapped through an MRO, which is
#: how ``LLMEmptyResponseError`` is wired. The two imports at the top of this
#: module are what make the walk complete and the result independent of import
#: order; ``tests/test_api_contract.py`` asserts that every class in the tree
#: is either published here or named in ``UNREACHABLE_ERRORS``.
#: The one error mapped to HTTP through its base class's MRO rather than
#: through ``HTTP_MAPPED_ERRORS``. Named here so that the import above is a
#: statement about the taxonomy and not an unused line someone deletes.
MRO_MAPPED_ERRORS: Final[tuple[type[BackendError], ...]] = (LLMEmptyResponseError,)

ERROR_CODES: Final[tuple[str, ...]] = tuple(
    sorted(
        (_subclass_codes(BackendError) | set(SSE_ONLY_ERROR_CODES))
        - {error.code for error in UNREACHABLE_ERRORS}
    )
)


class ErrorEnvelope(BaseModel):
    """``{"error", "code"}``: the application's own error body.

    ``error`` is the raising class's fixed ``client_message`` and is safe to
    show a user; it is never ``str(exc)`` (D-53). ``code`` is what to branch
    on, and its vocabulary is :data:`ERROR_CODES`.
    """

    error: str = Field(description="One sentence, safe to show a user.")
    code: str = Field(description="Machine-readable. One of ERROR_CODES.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": (
                        "The language model provider is unavailable. "
                        "Try again in a moment."
                    ),
                    "code": "LLM_UNAVAILABLE",
                }
            ]
        }
    )


class ErrorDetail(BaseModel):
    """``{"detail": "<sentence>"}``: an ``HTTPException`` raised in a router.

    No ``code``. A client that needs to branch on one of these has only the
    status and the path, which is the gap the recommendation in this module's
    docstring closes.
    """

    detail: str

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "Resume not found"}]}
    )


class ValidationIssue(BaseModel):
    """One entry of FastAPI's 422 body.

    ``extra="allow"``: pydantic v2 also emits ``input`` and sometimes ``ctx``
    and ``url``, and this model documents the three fields a client can rely
    on without claiming the others are absent.
    """

    loc: list[str | int]
    msg: str
    type: str

    model_config = ConfigDict(extra="allow")


class RequestValidationDetail(BaseModel):
    """FastAPI's own 422: the request never reached a handler."""

    detail: list[ValidationIssue]


#: What any declared error status can carry. See the module docstring for why
#: this is one union rather than one shape per status.
ApiErrorBody = ErrorEnvelope | ErrorDetail | RequestValidationDetail


#: The sentence attached to each status this API can answer with, so the
#: OpenAPI document says *why* a status happens and not just that it can.
#: Keyed by status; a route names the statuses it can produce and gets these.
_STATUS_DESCRIPTIONS: Final[dict[int, str]] = {
    400: "The request is malformed in a way the route checks itself.",
    404: "No such resource. `{detail}`, with no `code`.",
    413: ("The body, or an upload inside it, is over the cap. `REQUEST_TOO_LARGE`."),
    422: (
        "The request was understood and refused. Any of the three shapes: "
        "FastAPI's array of issues for a malformed body, a located-issues "
        "sentence for a document RenderCV rejects, or a `PDF_EXTRACT_FAILED` "
        "envelope for an unreadable upload."
    ),
    429: "The caller has spent its request budget. `RATE_LIMITED`, with `Retry-After`.",
    500: (
        "`INTERNAL_ERROR`, `RENDER_FAILED` or `LLM_AUTH_ERROR`. The body never "
        "carries the cause; it is logged with the request id instead (D-53)."
    ),
    503: (
        "The provider is unreachable or answered with nothing. "
        "`LLM_UNAVAILABLE` or `LLM_EMPTY_RESPONSE`."
    ),
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """The ``responses=`` entry for each status a route can answer with.

    Args:
        statuses: The error statuses this route produces. Every one must be in
            :data:`_STATUS_DESCRIPTIONS`, so a typo is an import-time
            ``KeyError`` rather than an undocumented status.

    Returns:
        A mapping ready to splice into a route decorator. Declaring 422 here
        also *replaces* FastAPI's automatic 422, which is the point: a route
        that can answer 422 in more than one shape should document all of
        them.
    """
    return {
        status: {
            "model": ApiErrorBody,
            "description": _STATUS_DESCRIPTIONS[status],
        }
        for status in statuses
    }


def pdf_response(description: str) -> dict[int | str, dict[str, Any]]:
    """The 200 entry for a route whose body is a PDF, not JSON.

    ``response_class`` alone tells FastAPI how to send the response but leaves
    the documented media type as ``application/json``, so a generated client
    would expect to parse one. This states the real one.
    """
    return {
        200: {
            "description": description,
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    }
