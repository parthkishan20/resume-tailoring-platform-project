"""Protocols for the three swappable adapters.

MOVED BY TASK 1.3. `LLMPort` becomes `llm/port.py`; `PDFRenderPort` moves next
to the render runner in `rendering/`; `PDFExtractPort` moves to `pdf/`.

The exception hierarchy that used to live here has already gone: it is
`core/errors.py` now, because the HTTP mapping belongs with the exceptions and
not in four handlers in `main.py`. The names are re-exported below so that
`adapters.py`, the routers and the tests keep importing them from where they
always have, until 1.3 rewrites those call sites.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from resumetailor.core.errors import (
    BackendError,
    LLMAuthError,
    LLMUnavailableError,
    PDFExtractError,
    RenderError,
)

__all__ = [
    "BackendError",
    "LLMAuthError",
    "LLMPort",
    "LLMUnavailableError",
    "PDFExtractError",
    "PDFExtractPort",
    "PDFRenderPort",
    "RenderError",
]


@runtime_checkable
class LLMPort(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str: ...

    async def stream(
        self,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class PDFRenderPort(Protocol):
    async def render(self, yaml_content: str) -> bytes: ...


@runtime_checkable
class PDFExtractPort(Protocol):
    async def extract(self, pdf_bytes: bytes) -> str: ...
