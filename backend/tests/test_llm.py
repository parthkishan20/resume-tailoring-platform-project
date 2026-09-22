"""
Adapter-layer test suite.

Async tests use @pytest.mark.anyio (anyio is installed; pytest-asyncio is not).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from resumetailor.core.errors import (
    BackendError,
    LLMAuthError,
    LLMUnavailableError,
    PDFExtractError,
    RenderError,
)
from resumetailor.llm.port import LLMPort
from resumetailor.pdf.port import PDFExtractPort
from resumetailor.rendering.port import PDFRenderPort


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


def test_render_and_extract_ports_are_runtime_checkable():
    class FakeRenderer:
        async def render(self, yaml_content):
            return b"%PDF"

    class FakeExtractor:
        async def extract(self, pdf_bytes):
            return ""

    assert isinstance(FakeRenderer(), PDFRenderPort)
    assert isinstance(FakeExtractor(), PDFExtractPort)


# ---------------------------------------------------------------------------
# Task 2 — Real adapters (error mapping only — no real LLM calls)
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from resumetailor.llm.litellm_adapter import LiteLLMAdapter
from resumetailor.core.config import Settings as _Settings
from resumetailor.core.security import SecurityPolicy as _SecurityPolicy
from resumetailor.rendering.config import RenderProfile
from resumetailor.rendering.runner import RenderCVAdapter


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
async def test_litellm_adapter_passes_key_per_call_not_via_environ(monkeypatch):
    """D-49: the key must not be written to the process environment.

    It used to be set in the constructor, from which every child process —
    including the rendercv subprocess — inherited it.

    The precondition is a *present* sentinel, not an absent key. Deleting the
    key outright used to be how this test set up its precondition, but that
    leaves a real gap for anything importing `litellm` for the first time
    during the test to fill: `litellm/__init__.py` calls
    `dotenv.load_dotenv(override=False)` at import time, and `load_dotenv`
    only skips a key that is already *present* in `os.environ` — an absent
    one gets filled in from whatever `.env` `find_dotenv()` walks up and
    finds, which in this repo's layout is the real key at the repo root. A
    present, obviously-fake sentinel closes that gap and is a strictly more
    direct test of the actual claim: the adapter must never touch this key,
    whatever value it holds.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-unrelated-to-the-adapter")
    adapter = LiteLLMAdapter(model="openrouter/test/model", api_key="secret-key")
    import os

    assert os.environ["OPENAI_API_KEY"] == "sentinel-unrelated-to-the-adapter"

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="hi"))]
        )
        await adapter.complete([{"role": "user", "content": "hi"}])

    assert os.environ["OPENAI_API_KEY"] == "sentinel-unrelated-to-the-adapter"
    assert mock_llm.call_args.kwargs["api_key"] == "secret-key"


@pytest.mark.anyio
async def test_litellm_adapter_calls_on_request_once_per_complete():
    """The rate-limit counter's hook fires once per logical call, before it."""
    calls: list[str] = []

    async def on_request() -> None:
        calls.append("recorded")

    adapter = LiteLLMAdapter(
        model="openrouter/test/model", api_key="key", on_request=on_request
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="hi"))]
        )
        await adapter.complete([{"role": "user", "content": "hi"}])

    assert calls == ["recorded"]


@pytest.mark.anyio
async def test_litellm_adapter_calls_on_request_before_stream_is_sent():
    """A stream nobody iterates never opens a connection, so it never counts."""
    calls: list[str] = []

    async def on_request() -> None:
        calls.append("recorded")

    adapter = LiteLLMAdapter(
        model="openrouter/test/model", api_key="key", on_request=on_request
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="hi"))]
        )

        stream = await adapter.stream([{"role": "user", "content": "hi"}])
        assert calls == []  # not sent yet — nobody has iterated

        async for _ in stream:
            pass

    assert calls == ["recorded"]


@pytest.mark.anyio
async def test_litellm_adapter_on_request_failure_does_not_break_the_call():
    """A broken counter must not be able to fail the user's actual generation."""

    async def on_request() -> None:
        raise RuntimeError("db is down")

    adapter = LiteLLMAdapter(
        model="openrouter/test/model", api_key="key", on_request=on_request
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="hi"))]
        )
        result = await adapter.complete([{"role": "user", "content": "hi"}])

    assert result == "hi"


@pytest.mark.anyio
async def test_rendercv_adapter_maps_nonzero_exit_to_render_error():
    adapter = RenderCVAdapter()
    proc_mock = MagicMock()
    proc_mock.returncode = 1
    proc_mock.communicate = AsyncMock(return_value=(b"", b"YAML error"))
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with pytest.raises(RenderError):
            await adapter.render("bad: yaml")


@pytest.mark.anyio
async def test_rendercv_adapter_passes_all_three_overlay_files():
    """D-16: the locale is passed as `--locale-catalog PATH`, not merged in.

    `rendercv render --help` on 2.8 has no `--locale` flag at all; the
    workaround this replaces merged locale.yaml's contents into the top level
    of the user's own document.
    """
    profile = RenderProfile()
    adapter = RenderCVAdapter(profile)
    proc_mock = MagicMock()
    proc_mock.returncode = 1  # fail early — we only care about the call args
    proc_mock.communicate = AsyncMock(return_value=(b"", b"err"))

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with pytest.raises(RenderError):
            await adapter.render("cv:\n  name: Test\n")

    cmd = [str(a) for a in mock_exec.call_args[0]]
    assert "--design" in cmd
    assert cmd[cmd.index("--design") + 1] == str(profile.design_path)
    assert "--locale-catalog" in cmd
    assert cmd[cmd.index("--locale-catalog") + 1] == str(profile.locale_path)
    assert "--settings" in cmd
    assert cmd[cmd.index("--settings") + 1] == str(profile.settings_path)
    # `--dont-generate-typst` must never be passed: rendercv's own help says it
    # implicitly disables PDF, so passing it produces no PDF at all.
    assert "--dont-generate-typst" not in cmd


@pytest.mark.anyio
async def test_rendercv_adapter_does_not_touch_the_document():
    """The YAML handed to rendercv is the YAML we were given, byte for byte."""
    adapter = RenderCVAdapter()
    written: list[str] = []
    proc_mock = MagicMock()
    proc_mock.returncode = 1
    proc_mock.communicate = AsyncMock(return_value=(b"", b"err"))

    original = "cv:\n  name: Test\n"
    real_write_text = Path.write_text

    def capture(self, data, **kwargs):
        written.append(data)
        return real_write_text(self, data, **kwargs)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with patch.object(Path, "write_text", capture):
            with pytest.raises(RenderError):
                await adapter.render(original)

    assert written == [original]


@pytest.mark.anyio
async def test_rendercv_adapter_kills_the_subprocess_on_timeout():
    """D-07: a hung render must not hold the request, nor orphan the child."""
    profile = RenderProfile(timeout_s=0.01)
    adapter = RenderCVAdapter(profile)

    async def never_returns():
        await asyncio.sleep(10)

    proc_mock = MagicMock()
    proc_mock.returncode = None
    proc_mock.communicate = MagicMock(side_effect=never_returns)
    proc_mock.wait = AsyncMock(return_value=-9)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with pytest.raises(RenderError, match="timed out"):
            await adapter.render("cv:\n  name: Test\n")

    proc_mock.kill.assert_called_once()
    proc_mock.wait.assert_awaited()


@pytest.mark.anyio
async def test_rendercv_adapter_bounds_concurrent_renders():
    """D-07: N concurrent generations must not spawn N typst processes."""
    profile = RenderProfile(max_concurrent=2)
    adapter = RenderCVAdapter(profile)
    live = 0
    peak = 0

    async def slow_communicate():
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1
        return (b"", b"err")

    def make_proc(*args, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = MagicMock(side_effect=slow_communicate)
        return proc

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = make_proc
        results = await asyncio.gather(
            *(adapter.render("cv:\n  name: Test\n") for _ in range(6)),
            return_exceptions=True,
        )

    assert all(isinstance(r, RenderError) for r in results)
    assert peak <= 2


def test_render_profile_reads_the_configured_theme():
    """D-18: the backstop must probe with the theme the renderer actually uses."""
    assert RenderProfile().theme() == "engineeringresumes"


def test_render_profile_is_env_overridable(monkeypatch, tmp_path):
    """D-15: the overlay paths leave the package, so no repo file is required."""
    design = tmp_path / "design.yaml"
    design.write_text("design:\n  theme: sb2nov\n", encoding="utf-8")
    monkeypatch.setenv("RENDER_DESIGN_PATH", str(design))
    monkeypatch.setenv("RENDER_TIMEOUT_S", "7.5")
    monkeypatch.setenv("RENDER_MAX_CONCURRENT", "9")
    profile = RenderProfile()
    assert profile.design_path == design
    assert profile.theme() == "sb2nov"
    assert profile.timeout_s == 7.5
    assert profile.max_concurrent == 9


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(RenderProfile, id="RenderProfile"),
        pytest.param(_SecurityPolicy, id="SecurityPolicy"),
        pytest.param(_Settings, id="Settings"),
    ],
)
def test_settings_classes_ignore_unrelated_dotenv_keys(factory, monkeypatch, tmp_path):
    """One `.env` is shared by three settings classes; none may choke on it.

    An `env_prefix` does not, on its own, keep the namespaces apart:
    pydantic-settings reads *every* key in `.env` and then rejects the ones
    that are not fields of the class being built. So the `.env` a developer
    copies from `.env.example` made all three raise `extra_forbidden` --
    `RenderProfile()` took down every real (non-`LLM_MOCK`) render including
    `GET /api/master-resume/preview`, and `SecurityPolicy()` is built by the
    middleware on every request, so it turned into a blanket 500 on every
    route. Docker never reproduced any of it because `.dockerignore` keeps
    `.env` out of the image.
    """
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=sk-or-v1-notarealkey\n"
        "LLM_MODEL=openrouter/openai/gpt-oss-120b\n"
        "LLM_MOCK=false\n"
        "RENDER_TIMEOUT_S=12.5\n"
        "SECURITY_MAX_UPLOAD_BODY_BYTES=4096\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    # The keys belonging to the other two classes are ignored, not fatal.
    factory()

    # ...and each prefixed class still reads its own key out of that same file.
    assert RenderProfile().timeout_s == 12.5
    assert _SecurityPolicy().max_upload_body_bytes == 4096


@pytest.mark.anyio
async def test_pymupdf_adapter_oversized_pdf_raises_extract_error():
    from resumetailor.pdf.extract import MAX_BYTES, PyMuPDFAdapter

    adapter = PyMuPDFAdapter()
    with pytest.raises(PDFExtractError):
        await adapter.extract(b"x" * (MAX_BYTES + 1))


# ---------------------------------------------------------------------------
# Task 3 — Mock PDF fixture + Tier 1 SimulatedBackendAPI
# ---------------------------------------------------------------------------

from resumetailor.llm.stub import (
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


def test_fixture_pdf_ships_inside_the_package():
    """D-64: the e2e image excludes backend/tests/, so the fixture cannot live there."""
    from resumetailor.llm import stub
    import resumetailor

    package_root = Path(resumetailor.__file__).resolve().parent
    assert stub._FIXTURE_PDF.is_file()
    assert package_root in stub._FIXTURE_PDF.parents


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


def test_stub_backend_is_a_real_backend_api():
    """deps used to return the stub where a BackendAPI was declared."""
    from resumetailor.backend_api import BackendAPI, create_stub_backend

    assert isinstance(create_stub_backend(), BackendAPI)


# ---------------------------------------------------------------------------
# Task 3.3 — Tool-call simulation (D-33)
#
# Deterministic dispatch by trigger phrase, so `LLM_MOCK=true` (this same
# class, run for real by the e2e stack) and the pytest suite exercise one
# routing table rather than two. See `llm/stub.py`'s "Tool-call simulation"
# section for why a fixed trigger phrase stands in for a real model's
# judgment here.
# ---------------------------------------------------------------------------

from resumetailor.llm.port import ToolCall, ToolSpec
from resumetailor.llm.stub import MOCK_TOOL_CALL_ID, MOCK_TOOL_TRIGGERS

_ANY_TOOL = (
    ToolSpec(name="noop", description="unused", parameters={"type": "object"}),
)


@pytest.mark.anyio
async def test_simulator_stream_ignores_triggers_when_no_tools_are_offered():
    """A trigger phrase alone does nothing: `tools` has to be non-empty too."""
    sim = SimulatedBackendAPI()
    events = [
        e
        async for e in await sim.stream(
            [{"role": "user", "content": "please generate a tailored resume"}]
        )
    ]
    assert events == [MOCK_CHAT_RESULT["text"]]


@pytest.mark.anyio
@pytest.mark.parametrize("phrase", list(MOCK_TOOL_TRIGGERS))
async def test_simulator_stream_triggers_the_matching_tool(phrase: str):
    expected_name, expected_arguments = MOCK_TOOL_TRIGGERS[phrase]
    sim = SimulatedBackendAPI()

    events = [
        e
        async for e in await sim.stream(
            [{"role": "user", "content": f"Please {phrase} for me"}], tools=_ANY_TOOL
        )
    ]

    assert events == [
        ToolCall(
            id=MOCK_TOOL_CALL_ID,
            name=expected_name,
            arguments=json.dumps(expected_arguments),
        )
    ]


@pytest.mark.anyio
async def test_simulator_stream_with_tools_and_no_matching_trigger_answers_in_text():
    sim = SimulatedBackendAPI()
    events = [
        e
        async for e in await sim.stream(
            [{"role": "user", "content": "how are you today?"}], tools=_ANY_TOOL
        )
    ]
    assert events == [MOCK_CHAT_RESULT["text"]]


@pytest.mark.anyio
async def test_simulator_stream_does_not_retrigger_once_a_tool_has_run():
    """One tool call per turn (ADR 0005's fixed four-tool set), even on a
    trigger phrase: once the conversation already carries a `role: "tool"`
    message, the stub answers in text so a deterministic test's second round
    always terminates the turn.
    """
    sim = SimulatedBackendAPI()
    messages = [
        {"role": "user", "content": "please generate a tailored resume"},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "tool_call_id": "call-1", "content": "done"},
    ]

    events = [e async for e in await sim.stream(messages, tools=_ANY_TOOL)]

    assert events == [MOCK_CHAT_RESULT["text"]]


# ---------------------------------------------------------------------------
# Task 4 — Tier 2 ConfigurableBackendAPI (helpers/simulator.py)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_configurable_backend_llm_complete():
    from tests.helpers.simulator import ConfigurableBackendAPI

    api = ConfigurableBackendAPI()
    api.sim_llm.set_complete_response("hello world")
    result = await api.complete([{"role": "user", "content": "hi"}])
    assert result == "hello world"
    assert api.sim_llm.complete_call_count == 1


@pytest.mark.anyio
async def test_configurable_backend_llm_error():
    from tests.helpers.simulator import ConfigurableBackendAPI

    api = ConfigurableBackendAPI()
    api.sim_llm.set_complete_error(LLMUnavailableError("down"))
    with pytest.raises(LLMUnavailableError):
        await api.complete([{"role": "user", "content": "hi"}])


@pytest.mark.anyio
async def test_configurable_backend_render_error():
    from tests.helpers.simulator import ConfigurableBackendAPI

    api = ConfigurableBackendAPI()
    api.sim_pdf_render.set_error(RenderError("bad yaml"))
    with pytest.raises(RenderError):
        await api.render("bad yaml")
