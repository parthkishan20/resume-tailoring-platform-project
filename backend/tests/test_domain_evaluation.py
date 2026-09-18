"""Task 2.5: the evaluation service, exercised without an HTTP layer.

One provider call and one parse, and the parse is the part that used to be
untestable: ``json.loads`` inside an SSE generator, whose failure mode was a
half-populated panel rather than an error.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from resumetailor.backend_api import BackendAPI
from resumetailor.core.errors import LLMAuthError
from resumetailor.domain.evaluation import EvaluationResult, evaluate

NOT_A_STREAM = "evaluation does not stream"
KEY_DETAIL = "key detail that must not travel"

GENERATED_YAML = "cv:\n  name: Tester\n  label: A generated resume\n"

SCORED = {
    "match_score": 72,
    "critique": "Missing Kubernetes.",
    "matched_keywords": ["Python"],
    "missing_keywords": ["Kubernetes"],
}


class ScriptedLLM:
    def __init__(self, response: str) -> None:
        self._response = response
        self.messages: list[dict] | None = None
        self.response_format: dict | None = None

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        self.messages = messages
        self.response_format = response_format
        return self._response

    async def stream(self, messages: list[dict]):
        raise AssertionError(NOT_A_STREAM)


def build_api(llm: ScriptedLLM) -> BackendAPI:
    return BackendAPI(llm=llm, pdf_render=None, pdf_extract=None)


@pytest.mark.anyio
async def test_a_scored_response_becomes_a_typed_result():
    llm = ScriptedLLM(json.dumps(SCORED))

    result = await evaluate(
        build_api(llm), yaml_content=GENERATED_YAML, job_description="Python role"
    )

    assert isinstance(result, EvaluationResult)
    assert result.match_score == 72
    assert result.critique == "Missing Kubernetes."
    assert result.matched_keywords == ["Python"]
    assert result.missing_keywords == ["Kubernetes"]


@pytest.mark.anyio
async def test_the_wire_shape_is_the_four_keys_the_frontend_reads():
    llm = ScriptedLLM(json.dumps(SCORED))

    result = await evaluate(
        build_api(llm), yaml_content=GENERATED_YAML, job_description="jd"
    )

    assert result.model_dump() == SCORED


@pytest.mark.anyio
async def test_any_document_can_be_scored_not_only_the_master():
    """D-45: the service takes YAML, and has no opinion about where it came from."""
    llm = ScriptedLLM(json.dumps(SCORED))

    await evaluate(
        build_api(llm), yaml_content=GENERATED_YAML, job_description="Python role"
    )

    assert llm.messages is not None
    user_prompt = llm.messages[1]["content"]
    assert "A generated resume" in user_prompt
    assert "Python role" in user_prompt


@pytest.mark.anyio
async def test_the_document_is_scored_as_written_not_normalized():
    """Scoring reads; it does not repair. The user is told about what they have."""
    llm = ScriptedLLM(json.dumps(SCORED))
    unrenderable = "cv:\n  name: Tester\n  bogus_key: kept\n"

    await evaluate(build_api(llm), yaml_content=unrenderable, job_description="jd")

    assert llm.messages is not None
    assert "bogus_key: kept" in llm.messages[1]["content"]


@pytest.mark.anyio
async def test_the_provider_is_asked_for_the_evaluation_schema():
    llm = ScriptedLLM(json.dumps(SCORED))

    await evaluate(build_api(llm), yaml_content=GENERATED_YAML, job_description="jd")

    assert llm.response_format is not None
    schema = llm.response_format["json_schema"]
    assert schema["name"] == "evaluation_result"
    assert schema["strict"] is True
    assert sorted(schema["schema"]["required"]) == [
        "critique",
        "match_score",
        "matched_keywords",
        "missing_keywords",
    ]


@pytest.mark.anyio
async def test_a_provider_that_ignores_the_schema_is_an_error_not_a_gap():
    llm = ScriptedLLM(json.dumps({"match_score": 50}))

    with pytest.raises(ValidationError):
        await evaluate(build_api(llm), yaml_content=GENERATED_YAML, job_description="")


@pytest.mark.anyio
async def test_a_provider_that_answers_prose_is_an_error():
    llm = ScriptedLLM("I think this resume is pretty good, actually.")

    with pytest.raises(ValidationError):
        await evaluate(build_api(llm), yaml_content=GENERATED_YAML, job_description="")


@pytest.mark.anyio
async def test_a_provider_failure_propagates_as_the_domain_error():
    class FailingLLM(ScriptedLLM):
        async def complete(
            self, messages: list[dict], response_format: dict | None = None
        ) -> str:
            raise LLMAuthError(KEY_DETAIL)

    with pytest.raises(LLMAuthError):
        await evaluate(
            build_api(FailingLLM("")), yaml_content=GENERATED_YAML, job_description=""
        )
