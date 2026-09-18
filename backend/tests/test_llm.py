"""
LLM-layer test suite (Wave 1).

Async tests use @pytest.mark.anyio (anyio is installed; pytest-asyncio is not).
"""
from __future__ import annotations

import asyncio
import json
import pytest

from resumetailor.ports import (
    LLMPort,
    PDFRenderPort,
    PDFExtractPort,
    LLMAuthError,
    LLMUnavailableError,
    RenderError,
    PDFExtractError,
    BackendError,
)


# ---------------------------------------------------------------------------
# Task 1 — Port protocols and exception hierarchy
# ---------------------------------------------------------------------------

def test_exception_hierarchy():
    assert issubclass(LLMAuthError, BackendError)
    assert issubclass(LLMUnavailableError, BackendError)
    assert issubclass(RenderError, BackendError)
    assert issubclass(PDFExtractError, BackendError)


def test_llm_port_is_protocol():
    from typing import Protocol
    assert issubclass(LLMPort, Protocol)


def test_ports_are_runtime_checkable():
    # A class with the right shape satisfies the protocol
    class FakeLLM:
        async def complete(self, messages, response_format=None):
            return ""

        async def stream(self, messages):
            yield ""

    assert isinstance(FakeLLM(), LLMPort)


# ---------------------------------------------------------------------------
# Task 2 — Real adapters (error mapping only — no real LLM calls)
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from resumetailor.adapters import LiteLLMAdapter


@pytest.mark.anyio
async def test_litellm_adapter_maps_auth_error():
    import litellm.exceptions as llm_exc
    adapter = LiteLLMAdapter(model="openrouter/test/model", api_key="key")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = llm_exc.AuthenticationError(
            "bad key", llm_provider="openrouter", model="test"
        )
        with pytest.raises(LLMAuthError):
            await adapter.complete([{"role": "user", "content": "hi"}])


@pytest.mark.anyio
async def test_litellm_adapter_maps_rate_limit_to_unavailable():
    import litellm.exceptions as llm_exc
    adapter = LiteLLMAdapter(model="openrouter/test/model", api_key="key")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = llm_exc.RateLimitError(
            "rate limited", llm_provider="openrouter", model="test"
        )
        with pytest.raises(LLMUnavailableError):
            await adapter.complete([{"role": "user", "content": "hi"}])


@pytest.mark.anyio
async def test_rendercv_adapter_maps_nonzero_exit_to_render_error():
    from resumetailor.adapters import RenderCVAdapter
    adapter = RenderCVAdapter()
    proc_mock = MagicMock()
    proc_mock.returncode = 1
    proc_mock.communicate = AsyncMock(return_value=(b"", b"YAML error"))
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with pytest.raises(RenderError):
            await adapter.render("bad: yaml")


@pytest.mark.anyio
async def test_rendercv_adapter_passes_design_flag_and_embeds_locale():
    from resumetailor.adapters import RenderCVAdapter, _CONFIG_DIR
    import yaml as _yaml
    adapter = RenderCVAdapter()
    proc_mock = MagicMock()
    proc_mock.returncode = 1  # fail early — we only care about the call args
    proc_mock.communicate = AsyncMock(return_value=(b"", b"err"))

    dumped_data = []
    real_dump = _yaml.dump

    def capture_dump(data, **kwargs):
        dumped_data.append(data)
        return real_dump(data, **kwargs)

    with patch("resumetailor.adapters.yaml.dump", side_effect=capture_dump):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = proc_mock
            with pytest.raises(RenderError):
                await adapter.render("cv:\n  name: Test\n")

    cmd_str = " ".join(str(a) for a in mock_exec.call_args[0])
    assert "--design" in cmd_str
    assert str(_CONFIG_DIR / "design.yaml") in cmd_str
    assert "--locale" not in cmd_str
    assert dumped_data and "locale" in dumped_data[0]


@pytest.mark.anyio
async def test_pymupdf_adapter_oversized_pdf_raises_extract_error():
    from resumetailor.adapters import PyMuPDFAdapter
    adapter = PyMuPDFAdapter()
    with pytest.raises(PDFExtractError):
        await adapter.extract(b"x" * (adapter._MAX_BYTES + 1))


# ---------------------------------------------------------------------------
# Task 3 — Mock PDF fixture + Tier 1 SimulatedBackendAPI
# ---------------------------------------------------------------------------

from resumetailor.simulator import (
    SimulatedBackendAPI,
    MOCK_CHAT_RESULT,
    MOCK_GENERATION_RESULT_YAML,
    MOCK_EVALUATION_RESULT,
    MOCK_IMPORT_YAML,
)


def test_mock_constants_match_plan():
    assert MOCK_EVALUATION_RESULT["match_score"] == 72
    assert "Kubernetes" in MOCK_EVALUATION_RESULT["missing_keywords"]
    assert "Python" in MOCK_EVALUATION_RESULT["matched_keywords"]
    assert MOCK_CHAT_RESULT["action"] is None
    assert "cv:" in MOCK_GENERATION_RESULT_YAML
    assert MOCK_IMPORT_YAML == MOCK_GENERATION_RESULT_YAML


@pytest.mark.anyio
async def test_simulator_stream_yields_chat_text():
    sim = SimulatedBackendAPI()
    chunks = []
    async for chunk in await sim.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)
    assert len(chunks) > 0
    assert "".join(chunks) == MOCK_CHAT_RESULT["text"]


@pytest.mark.anyio
async def test_simulator_render_returns_pdf_bytes():
    sim = SimulatedBackendAPI()
    pdf = await sim.render("cv:\n  name: Test")
    assert pdf[:4] == b"%PDF"


@pytest.mark.anyio
async def test_simulator_extract_returns_text():
    sim = SimulatedBackendAPI()
    text = await sim.extract(b"%PDF-1.4 fake")
    assert "Mock" in text


# ---------------------------------------------------------------------------
# Task 4 — Tier 2 ConfigurableBackendAPI (helpers/simulator.py)
# Note: ConfigurableBackendAPI imports BackendAPI from resumetailor.backend_api which
# is created by Wave 2 Backend API Engineer. Tests are skipped until then.
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_configurable_backend_llm_complete():
    try:
        from tests.helpers.simulator import ConfigurableBackendAPI
    except ImportError:
        pytest.skip("resumetailor.backend_api not yet available (Wave 2)")
    api = ConfigurableBackendAPI()
    api.sim_llm.set_complete_response("hello world")
    result = await api.complete([{"role": "user", "content": "hi"}])
    assert result == "hello world"
    assert api.sim_llm.complete_call_count == 1


@pytest.mark.anyio
async def test_configurable_backend_llm_error():
    try:
        from tests.helpers.simulator import ConfigurableBackendAPI
    except ImportError:
        pytest.skip("resumetailor.backend_api not yet available (Wave 2)")
    api = ConfigurableBackendAPI()
    api.sim_llm.set_complete_error(LLMUnavailableError("down"))
    with pytest.raises(LLMUnavailableError):
        await api.complete([{"role": "user", "content": "hi"}])


@pytest.mark.anyio
async def test_configurable_backend_render_error():
    try:
        from tests.helpers.simulator import ConfigurableBackendAPI
    except ImportError:
        pytest.skip("resumetailor.backend_api not yet available (Wave 2)")
    api = ConfigurableBackendAPI()
    api.sim_pdf_render.set_error(RenderError("bad yaml"))
    with pytest.raises(RenderError):
        await api.render("bad yaml")
