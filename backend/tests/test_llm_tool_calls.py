"""Task 3.3: tool-call streaming in `LiteLLMAdapter`, closing D-33's adapter half.

Task 2.1 built the streaming lifecycle (`test_llm_bounds.py`) and deliberately
left `tools` unwired -- this is that parameter. The fake chunk shapes below
extend `test_llm_bounds.py`'s `_Chunk`/`_Choice` doubles with `delta.tool_calls`,
because a hand-written double is the only version of this that keeps "content
is absent" and "tool_calls is present" distinguishable, which a `MagicMock`
attribute is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from resumetailor.llm.config import LLMProfile
from resumetailor.llm.litellm_adapter import LiteLLMAdapter
from resumetailor.llm.port import StreamEvent, ToolCall, ToolSpec

MODEL = "openrouter/test/model"
FAST = LLMProfile(timeout_s=5.0, max_attempts=3, backoff_base_s=0.001, max_tokens=123)

ECHO_TOOL = ToolSpec(
    name="echo",
    description="Echo something back.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
)


@dataclass
class _FunctionDelta:
    name: str | None = None
    arguments: str | None = None


@dataclass
class _ToolCallDelta:
    index: int
    id: str | None = None
    function: _FunctionDelta | None = None


@dataclass
class _Delta:
    content: str | None = None
    tool_calls: list[_ToolCallDelta] | None = None


@dataclass
class _Choice:
    delta: _Delta = field(default_factory=_Delta)


@dataclass
class _Chunk:
    choices: list[_Choice]


class _FakeStream:
    def __init__(self, chunks: list[_Chunk]) -> None:
        self._chunks = chunks
        self.closed = False

    def __aiter__(self) -> Any:
        return self._produce()

    async def _produce(self) -> Any:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def _text(content: str) -> _Chunk:
    return _Chunk([_Choice(_Delta(content=content))])


def _tool_start(index: int, call_id: str, name: str) -> _Chunk:
    return _Chunk(
        [
            _Choice(
                _Delta(
                    tool_calls=[
                        _ToolCallDelta(index, call_id, _FunctionDelta(name, ""))
                    ]
                )
            )
        ]
    )


def _tool_args(index: int, arguments: str) -> _Chunk:
    return _Chunk(
        [
            _Choice(
                _Delta(
                    tool_calls=[
                        _ToolCallDelta(
                            index, function=_FunctionDelta(arguments=arguments)
                        )
                    ]
                )
            )
        ]
    )


def _adapter() -> LiteLLMAdapter:
    return LiteLLMAdapter(model=MODEL, api_key="key", profile=FAST)


async def _drain(**kwargs: Any) -> list[StreamEvent]:
    return [
        event
        async for event in await _adapter().stream(
            [{"role": "user", "content": "hi"}], **kwargs
        )
    ]


@pytest.mark.anyio
async def test_no_tools_means_no_tools_kwarg_reaches_the_provider() -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_text("hi")])
        await _drain()

    assert "tools" not in call.call_args.kwargs


@pytest.mark.anyio
async def test_tools_are_translated_to_the_provider_function_schema() -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_text("hi")])
        await _drain(tools=[ECHO_TOOL])

    [schema] = call.call_args.kwargs["tools"]
    assert schema == {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echo something back.",
            "parameters": ECHO_TOOL.parameters,
        },
    }


@pytest.mark.anyio
async def test_a_tool_call_fragmented_across_chunks_is_assembled_whole() -> None:
    """`id` and `name` arrive once; `arguments` is sliced like a text delta."""
    stream = _FakeStream(
        [
            _tool_start(0, "call-1", "echo"),
            _tool_args(0, '{"text": '),
            _tool_args(0, '"hi"}'),
        ]
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        events = await _drain(tools=[ECHO_TOOL])

    assert events == [ToolCall(id="call-1", name="echo", arguments='{"text": "hi"}')]
    assert stream.closed is True


@pytest.mark.anyio
async def test_a_tool_call_is_not_yielded_until_the_stream_ends() -> None:
    """Unlike text, a tool call is unusable half-sent, so it is buffered whole.

    Both provider chunks below carry only a fragment of the call, and neither
    carries any text, so the first thing the returned generator can produce is
    the fully-assembled call -- there is no earlier point where a half-built
    one could leak out -- and the generator is finished right after it.
    """
    stream = _FakeStream(
        [_tool_start(0, "call-1", "echo"), _tool_args(0, '{"text": "hi"}')]
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        generator = await _adapter().stream(
            [{"role": "user", "content": "hi"}], tools=[ECHO_TOOL]
        )
        first = await generator.__anext__()
        assert first == ToolCall(id="call-1", name="echo", arguments='{"text": "hi"}')
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()


@pytest.mark.anyio
async def test_two_tool_calls_in_one_turn_are_kept_separate_by_index() -> None:
    stream = _FakeStream(
        [
            _tool_start(0, "call-1", "echo"),
            _tool_start(1, "call-2", "echo"),
            _tool_args(0, '{"text": "a"}'),
            _tool_args(1, '{"text": "b"}'),
        ]
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        events = await _drain(tools=[ECHO_TOOL])

    assert events == [
        ToolCall(id="call-1", name="echo", arguments='{"text": "a"}'),
        ToolCall(id="call-2", name="echo", arguments='{"text": "b"}'),
    ]


@pytest.mark.anyio
async def test_text_before_a_tool_call_is_still_streamed_as_text() -> None:
    """A model that narrates before calling a tool: both event kinds arrive."""
    stream = _FakeStream(
        [
            _text("Sure, "),
            _text("one moment. "),
            _tool_start(0, "call-1", "echo"),
            _tool_args(0, '{"text": "hi"}'),
        ]
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        events = await _drain(tools=[ECHO_TOOL])

    assert events == [
        "Sure, ",
        "one moment. ",
        ToolCall(id="call-1", name="echo", arguments='{"text": "hi"}'),
    ]


@pytest.mark.anyio
async def test_a_tool_call_with_no_name_is_dropped_rather_than_yielded_empty() -> None:
    """Nothing in the OpenAI shape produces this; the accumulator still guards it."""
    stream = _FakeStream([_Chunk([_Choice(_Delta(tool_calls=[_ToolCallDelta(0)]))])])
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        events = await _drain(tools=[ECHO_TOOL])

    assert events == []


@pytest.mark.anyio
async def test_an_empty_tools_sequence_is_treated_as_no_tools() -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_text("hi")])
        await _drain(tools=[])

    assert "tools" not in call.call_args.kwargs


def test_json_round_trips_through_a_real_tool_call_argument_string() -> None:
    """Sanity: the caller parses `arguments` the same way `json.dumps` writes it."""
    payload = {"text": "hi", "n": 3, "nested": {"ok": True}}
    call = ToolCall(id="1", name="echo", arguments=json.dumps(payload))
    assert json.loads(call.arguments) == payload
