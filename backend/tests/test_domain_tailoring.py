"""Task 2.5: the tailoring pipeline, exercised without an HTTP layer.

Everything here used to need an SSE response and a running application to
reach. The point of the extraction is that it does not: each test below drives
``domain.tailoring`` directly with a scripted provider, which is why the two
passes, the audit-report strip and the "what was rendered is what is stored"
guarantee can be asserted on their own rather than inferred from a stream.

The SSE contract itself — the event names and the progress strings — is a
property of the route, and stays pinned in ``test_routes_resumes.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resumetailor.backend_api import BackendAPI
from resumetailor.core.errors import LLMUnavailableError
from resumetailor.db.models import GenerationRule
from resumetailor.domain.tailoring import (
    Stage,
    TailoredResume,
    store_tailored_resume,
    tailor,
)

NOT_A_STREAM = "the tailoring pipeline does not stream"
PROVIDER_DETAIL = "provider detail that must not travel"
RENDER_DETAIL = "render detail that must not travel"

MASTER_YAML = "cv:\n  name: Tester\n  email: tester@example.com\n"
DRAFT_YAML = (
    "cv:\n  name: Tester\n  email: tester@example.com\n  location: Draft City\n"
)
FINAL_YAML = (
    "cv:\n  name: Tester\n  email: tester@example.com\n  location: Final City\n"
)


class ScriptedLLM:
    """Answers ``complete`` from a queue and records every call.

    The shared ``sim`` fixture pins one response for every call, which cannot
    express "the generation pass said this and the audit pass said that" — the
    distinction this module's whole shape depends on.
    """

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list[dict], dict | None]] = []

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        self.calls.append((messages, response_format))
        return self._responses.pop(0)

    async def stream(self, messages: list[dict]):
        raise AssertionError(NOT_A_STREAM)

    def system_prompt(self, call: int) -> str:
        return str(self.calls[call][0][0]["content"])

    def user_prompt(self, call: int) -> str:
        return str(self.calls[call][0][1]["content"])


class RecordingRenderer:
    def __init__(self, pdf_bytes: bytes = b"%PDF-1.4 tailored") -> None:
        self._pdf_bytes = pdf_bytes
        self.error: Exception | None = None
        self.yaml_seen: list[str] = []

    async def render(self, yaml_content: str) -> bytes:
        self.yaml_seen.append(yaml_content)
        if self.error is not None:
            raise self.error
        return self._pdf_bytes


def build_api(llm: ScriptedLLM, renderer: RecordingRenderer) -> BackendAPI:
    """The real facade over scripted ports. No HTTP, no database, no network."""
    return BackendAPI(llm=llm, pdf_render=renderer, pdf_extract=None)


def generation_response(yaml_content: str) -> str:
    return json.dumps({"yaml_content": yaml_content})


async def run(api: BackendAPI, **kwargs: object) -> list[object]:
    """Drain the pipeline into a list of events."""
    defaults: dict[str, object] = {
        "master_yaml": MASTER_YAML,
        "job_description": "Senior Python role",
        "rules": [],
    }
    defaults.update(kwargs)
    return [event async for event in tailor(api, **defaults)]  # type: ignore[arg-type]


# ── The stages, and their order ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_the_pipeline_narrates_three_stages_then_one_result():
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)
    renderer = RecordingRenderer()

    events = await run(build_api(llm, renderer))

    assert events[:3] == [Stage.ANALYZING, Stage.TAILORING, Stage.RENDERING]
    assert isinstance(events[3], TailoredResume)
    assert len(events) == 4


@pytest.mark.anyio
async def test_a_stage_is_yielded_before_the_work_it_names():
    """Progress is a promise, not a receipt: the caller can say what is next."""
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)
    renderer = RecordingRenderer()

    generator = tailor(
        build_api(llm, renderer),
        master_yaml=MASTER_YAML,
        job_description="jd",
        rules=[],
    )

    assert await anext(generator) == Stage.ANALYZING
    assert llm.calls == [], "the generation call has not been made yet"
    assert await anext(generator) == Stage.TAILORING
    assert len(llm.calls) == 1
    assert await anext(generator) == Stage.RENDERING
    assert len(llm.calls) == 2
    assert renderer.yaml_seen == [], "the render has not been made yet"
    assert isinstance(await anext(generator), TailoredResume)
    assert len(renderer.yaml_seen) == 1


# ── The two passes ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_generate_then_audit_is_two_calls_with_different_prompts():
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)

    await run(build_api(llm, RecordingRenderer()))

    assert len(llm.calls) == 2
    assert "ResumeTailor-v2" in llm.system_prompt(0)
    assert "ResumeAuditor-v2" in llm.system_prompt(1)
    # Only the generation pass is schema-constrained; the auditor answers with
    # a rubric report followed by YAML.
    assert llm.calls[0][1] is not None
    assert llm.calls[1][1] is None


@pytest.mark.anyio
async def test_the_audit_pass_sees_the_draft_the_master_and_the_job():
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)

    await run(build_api(llm, RecordingRenderer()), job_description="Rust role")

    audit_prompt = llm.user_prompt(1)
    assert "location: Draft City" in audit_prompt
    assert "tester@example.com" in audit_prompt
    assert "Rust role" in audit_prompt


@pytest.mark.anyio
async def test_user_rules_reach_both_system_prompts():
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)
    rules = [
        GenerationRule(section="experience", rule_key="max_entries", rule_value="7")
    ]

    await run(build_api(llm, RecordingRenderer()), rules=rules)

    for call in (0, 1):
        assert "USER-CONFIGURED LIMITS" in llm.system_prompt(call)
        assert "experience.max_entries = 7" in llm.system_prompt(call)


# ── Normalization: D-04 and D-08 ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_the_master_is_normalized_before_the_provider_sees_it():
    """A stored master is not necessarily a renderable one."""
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)

    await run(
        build_api(llm, RecordingRenderer()),
        master_yaml="cv:\n  name: Tester\n  contact:\n    email: t@example.com\n",
    )

    generation_prompt = llm.user_prompt(0)
    assert "email: t@example.com" in generation_prompt
    assert "contact:" not in generation_prompt


@pytest.mark.anyio
async def test_what_was_rendered_is_what_is_returned_to_be_stored():
    """D-04 on this path: the stored document is one that demonstrably renders."""
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)
    renderer = RecordingRenderer(pdf_bytes=b"%PDF-1.4 final")

    events = await run(build_api(llm, renderer))
    result = events[-1]

    assert isinstance(result, TailoredResume)
    assert renderer.yaml_seen == [result.yaml_content]
    assert result.pdf_bytes == b"%PDF-1.4 final"
    assert "location: Final City" in result.yaml_content


@pytest.mark.anyio
async def test_dropped_fields_are_collected_from_every_pass():
    """D-08: what the normalizer removed survives as far as the caller."""
    llm = ScriptedLLM(
        generation_response(DRAFT_YAML + "  phone: not-a-number\n"), FINAL_YAML
    )

    events = await run(
        build_api(llm, RecordingRenderer()),
        master_yaml=MASTER_YAML + "  bogus_key: x\n",
    )
    result = events[-1]

    assert isinstance(result, TailoredResume)
    assert {dropped.field_path for dropped in result.dropped} == {
        "cv.bogus_key",
        "cv.phone",
    }


# ── The audit report ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_the_audit_report_is_stripped_from_the_final_document():
    audit_response = (
        "AUDIT_START\n[S1] FAIL - one bullet is a fragment\nIssues found: 1\n"
        f"AUDIT_END\n{FINAL_YAML}"
    )
    llm = ScriptedLLM(generation_response(DRAFT_YAML), audit_response)
    renderer = RecordingRenderer()

    events = await run(build_api(llm, renderer))
    result = events[-1]

    assert isinstance(result, TailoredResume)
    assert "AUDIT" not in result.yaml_content
    assert "Issues found" not in result.yaml_content
    assert "location: Final City" in result.yaml_content


@pytest.mark.anyio
async def test_an_auditor_that_skips_the_report_is_taken_at_its_word():
    llm = ScriptedLLM(generation_response(DRAFT_YAML), f"\n{FINAL_YAML}\n")

    events = await run(build_api(llm, RecordingRenderer()))
    result = events[-1]

    assert isinstance(result, TailoredResume)
    assert "location: Final City" in result.yaml_content


# ── Failures ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_provider_failure_propagates_as_the_domain_error():
    """The pipeline does not catch: the route owns what a failure looks like."""

    class FailingLLM(ScriptedLLM):
        async def complete(
            self, messages: list[dict], response_format: dict | None = None
        ) -> str:
            raise LLMUnavailableError(PROVIDER_DETAIL)

    with pytest.raises(LLMUnavailableError):
        await run(build_api(FailingLLM(), RecordingRenderer()))


@pytest.mark.anyio
async def test_a_render_failure_propagates_and_nothing_is_returned():
    llm = ScriptedLLM(generation_response(DRAFT_YAML), FINAL_YAML)
    renderer = RecordingRenderer()
    renderer.error = LLMUnavailableError(RENDER_DETAIL)

    with pytest.raises(LLMUnavailableError):
        await run(build_api(llm, renderer))


# ── The write (D-20's one place) ─────────────────────────────────────────────


def test_storing_a_result_writes_the_row_the_pdf_and_the_path(db_path, pdfs_dir):
    result = TailoredResume(yaml_content=FINAL_YAML, pdf_bytes=b"%PDF-1.4 stored")

    row = store_tailored_resume(
        db_path, pdfs_dir, job_description="Senior Python role", result=result
    )

    assert row.yaml_content == FINAL_YAML
    assert row.pdf_path == f"{row.id}.pdf"
    assert row.job_description == "Senior Python role"
    written = Path(pdfs_dir) / f"{row.id}.pdf"
    assert written.read_bytes() == b"%PDF-1.4 stored"


def test_the_stored_name_is_the_head_of_the_job_description(db_path, pdfs_dir):
    result = TailoredResume(yaml_content=FINAL_YAML, pdf_bytes=b"%PDF")
    job_description = "Staff Engineer, Platform, at a company with a long name"

    row = store_tailored_resume(
        db_path, pdfs_dir, job_description=job_description, result=result
    )

    assert row.name.endswith(job_description[:40])
    assert job_description[:40] in row.name
    assert len(row.name) < len(job_description)


def test_the_pdf_directory_is_created_if_it_is_missing(db_path, tmp_path):
    missing = tmp_path / "not" / "there"
    result = TailoredResume(yaml_content=FINAL_YAML, pdf_bytes=b"%PDF")

    row = store_tailored_resume(
        db_path, str(missing), job_description="jd", result=result
    )

    assert (missing / f"{row.id}.pdf").exists()
