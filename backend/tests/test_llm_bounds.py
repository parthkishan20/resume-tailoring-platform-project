"""What bounds an LLM call: timeout, retry, `max_tokens`, empty content, usage.

This is task 2.1's half of the adapter suite. `test_llm.py` covers the port
protocols, the error *mapping*, and the D-49 key handling; everything here is
about the limits that mapping had nothing behind it (PLAN.md D-46, D-59).

Every test drives a `LiteLLMAdapter` built with an explicit `LLMProfile`
rather than one read from the environment. That is deliberate: `get_settings`
is `lru_cache`d, so a `monkeypatch.setenv` after the first read changes
nothing, and the new `LLM_*` fields are not pinned in `conftest.TEST_ENV` (see
the 2.1 report) — a developer with them set in `backend/.env` would otherwise
run a different suite from CI.

`asyncio.sleep` is not patched. The backoff base is set to a millisecond
instead, so a retry test costs microseconds and still exercises the real
sleep; the *schedule* is asserted directly against `LLMProfile.backoff_delay`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from resumetailor.core.errors import (
    BackendError,
    LLMAuthError,
    LLMUnavailableError,
)
from resumetailor.llm.config import LLMProfile
from resumetailor.llm.errors import LLMEmptyResponseError
from resumetailor.llm.litellm_adapter import LiteLLMAdapter, _stream_usage_options
from resumetailor.llm.usage import TokenUsage, parse_usage

MODEL = "openrouter/test/model"

#: Fast enough that a retry test is not a slow test, wide enough that the
#: timeout assertions are about the code and not about machine load.
FAST = LLMProfile(
    timeout_s=5.0,
    max_attempts=3,
    backoff_base_s=0.001,
    max_tokens=123,
    stream_stall_timeout_s=5.0,
)


# ── Provider response doubles ──────────────────────────────────────────────
#
# Hand-written rather than `MagicMock`: a MagicMock attribute is truthy and
# `isinstance`-opaque, so a test that asserts "content is absent" or "choices
# is empty" against one asserts nothing at all.


@dataclass
class _Content:
    content: str | None


@dataclass
class _Choice:
    message: _Content | None = None
    delta: _Content | None = None
    finish_reason: str | None = None


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _Response:
    choices: list[_Choice]
    usage: _Usage | None = None


def _answer(text: str | None, **kwargs: Any) -> _Response:
    return _Response(
        choices=[_Choice(message=_Content(text), **kwargs)],
        usage=_Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )


def _token(text: str | None) -> _Choice:
    return _Choice(delta=_Content(text))


@dataclass
class _Chunk:
    choices: list[_Choice]
    usage: _Usage | None = None


class _FakeStream:
    """A LiteLLM `CustomStreamWrapper` stand-in, with a visible `aclose`."""

    def __init__(
        self,
        chunks: list[_Chunk],
        error: Exception | None = None,
        stall_s: float | None = None,
    ) -> None:
        self._chunks = chunks
        self._error = error
        self._stall_s = stall_s
        self.closed = False

    def __aiter__(self) -> Any:
        return self._produce()

    async def _produce(self) -> Any:
        for chunk in self._chunks:
            yield chunk
        if self._stall_s is not None:
            await asyncio.sleep(self._stall_s)
        if self._error is not None:
            raise self._error

    async def aclose(self) -> None:
        self.closed = True


def _rate_limit() -> Exception:
    import litellm.exceptions as llm_exc

    return llm_exc.RateLimitError("slow down", llm_provider="openrouter", model="test")


def _auth_failure() -> Exception:
    import litellm.exceptions as llm_exc

    return llm_exc.AuthenticationError(
        "bad key", llm_provider="openrouter", model="test"
    )


def _provider_timeout() -> Exception:
    import litellm.exceptions as llm_exc

    return llm_exc.Timeout("too slow", model="test", llm_provider="openrouter")


def _adapter(**kwargs: Any) -> LiteLLMAdapter:
    return LiteLLMAdapter(model=MODEL, api_key="key", profile=FAST, **kwargs)


async def _drain(adapter: LiteLLMAdapter) -> list[str]:
    return [
        delta
        async for delta in await adapter.stream([{"role": "user", "content": "x"}])
    ]


# ── 1. Timeout ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_complete_passes_litellms_own_timeout() -> None:
    """D-46: the call carries a timeout the provider SDK will honour."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _answer("ok")
        await _adapter().complete([{"role": "user", "content": "hi"}])

    assert call.call_args.kwargs["timeout"] == FAST.timeout_s


@pytest.mark.anyio
async def test_stream_passes_litellms_own_timeout() -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_Chunk([_token("hi")])])
        await _drain(_adapter())

    assert call.call_args.kwargs["timeout"] == FAST.timeout_s
    assert call.call_args.kwargs["stream"] is True


@pytest.mark.anyio
async def test_a_provider_that_never_answers_is_abandoned_by_the_backstop() -> None:
    """The bound does not depend on LiteLLM honouring its own timeout.

    `acompletion` here ignores the `timeout` it was handed and simply never
    returns, which is the failure the native timeout cannot cover by
    definition. `asyncio.wait_for` outside it is what makes the ceiling real.
    """

    async def never_answers(**_kwargs: Any) -> Any:
        await asyncio.sleep(30)

    profile = LLMProfile(timeout_s=0.02, max_attempts=3, backoff_base_s=0.001)
    adapter = LiteLLMAdapter(model=MODEL, api_key="key", profile=profile)

    with patch("litellm.acompletion", never_answers):
        with pytest.raises(LLMUnavailableError, match="ceiling"):
            await adapter.complete([{"role": "user", "content": "hi"}])


@pytest.mark.anyio
async def test_a_stream_that_goes_quiet_is_abandoned() -> None:
    """A started stream that stops sending tokens must not hold the connection.

    This is the half of D-46 a single call timeout cannot express: the request
    succeeded, the first token arrived, and then nothing.
    """
    profile = LLMProfile(timeout_s=5.0, stream_stall_timeout_s=0.02)
    adapter = LiteLLMAdapter(model=MODEL, api_key="key", profile=profile)
    stream = _FakeStream([_Chunk([_token("half a sen")])], stall_s=30)

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        with pytest.raises(LLMUnavailableError, match="no token"):
            await _drain(adapter)

    assert stream.closed is True


@pytest.mark.anyio
async def test_provider_timeout_maps_to_unavailable_and_is_not_retried() -> None:
    """A timeout has already spent the budget; a second attempt only doubles it."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.side_effect = _provider_timeout()
        with pytest.raises(LLMUnavailableError, match="did not answer within"):
            await _adapter().complete([{"role": "user", "content": "hi"}])

    assert call.await_count == 1


# ── 2. Retry with backoff ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_transient_rate_limit_is_retried_and_succeeds() -> None:
    """D-46: a rate limit was an immediate client-visible 503."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.side_effect = [_rate_limit(), _rate_limit(), _answer("third time")]
        result = await _adapter().complete([{"role": "user", "content": "hi"}])

    assert result == "third time"
    assert call.await_count == 3


@pytest.mark.anyio
async def test_retries_are_bounded_and_the_last_failure_is_reported() -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.side_effect = _rate_limit()
        with pytest.raises(LLMUnavailableError, match="after 3 attempts"):
            await _adapter().complete([{"role": "user", "content": "hi"}])

    assert call.await_count == FAST.max_attempts


@pytest.mark.anyio
async def test_an_auth_failure_is_never_retried() -> None:
    """A rejected key is rejected on every attempt. Retrying hides the cause."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.side_effect = _auth_failure()
        with pytest.raises(LLMAuthError):
            await _adapter().complete([{"role": "user", "content": "hi"}])

    assert call.await_count == 1


@pytest.mark.anyio
async def test_max_attempts_of_one_disables_retrying() -> None:
    profile = LLMProfile(max_attempts=1, backoff_base_s=0.001)
    adapter = LiteLLMAdapter(model=MODEL, api_key="key", profile=profile)

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.side_effect = _rate_limit()
        with pytest.raises(LLMUnavailableError):
            await adapter.complete([{"role": "user", "content": "hi"}])

    assert call.await_count == 1


@pytest.mark.anyio
async def test_stream_setup_is_retried_but_an_established_stream_is_not() -> None:
    """Retry belongs on the connection phase and nowhere past it.

    Setup: two rate limits, then a stream — retried, and the caller never
    learns there was a problem. Mid-flight: a rate limit after two tokens have
    already reached the caller — surfaced, because the alternative is either
    buffering the whole response (which defeats streaming) or re-emitting text
    the user has read, and choosing between those is the route's call.
    """
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.side_effect = [
            _rate_limit(),
            _rate_limit(),
            _FakeStream([_Chunk([_token("hi ")]), _Chunk([_token("there")])]),
        ]
        assert await _drain(_adapter()) == ["hi ", "there"]
    assert call.await_count == 3

    mid_flight = _FakeStream(
        [_Chunk([_token("hi ")]), _Chunk([_token("the")])], error=_rate_limit()
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = mid_flight
        with pytest.raises(LLMUnavailableError, match="after it had started"):
            await _drain(_adapter())

    assert call.await_count == 1
    assert mid_flight.closed is True


def test_backoff_doubles_and_the_worst_case_is_one_timeout_not_three() -> None:
    profile = LLMProfile(timeout_s=60.0, max_attempts=4, backoff_base_s=0.5)

    assert [profile.backoff_delay(n) for n in (1, 2, 3)] == [0.5, 1.0, 2.0]
    # 60 * 1.25 for the one attempt that may time out, plus the three waits.
    assert profile.worst_case_seconds() == pytest.approx(75.0 + 3.5)


# ── 3. max_tokens ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_both_paths_bound_the_generated_tokens() -> None:
    """D-46: without this, cost per call is whatever the model felt like."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _answer("ok")
        await _adapter().complete([{"role": "user", "content": "hi"}])
    assert call.call_args.kwargs["max_tokens"] == 123

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_Chunk([_token("ok")])])
        await _drain(_adapter())
    assert call.call_args.kwargs["max_tokens"] == 123


def test_the_shipped_defaults_are_sane() -> None:
    """A default that kills real usage is worse than no limit at all."""
    default = LLMProfile()

    assert default.timeout_s >= 30.0
    assert default.max_attempts >= 2
    assert default.max_tokens >= 4096
    assert default.stream_stall_timeout_s < default.timeout_s


# ── 4. Empty content (D-59) ─────────────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("content", [None, "", "   "])
async def test_a_response_with_no_text_raises_rather_than_returning_none(
    content: str | None,
) -> None:
    """D-59: `None` used to be returned from a function annotated `-> str`.

    It then reached `json.loads` in three routes: two turned into a generic
    SSE error and `import_pdf` into an unhandled 500.
    """
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _answer(content, finish_reason="content_filter")
        with pytest.raises(LLMEmptyResponseError, match="content_filter"):
            await _adapter().complete([{"role": "user", "content": "hi"}])


def test_the_empty_response_error_reaches_the_client_as_a_mapped_error() -> None:
    """It is mapped without being added to `HTTP_MAPPED_ERRORS`.

    Starlette resolves a handler along the raised exception's MRO, so
    subclassing an already-registered error is what keeps `core/errors.py` —
    which task 2.4 is editing — out of this task's diff.
    """
    from resumetailor.core.errors import HTTP_MAPPED_ERRORS, error_response

    assert issubclass(LLMEmptyResponseError, LLMUnavailableError)
    assert issubclass(LLMEmptyResponseError, BackendError)
    assert any(
        issubclass(LLMEmptyResponseError, mapped) for mapped in HTTP_MAPPED_ERRORS
    )

    response = error_response(LLMEmptyResponseError("nothing came back"))
    assert response.status_code == 503
    assert b"LLM_EMPTY_RESPONSE" in response.body


@pytest.mark.anyio
async def test_a_stream_of_empty_deltas_is_not_an_error() -> None:
    """An opening chunk carries a role and no content. That is normal."""
    stream = _FakeStream(
        [
            _Chunk([_Choice(delta=_Content(None))]),
            _Chunk([_token("real text")]),
            _Chunk([]),
        ]
    )
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        assert await _drain(_adapter()) == ["real text"]


# ── 5. Token accounting ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_usage_reaches_the_sink_on_a_completion() -> None:
    seen: list[TokenUsage] = []
    adapter = _adapter(on_usage=seen.append)

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _answer("ok")
        await adapter.complete([{"role": "user", "content": "hi"}])

    assert seen == [
        TokenUsage(
            model=MODEL,
            operation="complete",
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        )
    ]


@pytest.mark.anyio
async def test_usage_reaches_the_sink_from_a_streams_final_chunk() -> None:
    """The counts arrive after the text, in a chunk with no choices at all."""
    seen: list[TokenUsage] = []
    adapter = _adapter(on_usage=seen.append)
    stream = _FakeStream(
        [
            _Chunk([_token("hello")]),
            _Chunk([], usage=_Usage(prompt_tokens=3, completion_tokens=1)),
        ]
    )

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        assert await _drain(adapter) == ["hello"]

    assert [(u.operation, u.total_tokens) for u in seen] == [("stream", 4)]


@pytest.mark.anyio
async def test_a_provider_that_reports_no_usage_is_not_recorded_as_free() -> None:
    seen: list[TokenUsage] = []
    adapter = _adapter(on_usage=seen.append)

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _Response(choices=[_Choice(message=_Content("ok"))])
        await adapter.complete([{"role": "user", "content": "hi"}])

    assert seen == []


@pytest.mark.anyio
async def test_a_broken_usage_sink_does_not_break_the_generation() -> None:
    """The sink is an injection point for code that does not exist yet."""

    def explode(_usage: TokenUsage) -> None:
        error = RuntimeError("the cost table is on fire")
        raise error

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _answer("still fine")
        result = await _adapter(on_usage=explode).complete(
            [{"role": "user", "content": "hi"}]
        )

    assert result == "still fine"


def test_usage_is_read_from_a_dict_as_well_as_an_object() -> None:
    """A response replayed from a cache or a proxy carries a plain dict."""
    from_object = parse_usage(MODEL, "complete", _Usage(2, 3, 5))
    from_dict = parse_usage(
        MODEL,
        "complete",
        {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    )

    assert from_object == from_dict
    assert parse_usage(MODEL, "complete", None) is None
    assert parse_usage(MODEL, "complete", _Usage()) is None


@pytest.mark.anyio
async def test_stream_usage_is_requested_only_where_the_provider_takes_it() -> None:
    """`stream_options` is an OpenAI extension several providers reject."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_Chunk([_token("ok")])])

        _stream_usage_options.cache_clear()
        with patch("litellm.get_supported_openai_params", return_value=["max_tokens"]):
            await _drain(_adapter())
        assert "stream_options" not in call.call_args.kwargs

        _stream_usage_options.cache_clear()
        with patch(
            "litellm.get_supported_openai_params",
            return_value=["max_tokens", "stream_options"],
        ):
            call.return_value = _FakeStream([_Chunk([_token("ok")])])
            await _drain(_adapter())
        assert call.call_args.kwargs["stream_options"] == {"include_usage": True}

    _stream_usage_options.cache_clear()


# ── 6. Streaming lifecycle ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_the_provider_stream_is_closed_when_it_ends_normally() -> None:
    stream = _FakeStream([_Chunk([_token("a")]), _Chunk([_token("b")])])

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        assert await _drain(_adapter()) == ["a", "b"]

    assert stream.closed is True


@pytest.mark.anyio
async def test_the_provider_stream_is_closed_when_the_client_disconnects() -> None:
    """The leak this closes: a browser closing an SSE connection mid-response.

    Starlette cancels the response task, which closes the async generator,
    which delivers `GeneratorExit` at the `yield`. Before task 2.1 the
    generator simply stopped being read and the underlying HTTP response was
    released whenever it happened to be collected. `gen.aclose()` below is
    exactly what that teardown does.
    """
    stream = _FakeStream([_Chunk([_token(str(n))]) for n in range(100)])

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        generator = await _adapter().stream([{"role": "user", "content": "x"}])
        assert await generator.__anext__() == "0"
        assert stream.closed is False
        await generator.aclose()

    assert stream.closed is True


@pytest.mark.anyio
async def test_nothing_is_sent_until_the_stream_is_iterated() -> None:
    """A generator nobody reads must not open a connection nobody closes."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _FakeStream([_Chunk([_token("a")])])
        await _adapter().stream([{"role": "user", "content": "x"}])

    assert call.await_count == 0


@pytest.mark.anyio
async def test_the_provider_stream_is_closed_when_setup_succeeds_but_auth_fails() -> (
    None
):
    """An auth failure arriving mid-stream is still a stream to clean up."""
    stream = _FakeStream([_Chunk([_token("a")])], error=_auth_failure())

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = stream
        with pytest.raises(LLMAuthError):
            await _drain(_adapter())

    assert stream.closed is True


@pytest.mark.anyio
async def test_a_structured_response_format_still_reaches_the_provider() -> None:
    """The three JSON-mode callers depend on this arriving alongside the bounds."""
    schema = {"type": "json_object"}

    with patch("litellm.acompletion", new_callable=AsyncMock) as call:
        call.return_value = _answer('{"ok": true}')
        result = await _adapter().complete(
            [{"role": "user", "content": "hi"}], response_format=schema
        )

    assert result == '{"ok": true}'
    assert call.call_args.kwargs["response_format"] == schema
    assert call.call_args.kwargs["max_tokens"] == 123


def test_the_profile_is_read_from_process_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production wiring passes no profile, so `from_settings` is the path.

    `create_real_backend` builds `LiteLLMAdapter(model=..., api_key=...)` and
    nothing else; if these five fields did not reach the adapter from
    `Settings`, every bound above would silently be a default. The `Settings`
    object is constructed directly rather than through the `lru_cache`d
    `get_settings`, which this suite pins per test.
    """
    from resumetailor.core.config import Settings

    for name, value in {
        "LLM_TIMEOUT_S": "12.5",
        "LLM_MAX_ATTEMPTS": "5",
        "LLM_RETRY_BACKOFF_S": "0.25",
        "LLM_MAX_TOKENS": "256",
        "LLM_STREAM_STALL_TIMEOUT_S": "7",
    }.items():
        monkeypatch.setenv(name, value)

    profile = LLMProfile.from_settings(Settings())
    adapter = LiteLLMAdapter(model=MODEL, api_key="key")

    assert profile == LLMProfile(
        timeout_s=12.5,
        max_attempts=5,
        backoff_base_s=0.25,
        max_tokens=256,
        stream_stall_timeout_s=7.0,
    )
    # No profile argument: the adapter reaches for settings itself.
    assert adapter._profile == LLMProfile.from_settings()


def test_a_nonsense_limit_fails_the_boot_rather_than_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every new field is bounded in `Settings`, where a bad value is loud."""
    from pydantic import ValidationError

    from resumetailor.core.config import Settings

    monkeypatch.setenv("LLM_TIMEOUT_S", "0")
    with pytest.raises(ValidationError):
        Settings()
