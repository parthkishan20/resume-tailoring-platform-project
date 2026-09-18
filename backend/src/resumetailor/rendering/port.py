"""The render boundary: YAML in, PDF bytes out."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PDFRenderPort(Protocol):
    async def render(self, yaml_content: str) -> bytes: ...
