"""Coverage for the wiring code route tests never exercise.

`client` (conftest.py) overrides `get_backend` with the `sim` fixture, so
`deps._backend`, `backend_api.create_real_backend` / `create_stub_backend`,
and `pdf.extract.PyMuPDFAdapter` never run in any route test. These call
those paths directly.
"""

from __future__ import annotations

import pytest

from resumetailor.backend_api import (
    BackendAPI,
    create_real_backend,
    create_stub_backend,
)
from resumetailor.core.errors import PDFExtractError
from resumetailor.llm.litellm_adapter import LiteLLMAdapter
from resumetailor.llm.stub import (
    MOCK_CHAT_RESULT,
    MOCK_EVALUATION_RESULT,
    MOCK_EXTRACTED_TEXT,
    MOCK_GENERATION_RESULT_YAML,
    SimulatedBackendAPI,
)
from resumetailor.pdf.extract import MAX_BYTES, PyMuPDFAdapter
from resumetailor.rendering.runner import RenderCVAdapter

# ── deps._backend / get_backend ──────────────────────────────────────────


def test_get_backend_returns_stub_wiring_when_llm_mock_true(isolated_settings):
    from resumetailor.core.config import get_settings
    from resumetailor.deps import _backend, get_backend

    assert get_settings().LLM_MOCK is True
    backend = get_backend()
    assert isinstance(backend, BackendAPI)
    assert isinstance(backend._llm, SimulatedBackendAPI)
    # lru_cache: the same instance comes back on a second call.
    assert _backend() is backend


def test_backend_switches_to_real_wiring_when_llm_mock_false(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
):
    from resumetailor.core.config import get_settings
    from resumetailor.deps import _backend

    monkeypatch.setenv("LLM_MOCK", "false")
    get_settings.cache_clear()
    _backend.cache_clear()
    try:
        backend = _backend()
        assert isinstance(backend._llm, LiteLLMAdapter)
        assert isinstance(backend._pdf_render, RenderCVAdapter)
        assert isinstance(backend._pdf_extract, PyMuPDFAdapter)
    finally:
        get_settings.cache_clear()
        _backend.cache_clear()


# ── backend_api factories, called directly ───────────────────────────────


def test_create_stub_backend_wires_one_stub_into_all_three_ports():
    backend = create_stub_backend()
    assert backend._llm is backend._pdf_render
    assert backend._llm is backend._pdf_extract
    assert isinstance(backend._llm, SimulatedBackendAPI)


def test_create_real_backend_wires_the_three_real_adapters(isolated_settings):
    backend = create_real_backend()
    assert isinstance(backend._llm, LiteLLMAdapter)
    assert isinstance(backend._pdf_render, RenderCVAdapter)
    assert isinstance(backend._pdf_extract, PyMuPDFAdapter)


@pytest.mark.anyio
async def test_backend_api_facade_delegates_render_and_extract(mock_pdf_bytes: bytes):
    backend = create_stub_backend()
    assert await backend.render("cv: {}") == mock_pdf_bytes
    assert await backend.extract(mock_pdf_bytes) == MOCK_EXTRACTED_TEXT


# ── pdf.extract.PyMuPDFAdapter ───────────────────────────────────────────


@pytest.mark.anyio
async def test_extract_reads_text_from_a_real_pdf(mock_pdf_bytes: bytes):
    adapter = PyMuPDFAdapter()
    text = await adapter.extract(mock_pdf_bytes)
    assert isinstance(text, str)


@pytest.mark.anyio
async def test_extract_rejects_oversized_pdf():
    adapter = PyMuPDFAdapter()
    oversized = b"x" * (MAX_BYTES + 1)
    with pytest.raises(PDFExtractError, match="10 MB limit"):
        await adapter.extract(oversized)


@pytest.mark.anyio
async def test_extract_rejects_unreadable_bytes():
    adapter = PyMuPDFAdapter()
    with pytest.raises(PDFExtractError, match="Cannot open PDF"):
        await adapter.extract(b"not a pdf at all")


@pytest.mark.anyio
async def test_extract_rejects_too_many_pages(monkeypatch: pytest.MonkeyPatch):
    import pymupdf

    class _FakeDoc:
        page_count = 51

        def close(self) -> None:
            pass

        def __iter__(self):
            return iter([])

    monkeypatch.setattr(pymupdf, "open", lambda **_kw: _FakeDoc())
    adapter = PyMuPDFAdapter()
    with pytest.raises(PDFExtractError, match="max 50"):
        await adapter.extract(b"irrelevant, open() is stubbed")


# ── llm.stub.SimulatedBackendAPI.complete: one branch per prompt shape ───


@pytest.mark.anyio
async def test_stub_complete_routes_generation_prompt_with_schema():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [{"role": "system", "content": "You are ResumeTailor."}],
        response_format={"type": "json_schema"},
    )
    import json

    assert json.loads(result)["yaml_content"] == MOCK_GENERATION_RESULT_YAML


@pytest.mark.anyio
async def test_stub_complete_routes_generation_prompt_without_schema():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [{"role": "system", "content": "You are ResumeTailor."}]
    )
    assert result == MOCK_GENERATION_RESULT_YAML


@pytest.mark.anyio
async def test_stub_complete_routes_audit_prompt_echoes_cv_from_user_message():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [
            {"role": "system", "content": "You are ResumeAuditor."},
            {"role": "user", "content": "some preamble\ncv:\n  name: Real User"},
        ]
    )
    assert result.startswith("cv:")
    assert "Real User" in result


@pytest.mark.anyio
async def test_stub_complete_routes_audit_prompt_does_not_echo_trailing_sections():
    """Regression for D-74.

    The real audit prompt (``domain.tailoring.tailor``) is
    ``f"Draft:\\n{draft.yaml}\\n\\nMaster:\\n{master.yaml}\\n\\nJD:\\n{jd}"``.
    Slicing from the draft's own ``cv:`` key to the end of the string used to
    carry the Master section's ``cv:`` key (and the JD text) along with it,
    so the "echoed" result had two top-level ``cv:`` blocks -- invalid YAML
    under ``resume_schema.validate``.
    """
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [
            {"role": "system", "content": "You are ResumeAuditor."},
            {
                "role": "user",
                "content": (
                    "Draft:\ncv:\n  name: Draft User\n\n"
                    "Master:\ncv:\n  name: Master User\n\n"
                    "JD:\nSenior Engineer"
                ),
            },
        ]
    )
    assert result == "cv:\n  name: Draft User"
    assert result.count("cv:") == 1
    assert "Master User" not in result
    assert "Senior Engineer" not in result


@pytest.mark.anyio
async def test_stub_complete_audit_prompt_falls_back_when_no_cv_marker():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [
            {"role": "system", "content": "You are ResumeAuditor."},
            {"role": "user", "content": "no cv marker here"},
        ]
    )
    assert result == MOCK_GENERATION_RESULT_YAML


@pytest.mark.anyio
async def test_stub_complete_routes_evaluation_prompt():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [{"role": "system", "content": "Score this evaluation."}]
    )
    import json

    assert json.loads(result) == MOCK_EVALUATION_RESULT


@pytest.mark.anyio
async def test_stub_complete_routes_pdf_import_prompt_by_response_format():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [{"role": "system", "content": "Import this PDF."}],
        response_format={"type": "json_schema"},
    )
    import json

    assert json.loads(result)["yaml_content"] == MOCK_GENERATION_RESULT_YAML


@pytest.mark.anyio
async def test_stub_complete_falls_back_to_chat_result():
    stub = SimulatedBackendAPI()
    result = await stub.complete(
        [{"role": "system", "content": "You are a chat assistant."}]
    )
    import json

    assert json.loads(result) == MOCK_CHAT_RESULT


@pytest.mark.anyio
async def test_stub_stream_yields_the_chat_text():
    stub = SimulatedBackendAPI()
    gen = await stub.stream([{"role": "user", "content": "hi"}])
    chunks = [chunk async for chunk in gen]
    assert chunks == [MOCK_CHAT_RESULT["text"]]


# ── api.openapi: install_openapi caching, main() CLI ─────────────────────


def test_install_openapi_caches_the_built_document():
    from resumetailor.api.openapi import build_openapi, install_openapi
    from resumetailor.main import app

    saved = app.openapi_schema
    saved_fn = app.openapi
    try:
        app.openapi_schema = None
        install_openapi(app)
        first = app.openapi()
        assert first == build_openapi(app)
        # Mutate the cache directly to prove the second call reads it back
        # rather than rebuilding, i.e. the None-check branch is exercised once.
        sentinel = {"cached": True}
        app.openapi_schema = sentinel
        assert app.openapi() is sentinel
    finally:
        app.openapi_schema = saved
        app.openapi = saved_fn  # type: ignore[method-assign]


def test_openapi_main_writes_the_document(tmp_path):
    from resumetailor.api.openapi import main

    destination = tmp_path / "nested" / "openapi.json"
    exit_code = main([str(destination)])
    assert exit_code == 0
    assert destination.exists()
    assert '"openapi"' in destination.read_text(encoding="utf-8")


def test_openapi_main_reports_usage_error_on_bad_args():
    from resumetailor.api.openapi import main

    assert main([]) == 2
    assert main(["a", "b"]) == 2
