"""
Tier 2: Per-port configurable simulators for unit tests.

ConfigurableBackendAPI extends BackendAPI (from resumetailor.backend_api, created by
Wave 2 Backend API Engineer). Until Wave 2 is complete this file will raise
an ImportError at import time — that is expected and handled in test_llm.py
via pytest.skip().
"""
from __future__ import annotations
from typing import AsyncIterator

from resumetailor.backend_api import BackendAPI  # available after Wave 2


class SimulatedLLMPort:
    def __init__(self) -> None:
        self._complete_response: str = ""
        self._complete_error: Exception | None = None
        self._stream_chunks: list[str] = []
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
        self._stream_chunks = chunks
        self._stream_error = None

    def set_stream_error(self, exc: Exception) -> None:
        self._stream_error = exc

    async def complete(self, messages: list[dict], response_format: dict | None = None) -> str:
        self.complete_call_count += 1
        self.last_complete_messages = messages
        if self._complete_error:
            raise self._complete_error
        return self._complete_response

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        self.stream_call_count += 1
        self.last_stream_messages = messages
        error = self._stream_error
        chunks = list(self._stream_chunks)

        async def _gen() -> AsyncIterator[str]:
            if error:
                raise error
            for chunk in chunks:
                yield chunk

        return _gen()


class SimulatedPDFRenderPort:
    def __init__(self) -> None:
        self._response: bytes = b"%PDF-1.4 mock"
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
        self._response: str = "Mock resume text"
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


class ConfigurableBackendAPI(BackendAPI):
    """Tier 2 per-port configurable simulator for route unit tests."""

    def __init__(self) -> None:
        self.sim_llm = SimulatedLLMPort()
        self.sim_pdf_render = SimulatedPDFRenderPort()
        self.sim_pdf_extract = SimulatedPDFExtractPort()
        super().__init__(
            llm=self.sim_llm,
            pdf_render=self.sim_pdf_render,
            pdf_extract=self.sim_pdf_extract,
        )
