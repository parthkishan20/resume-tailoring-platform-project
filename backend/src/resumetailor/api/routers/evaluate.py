# backend/src/resumetailor/api/routers/evaluate.py
from __future__ import annotations
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from resumetailor.backend_api import BackendAPI
from resumetailor.deps import get_backend
from resumetailor.core.errors import LLMAuthError, LLMUnavailableError
from resumetailor.core.security import MAX_JOB_DESCRIPTION_CHARS, MAX_RESUME_YAML_CHARS

router = APIRouter()

_EVALUATE_SYSTEM_PROMPT = (
    "You are a resume evaluation expert. Score the provided resume YAML against the job description. "
    "Return JSON with: match_score (integer 0-100), critique (string), "
    "matched_keywords (array of strings), missing_keywords (array of strings)."
)

_EVALUATE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "evaluation_result",
        "schema": {
            "type": "object",
            "properties": {
                "match_score": {"type": "integer"},
                "critique": {"type": "string"},
                "matched_keywords": {"type": "array", "items": {"type": "string"}},
                "missing_keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["match_score", "critique", "matched_keywords", "missing_keywords"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


class EvaluateRequest(BaseModel):
    yaml_content: str = Field(max_length=MAX_RESUME_YAML_CHARS)
    job_description: str = Field(max_length=MAX_JOB_DESCRIPTION_CHARS)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/api/evaluate/stream")
async def evaluate_stream(body: EvaluateRequest, api: BackendAPI = Depends(get_backend)):
    async def event_gen():
        try:
            yield _sse("progress", {"message": "Analyzing resume and job description..."})
            result_str = await api.complete(
                [
                    {"role": "system", "content": _EVALUATE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Resume YAML:\n{body.yaml_content}\n\nJob Description:\n{body.job_description}"},
                ],
                response_format=_EVALUATE_RESPONSE_FORMAT,
            )
            result = json.loads(result_str)
            yield _sse("done", {"result": result})
        except LLMAuthError as exc:
            yield _sse("error", {"error": str(exc), "code": "LLM_AUTH_ERROR"})
        except LLMUnavailableError as exc:
            yield _sse("error", {"error": str(exc), "code": "LLM_UNAVAILABLE"})
        except Exception as exc:
            yield _sse("error", {"error": str(exc), "code": "EVALUATION_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
