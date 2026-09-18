"""The LLM boundary: messages in, text or a stream of text out."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


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
