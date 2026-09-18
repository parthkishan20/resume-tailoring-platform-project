# backend/src/resumetailor/api/routers/evaluate.py
from __future__ import annotations
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from resumetailor.api.schemas.errors import error_responses
from resumetailor.backend_api import BackendAPI
from resumetailor.deps import get_backend
from resumetailor.core.errors import BackendError
from resumetailor.core.security import MAX_JOB_DESCRIPTION_CHARS, MAX_RESUME_YAML_CHARS
from resumetailor.domain.evaluation import evaluate

router = APIRouter()
logger = logging.getLogger(__name__)

# The SSE contract: the frontend matches on this string.
_PROGRESS_MESSAGE = "Analyzing resume and job description..."


class EvaluateRequest(BaseModel):
    """Any resume document, scored against any job description.

    `yaml_content` is deliberately not "the master resume": D-45 wants a
    generated resume, or the editor's unsaved buffer, evaluated too, and the
    service behind this route takes whatever it is given.
    """

    yaml_content: str = Field(max_length=MAX_RESUME_YAML_CHARS)
    job_description: str = Field(max_length=MAX_JOB_DESCRIPTION_CHARS)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _error_frame(exc: BackendError) -> str:
    """One SSE error frame, and the log line that keeps the detail.

    D-53, on the streaming path: an SSE error never reaches the exception
    handler in `core/errors.py`, so the client gets the class's fixed
    `client_message` and the operator gets `str(exc)` in the log, with the
    request id attached.

    The `code` parameter is gone as of task 2.2. It was a literal matched by
    hand to the exception each branch caught, which silently reported a
    subclass under its base class's code; `exc.code` is the value the HTTP
    error handler has always used for the same exception, so a streaming
    failure and a non-streaming one now carry the same code as well as the
    same shape. See the same change in `resumes.py` and `chat.py`.
    """
    logger.error(
        "sse domain error: %s",
        exc.code,
        exc_info=exc,
        extra={"error_code": exc.code, "error_detail": exc.detail},
    )
    return _sse("error", {"error": exc.client_message, "code": exc.code})


@router.post(
    "/api/evaluate/stream",
    response_class=StreamingResponse,
    responses=error_responses(413, 422, 429),
)
async def evaluate_stream(body: EvaluateRequest, api: BackendAPI = Depends(get_backend)):
    """Score a resume against a job description, as server-sent events.

    The call and the parse are `domain.evaluation.evaluate`; this handler only
    frames them.
    """
    async def event_gen():
        try:
            yield _sse("progress", {"message": _PROGRESS_MESSAGE})
            result = await evaluate(
                api,
                yaml_content=body.yaml_content,
                job_description=body.job_description,
            )
            yield _sse("done", {"result": result.model_dump()})
        # One branch for every domain error, keyed on `exc.code`: see
        # `_error_frame`. The two it replaces caught two classes and named two
        # literals, so an error class added anywhere else in the application
        # fell through to the generic branch below.
        except BackendError as exc:
            yield _error_frame(exc)
        except Exception:
            # Includes a provider that answered something other than the
            # schema it was given: a `ValidationError` from the service. Its
            # text quotes the response, so it is logged, not sent.
            logger.exception("sse evaluation failed", extra={"error_code": "EVALUATION_FAILED"})
            yield _sse("error", {"error": BackendError.client_message, "code": "EVALUATION_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
