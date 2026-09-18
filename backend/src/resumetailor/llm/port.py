"""The LLM boundary: messages in, text or a stream of text (and tool calls) out."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One function the model may call, declared the way a provider wants it.

    ``parameters`` is a JSON Schema object, handed to the provider verbatim
    (translated to whatever shape the wire format wants by the adapter, not by
    a caller). Declared once per tool in :mod:`resumetailor.domain.assistant`
    and handed to :meth:`LLMPort.stream` unchanged.
    """

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One request from the model to run a tool, as the provider sent it.

    ``arguments`` is the raw JSON text the model produced, not yet parsed: a
    provider is under no obligation to send well-formed JSON, so the boundary
    between "the provider sent garbage" and "the arguments failed validation"
    belongs to the caller, which knows the schema and can produce a client-safe
    message either way. See :mod:`resumetailor.domain.assistant`.
    """

    id: str
    name: str
    arguments: str


#: What :meth:`LLMPort.stream` yields: a chunk of assistant text, or one
#: completed request to run a tool. A provider's streamed response interleaves
#: these in principle; in practice a turn is either text or tool calls, and the
#: caller does not have to care which — it reads both off the same iterator.
StreamEvent = str | ToolCall


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
        tools: Sequence[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamEvent]: ...
