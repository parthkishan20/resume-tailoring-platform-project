"""The PDF-text boundary: bytes in, text out."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PDFExtractPort(Protocol):
    async def extract(self, pdf_bytes: bytes) -> str: ...
