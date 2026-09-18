"""The facade over the three adapters, and the two ways of assembling it.

``BackendAPI`` is what a route holds. It knows nothing about LiteLLM, RenderCV
or PyMuPDF — only the three protocols in ``llm/port.py``,
``rendering/port.py`` and ``pdf/port.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from resumetailor.llm.port import LLMPort
from resumetailor.pdf.port import PDFExtractPort
from resumetailor.rendering.port import PDFRenderPort


class BackendAPI:
    def __init__(
        self,
        llm: LLMPort,
        pdf_render: PDFRenderPort,
        pdf_extract: PDFExtractPort,
    ) -> None:
        self._llm = llm
        self._pdf_render = pdf_render
        self._pdf_extract = pdf_extract

    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        return await self._llm.complete(messages, response_format)

    async def stream(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        return await self._llm.stream(messages)

    async def render(self, yaml_content: str) -> bytes:
        return await self._pdf_render.render(yaml_content)

    async def extract(self, pdf_bytes: bytes) -> str:
        return await self._pdf_extract.extract(pdf_bytes)


def create_real_backend() -> BackendAPI:
    """The production wiring: a real provider, a real renderer, a real PDF reader."""
    from resumetailor.core.config import get_settings  # noqa: PLC0415
    from resumetailor.llm.litellm_adapter import LiteLLMAdapter  # noqa: PLC0415
    from resumetailor.pdf.extract import PyMuPDFAdapter  # noqa: PLC0415
    from resumetailor.rendering.runner import RenderCVAdapter  # noqa: PLC0415

    settings = get_settings()
    return BackendAPI(
        llm=LiteLLMAdapter(model=settings.LLM_MODEL, api_key=settings.llm_api_key),
        pdf_render=RenderCVAdapter(),
        pdf_extract=PyMuPDFAdapter(),
    )


def create_stub_backend() -> BackendAPI:
    """The ``LLM_MOCK`` wiring: one deterministic object behind all three ports.

    ``deps`` used to return the stub object itself where a ``BackendAPI`` was
    declared — structurally similar, formally a lie, and pinned open in
    ``pyproject.toml`` as a mypy ``return-value`` exemption owned by this task.
    Wrapping it closes that.
    """
    from resumetailor.llm.stub import SimulatedBackendAPI  # noqa: PLC0415

    stub = SimulatedBackendAPI()
    return BackendAPI(llm=stub, pdf_render=stub, pdf_extract=stub)
