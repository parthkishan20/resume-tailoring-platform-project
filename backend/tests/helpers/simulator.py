"""Per-port configurable simulators for route tests.

:class:`ConfigurableBackendAPI` is the seam every route test runs through. It
exposes the same four methods the real backend facade does — ``complete``,
``stream``, ``render``, ``extract`` — and lets a test pin any one of them to a
fixed response or a fixed exception, then assert on what the route asked for.

Three things make it useful rather than merely convenient:

* **Call counters.** ``sim_llm.complete_call_count == 2`` is how the
  generate-then-audit two-pass pipeline is pinned. A refactor that quietly
  collapses it to one pass fails a test instead of shipping.
* **Last-call capture.** ``sim_llm.last_complete_messages`` is how rules
  injection is verified: the assertion is on the prompt actually sent, not on a
  mock's call log.
* **Error injection.** ``set_*_error`` is what makes the ``except`` branches in
  the routers reachable from a four-line test.

Duck-typed, deliberately
------------------------
This class does **not** subclass ``resumetailor.backend_api.BackendAPI``. It
matches its shape and is injected through FastAPI's ``dependency_overrides``,
which does no runtime type checking. Subclassing would tie the whole test
harness to one module path at a moment when task 1.3 is moving that module, and
would buy nothing: the property worth having is that the stub answers the same
calls the real facade does, and that is a test, not an inheritance edge.

Unset ports fall back to the canned responses in ``tests.helpers.llm_stub``, so
a test that does not care what the LLM said still gets something realistic and
identical on every run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from tests.helpers import llm_stub

# The default render output. Not a real PDF, and not meant to be: a test that
# needs real PDF bytes should use the `mock_pdf_bytes` fixture, which reads the
# committed fixture file.
DEFAULT_RENDER_BYTES = b"%PDF-1.4 mock"


class SimulatedLLMPort:
    """Stands in for the LLM. Deterministic by default, pinnable per test."""

    def __init__(self) -> None:
        self._complete_response: str | None = None
        self._complete_error: Exception | None = None
        self._stream_chunks: list[str] | None = None
        self._stream_error: Exception | None = None
        self.complete_call_count: int = 0
        self.stream_call_count: int = 0
        self.last_complete_messages: list[dict] | None = None
        self.last_stream_messages: list[dict] | None = None

    def set_complete_response(self, response: str) -> None:
        self._complete_response = response
        self._complete_error = None

    def set_complete_error(self, exc: Exception) -> None:
        self._complete_error = exc

    def set_stream_chunks(self, chunks: list[str]) -> None:
        self._stream_chunks = list(chunks)
        self._stream_error = None

    def set_stream_error(self, exc: Exception) -> None:
        self._stream_error = exc

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        self.complete_call_count += 1
        self.last_complete_messages = messages
        if self._complete_error:
            raise self._complete_error
        if self._complete_response is not None:
            return self._complete_response
        return llm_stub.respond(messages, response_format)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        self.stream_call_count += 1
        self.last_stream_messages = messages
        error = self._stream_error
        if self._stream_chunks is not None:
            chunks = list(self._stream_chunks)
        else:
            chunks = [str(llm_stub.CANNED_CHAT_RESULT["text"])]

        async def _gen() -> AsyncIterator[str]:
            if error:
                raise error
            for chunk in chunks:
                yield chunk

        return _gen()


class SimulatedPDFRenderPort:
    def __init__(self) -> None:
        self._response: bytes = DEFAULT_RENDER_BYTES
        self._error: Exception | None = None
        self.call_count: int = 0
        self.last_yaml_content: str | None = None

    def set_response(self, pdf_bytes: bytes) -> None:
        self._response = pdf_bytes
        self._error = None

    def set_error(self, exc: Exception) -> None:
        self._error = exc

    async def render(self, yaml_content: str) -> bytes:
        self.call_count += 1
        self.last_yaml_content = yaml_content
        if self._error:
            raise self._error
        return self._response


class SimulatedPDFExtractPort:
    def __init__(self) -> None:
        self._response: str = llm_stub.CANNED_EXTRACTED_TEXT
        self._error: Exception | None = None
        self.call_count: int = 0
        self.last_pdf_bytes: bytes | None = None

    def set_response(self, text: str) -> None:
        self._response = text
        self._error = None

    def set_error(self, exc: Exception) -> None:
        self._error = exc

    async def extract(self, pdf_bytes: bytes) -> str:
        self.call_count += 1
        self.last_pdf_bytes = pdf_bytes
        if self._error:
            raise self._error
        return self._response


class ConfigurableBackendAPI:
    """The backend facade, with every port replaced by a controllable stub."""

    def __init__(self) -> None:
        self.sim_llm = SimulatedLLMPort()
        self.sim_pdf_render = SimulatedPDFRenderPort()
        self.sim_pdf_extract = SimulatedPDFExtractPort()

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        return await self.sim_llm.complete(messages, response_format)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        return await self.sim_llm.stream(messages)

    async def render(self, yaml_content: str) -> bytes:
        return await self.sim_pdf_render.render(yaml_content)

    async def extract(self, pdf_bytes: bytes) -> str:
        return await self.sim_pdf_extract.extract(pdf_bytes)
