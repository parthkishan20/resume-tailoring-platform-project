# backend/src/resumetailor/api/routers/evaluate.py
from __future__ import annotations
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from resumetailor.backend_api import BackendAPI
from resumetailor.deps import get_backend
from resumetailor.core.errors import BackendError, LLMAuthError, LLMUnavailableError
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


def _error_frame(exc: BackendError, code: str) -> str:
    """One SSE error frame, and the log line that keeps the detail.

    D-53, on the streaming path: an SSE error never reaches the exception
    handler in `core/errors.py`, so the client gets the class's fixed
    `client_message` and the operator gets `str(exc)` in the log, with the
    request id attached. `code` stays a literal at the call site; reconciling
    the literals with `exc.code` is task 2.2's.
    """
    logger.error(
        "sse domain error: %s",
        code,
        exc_info=exc,
        extra={"error_code": code, "error_detail": exc.detail},
    )
    return _sse("error", {"error": exc.client_message, "code": code})


@router.post("/api/evaluate/stream")
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
        except LLMAuthError as exc:
            yield _error_frame(exc, "LLM_AUTH_ERROR")
        except LLMUnavailableError as exc:
            yield _error_frame(exc, "LLM_UNAVAILABLE")
        except Exception:
            # Includes a provider that answered something other than the
            # schema it was given: a `ValidationError` from the service. Its
            # text quotes the response, so it is logged, not sent.
            logger.exception("sse evaluation failed", extra={"error_code": "EVALUATION_FAILED"})
            yield _sse("error", {"error": BackendError.client_message, "code": "EVALUATION_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
