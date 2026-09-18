"""Score a resume against a job description: one LLM call, one parse.

Smaller than the tailoring pipeline and extracted for the same reason — it was
reachable only through an SSE response, so nothing could exercise the parse
without one.

The service takes **arbitrary YAML**, not "the master resume". That genericity
is what D-45 needs: the product should be able to evaluate a generated resume,
or the editor's unsaved buffer, and not only the stored master. The route's
``EvaluateRequest.yaml_content`` already worked this way, and the frontend half
of it is task 3.1's; this module keeps the seam open from the back.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from resumetailor.backend_api import BackendAPI

__all__ = ["EvaluationResult", "evaluate"]

EVALUATION_SYSTEM_PROMPT = (
    "You are a resume evaluation expert. Score the provided resume YAML "
    "against the job description. Return JSON with: match_score (integer "
    "0-100), critique (string), matched_keywords (array of strings), "
    "missing_keywords (array of strings)."
)

#: Hand-written rather than derived from :class:`EvaluationResult`: the JSON
#: schema a provider accepts in strict mode and the one Pydantic generates are
#: not the same document, and the deterministic stub branches on this one.
_RESPONSE_FORMAT: dict[str, Any] = {
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
            "required": [
                "match_score",
                "critique",
                "matched_keywords",
                "missing_keywords",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


class EvaluationResult(BaseModel):
    """How well one resume answers one job description.

    The field names and types are the ``event: done`` payload the frontend
    reads, unchanged from when this was ``json.loads`` in the route. Parsing
    into a model rather than a bare ``dict`` is what makes a provider that
    ignores the response schema a caught error instead of a half-populated
    panel.
    """

    match_score: int
    critique: str
    matched_keywords: list[str]
    missing_keywords: list[str]


async def evaluate(
    api: BackendAPI, *, yaml_content: str, job_description: str
) -> EvaluationResult:
    """Score ``yaml_content`` against ``job_description``.

    Args:
        api: The port facade. One ``complete`` call.
        yaml_content: Any resume document — the master, a generated one, or an
            unsaved buffer. Not normalized: this reads the document, it does
            not render it, and normalizing here would score something the user
            never wrote.
        job_description: The job to score against.
    """
    response = await api.complete(
        [
            {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Resume YAML:\n{yaml_content}\n\n"
                    f"Job Description:\n{job_description}"
                ),
            },
        ],
        response_format=_RESPONSE_FORMAT,
    )
    return EvaluationResult.model_validate_json(response)
