"""The real LLM provider, reached through LiteLLM.

One behaviour changed when this moved out of ``adapters.py``. The constructor
used to do ``os.environ["OPENAI_API_KEY"] = api_key`` — it wrote the user's
provider key into the process environment, from which every child process
inherited it, including the ``rendercv`` subprocess, which has no use for a
provider key and no business holding one (PLAN.md D-49). The key is passed
explicitly on each call now and never leaves this object.

Task 2.1 put a leash on the call itself. It was a bare, unbounded request
(D-46): no timeout, so a stalled provider held an SSE connection open for as
long as it cared to; no retry, so a rate limit — the most common transient
failure there is — reached the user as an immediate 503; no ``max_tokens``, so
the cost of a single call was whatever the model felt like generating. Five
bounds now hold, and all five are configurable through :class:`LLMProfile`:

* **A timeout per attempt.** LiteLLM's native ``timeout`` (it cancels the
  request at the HTTP client, which cancelling the awaiting task does not),
  with an ``asyncio.wait_for`` outside it as a backstop that does not depend on
  the provider honouring anything.
* **A stall timeout per streamed chunk.** A stream that is still producing
  text is working however long it runs; one that has gone quiet is not,
  however recently it started. Those are two different limits and a single
  call timeout cannot express both.
* **Retry with exponential backoff on transient failures only.** See
  :meth:`LiteLLMAdapter._attempt` for what counts as transient and why an
  auth failure and a timeout are both excluded.
* **``max_tokens``**, which is the ceiling on cost per call.
* **A guard on empty content** (D-59), which used to be a ``None`` returned
  from a function annotated ``-> str``.

Token usage leaves through :mod:`resumetailor.llm.usage` rather than the return
value, because the port's signature is fixed and every caller depends on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from functools import lru_cache
from typing import Any, NamedTuple, TypeVar

from resumetailor.core.errors import LLMAuthError, LLMUnavailableError
from resumetailor.llm.config import LLMProfile
from resumetailor.llm.errors import LLMEmptyResponseError
from resumetailor.llm.port import StreamEvent, ToolCall, ToolSpec
from resumetailor.llm.usage import UsageSink, log_usage, parse_usage

logger = logging.getLogger(__name__)

T = TypeVar("T")

_AUTH_MESSAGE = "Invalid LLM API key (check OPENAI_API_KEY / OPENROUTER_API_KEY)"

#: Called once per outbound provider call — right before it is sent, not
#: after it succeeds, because a rate limit that is about to be consumed is
#: consumed whether or not the call goes on to succeed. Async and awaited on
#: the event loop like everything else in this class, unlike `UsageSink`:
#: recording a request is a database write (`db.repositories.llm_requests`),
#: and this codebase's own convention (D-05) is that a blocking call never
#: runs on the loop directly, so a real sink wraps its write in
#: `asyncio.to_thread` rather than doing it inline the way the log-line
#: `UsageSink` default can.
RequestSink = Callable[[], Awaitable[None]]


async def _no_request_sink() -> None:
    """The default: nobody asked to know, so nothing is recorded."""


class _Taxonomy(NamedTuple):
    """LiteLLM's exception classes, sorted by what they mean for a retry."""

    #: Never retried: a rejected key is rejected on every attempt, so retrying
    #: only delays the failure the operator needs to see and spends attempts.
    auth: type[Exception]
    #: Not retried either, for a different reason: a timeout has already
    #: consumed the whole per-attempt budget, so a second attempt multiplies
    #: the user's wait for a provider that has just demonstrated it is stuck.
    #: This is what keeps the worst case at roughly one timeout rather than
    #: ``max_attempts`` of them.
    timeout: type[Exception]
    #: Retried. Each of these is a fast rejection or a dropped connection: the
    #: attempt costs little and the next one has a real chance.
    retryable: tuple[type[Exception], ...]


def _taxonomy() -> _Taxonomy:
    """Resolve the exception classes. Lazy: ``litellm`` is ~1s to import.

    ``Timeout`` and ``InternalServerError`` are named explicitly because
    neither is a subclass of anything else here. LiteLLM's ``Timeout`` derives
    from *openai*'s ``APIConnectionError``, not from LiteLLM's own class of
    that name, so catching ``litellm.exceptions.APIConnectionError`` does not
    catch it — which is how a timeout would otherwise have been silently
    retried by the branch that is documented not to retry it.
    """
    import litellm.exceptions as llm_exc

    return _Taxonomy(
        auth=llm_exc.AuthenticationError,
        timeout=llm_exc.Timeout,
        retryable=(
            llm_exc.RateLimitError,
            llm_exc.ServiceUnavailableError,
            llm_exc.APIConnectionError,
            llm_exc.InternalServerError,
        ),
    )


@lru_cache(maxsize=8)
def _stream_usage_options(model: str) -> dict[str, Any] | None:
    """``{"include_usage": True}`` when this model's provider accepts it.

    A streamed response carries no usage totals unless they are asked for, and
    the request that asks is an OpenAI extension that several providers reject
    outright. LiteLLM is asked which parameters the model supports rather than
    assumed to translate it, because the failure mode of guessing wrong is a
    400 on every chat message.
    """
    from litellm import get_supported_openai_params

    supported = get_supported_openai_params(model=model) or ()
    if "stream_options" not in supported:
        logger.debug("model %s reports no stream_options; usage unavailable", model)
        return None
    return {"include_usage": True}


def _delta(chunk: Any) -> str | None:
    """The text carried by one streaming chunk, if it carries any.

    Three chunk shapes are not text and none of them is an error: the
    usage-only final chunk that ``include_usage`` asks for has an empty
    ``choices`` list, the opening chunk carries a role and a ``None`` content,
    and a tool-call chunk carries arguments and a ``None`` content.
    """
    choices = getattr(chunk, "choices", None)
    if not choices:
        return None
    content = choices[0].delta.content
    return content if isinstance(content, str) and content else None


_ToolCallFragment = tuple[int, str | None, str | None, str | None]


def _tool_call_fragments(chunk: Any) -> list[_ToolCallFragment]:
    """The ``(index, id, name, arguments)`` fragment of a tool-call chunk, if any.

    A tool call is not sent whole: its ``id`` and its function ``name`` arrive
    once, on the first chunk that mentions that ``index``, and ``arguments``
    arrives as a JSON string sliced across every chunk after it — the same
    shape ``delta.content`` uses for plain text, applied to the arguments
    string instead. The caller accumulates by ``index`` because a model asking
    for more than one tool in the same turn interleaves their fragments.
    """
    choices = getattr(chunk, "choices", None)
    if not choices:
        return []
    tool_calls = getattr(choices[0].delta, "tool_calls", None)
    if not tool_calls:
        return []
    fragments: list[_ToolCallFragment] = []
    for call in tool_calls:
        function = getattr(call, "function", None)
        fragments.append(
            (
                getattr(call, "index", 0),
                getattr(call, "id", None),
                getattr(function, "name", None) if function is not None else None,
                getattr(function, "arguments", None) if function is not None else None,
            )
        )
    return fragments


def _accumulate_tool_calls(chunk: Any, pending: dict[int, dict[str, str]]) -> None:
    """Fold one chunk's tool-call fragments into the in-progress calls, by index."""
    for index, call_id, name, arguments in _tool_call_fragments(chunk):
        slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if call_id:
            slot["id"] = call_id
        if name:
            slot["name"] += name
        if arguments:
            slot["arguments"] += arguments


def _finished_tool_calls(pending: dict[int, dict[str, str]]) -> list[ToolCall]:
    """The accumulated calls, in the order the provider indexed them.

    A slot with no ``name`` was never a real tool call -- nothing in the
    OpenAI streaming shape produces one, but an empty ``pending`` entry is
    cheap to guard against and costs nothing to be defensive about.
    """
    return [
        ToolCall(id=slot["id"], name=slot["name"], arguments=slot["arguments"])
        for index in sorted(pending)
        if (slot := pending[index])["name"]
    ]


def _tool_schema(tool: ToolSpec) -> dict[str, Any]:
    """One tool, in the shape every OpenAI-compatible provider expects."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


async def _release(response: Any) -> None:
    """Close the provider connection behind a stream.

    This is the half of the streaming lifecycle that was missing. LiteLLM's
    ``CustomStreamWrapper`` holds the HTTP response open, and the previous
    implementation only ever stopped reading from it — on the normal end of a
    stream the connection was released by garbage collection eventually, and
    on a client disconnecting mid-response it was released whenever the object
    happened to be collected, which is not a bound on anything.

    Called from a ``finally``, so it runs on all three exits: the last chunk,
    an error, and the ``GeneratorExit`` that arrives when the caller closes
    the generator — which is what a browser closing an SSE connection
    produces, by way of Starlette cancelling the response task. Awaiting
    inside that ``finally`` is legal precisely because this is an *async*
    generator: ``aclose()`` drives it to completion.

    A failure to close is suppressed. It cannot be acted on, and letting it
    propagate out of a ``finally`` would replace whatever error the caller was
    already being told about with a less useful one.
    """
    aclose = getattr(response, "aclose", None)
    if aclose is None:
        return
    with contextlib.suppress(Exception):
        await aclose()


class LiteLLMAdapter:
    """Calls a provider through LiteLLM and maps its errors to domain errors."""

    def __init__(
        self,
        model: str,
        api_key: str,
        profile: LLMProfile | None = None,
        on_usage: UsageSink | None = None,
        on_request: RequestSink | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._profile = profile if profile is not None else LLMProfile.from_settings()
        self._on_usage: UsageSink = on_usage if on_usage is not None else log_usage
        self._on_request: RequestSink = on_request if on_request is not None else _no_request_sink

    # ── Provider call ──────────────────────────────────────────────────────

    def _kwargs(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "api_key": self._api_key,
            # LiteLLM's own timeout, which reaches the provider SDK's HTTP
            # client. `max_tokens` rather than `max_completion_tokens`:
            # LiteLLM translates it per provider, so this one name is correct
            # for both the chat-completions models and the newer ones that
            # renamed the parameter.
            "timeout": self._profile.timeout_s,
            "max_tokens": self._profile.max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        return kwargs

    async def _attempt(self, what: str, call: Callable[[], Awaitable[T]]) -> T:
        """Run ``call`` under the timeout, retrying transient failures.

        Retry is on the *connection and setup* phase of a call, which for
        ``stream`` means the request that opens the stream and nothing after
        it. Once a token has reached the client there is no transparent retry
        available: resuming would need the whole response buffered, which is
        the one thing streaming exists not to do, and restarting would mean
        re-emitting text the user has already read. Whether to start over is
        the caller's decision — it owns the SSE response — so a mid-stream
        failure is mapped to a domain error and raised, not papered over.
        """
        taxonomy = _taxonomy()
        attempts = self._profile.max_attempts
        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(
                    call(), timeout=self._profile.hard_timeout_s
                )
            except taxonomy.auth as exc:
                raise LLMAuthError(_AUTH_MESSAGE) from exc
            except taxonomy.timeout as exc:
                msg = f"the provider did not answer within {self._profile.timeout_s:g}s"
                raise LLMUnavailableError(msg) from exc
            except TimeoutError as exc:
                # The backstop fired, meaning LiteLLM's own timeout did not.
                msg = (
                    f"{what} exceeded its {self._profile.hard_timeout_s:g}s ceiling "
                    "and was abandoned"
                )
                raise LLMUnavailableError(msg) from exc
            except taxonomy.retryable as exc:
                if attempt == attempts:
                    msg = f"{what} failed after {attempts} attempts: {exc}"
                    raise LLMUnavailableError(msg) from exc
                delay = self._profile.backoff_delay(attempt)
                logger.warning(
                    "%s attempt %d/%d failed (%s); retrying in %.2fs",
                    what,
                    attempt,
                    attempts,
                    type(exc).__name__,
                    delay,
                    extra={"llm_retry_attempt": attempt, "llm_model": self._model},
                )
                await asyncio.sleep(delay)
            else:
                return result
        # Unreachable: every path above returns or raises. Present so that the
        # function has no implicit `None` return for mypy to reject.
        msg = f"{what} exhausted its retries without an error to report"
        raise LLMUnavailableError(msg)

    def _report_usage(self, operation: str, raw: Any) -> None:
        """Hand the call's token counts to the sink, if there are any.

        Guarded because the sink is an injection point for code that does not
        exist yet, and because for a stream this runs inside the teardown
        ``finally`` — a cost-tracking bug must not be able to break, or
        relabel, a generation the user was in the middle of.
        """
        usage = parse_usage(self._model, operation, raw)
        if usage is None:
            return
        try:
            self._on_usage(usage)
        except Exception:
            logger.exception("usage sink raised; this call is missing from the ledger")

    async def _record_request(self) -> None:
        """Tell the sink a provider call is about to go out.

        Guarded the same way as :meth:`_report_usage`: a rate-limit counter
        that is missing a row is a stale number in the UI, not a reason to
        fail the call the user actually asked for.
        """
        try:
            await self._on_request()
        except Exception:
            logger.exception("request sink raised; this call is missing from the counter")

    # ── The port ───────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """One non-streamed completion, as text.

        Raises:
            LLMAuthError: the key was rejected.
            LLMEmptyResponseError: the provider answered with no text.
            LLMUnavailableError: the provider timed out, or was still failing
                transiently after the configured number of attempts.
        """
        import litellm  # lazy: litellm is about a second to import

        kwargs = self._kwargs(messages, response_format)
        await self._record_request()
        response = await self._attempt(
            "completion", lambda: litellm.acompletion(**kwargs)
        )
        self._report_usage("complete", getattr(response, "usage", None))

        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            reason = getattr(response.choices[0], "finish_reason", None)
            msg = (
                "the provider returned no text"
                f"{f' (finish_reason={reason})' if reason else ''}"
            )
            raise LLMEmptyResponseError(msg)
        return content

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Sequence[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """The same completion, delivered as it is generated.

        ``tools`` puts the model in a position to ask for one or more of them
        instead of answering in text (task 3.3, closing D-33: task 2.1 built
        the streaming lifecycle below and deliberately did not wire this
        parameter). A tool call is not usable until the provider has finished
        sending it — resuming a partially-parsed JSON argument string is not a
        thing a caller can act on — so unlike a text delta, which is yielded
        the moment it arrives, a :class:`ToolCall` is assembled across the
        whole stream and yielded only once, after the last chunk, in whatever
        order the provider's own tool-call indices give it.

        Raises (from the returned iterator, not from this coroutine — the
        request is not sent until the first chunk is asked for, so that a
        generator nobody iterates does not open a connection nobody closes):
            LLMAuthError, LLMUnavailableError: as :meth:`complete`, plus
                ``LLMUnavailableError`` when an established stream goes quiet
                for longer than ``stream_stall_timeout_s``.
        """
        import litellm  # lazy: litellm is about a second to import

        kwargs = self._kwargs(messages)
        kwargs["stream"] = True
        if tools:
            kwargs["tools"] = [_tool_schema(tool) for tool in tools]
        options = _stream_usage_options(self._model)
        if options is not None:
            kwargs["stream_options"] = options

        async def _gen() -> AsyncIterator[StreamEvent]:
            await self._record_request()
            response = await self._attempt(
                "stream setup", lambda: litellm.acompletion(**kwargs)
            )
            raw_usage: Any = None
            # Keyed by the provider's own tool-call index, not call id: the id
            # arrives on the same chunk as the index, but nothing guarantees
            # it arrives before a later fragment for that index needs a slot
            # to land in.
            pending: dict[int, dict[str, str]] = {}
            try:
                async for chunk in self._chunks(response):
                    raw_usage = getattr(chunk, "usage", None) or raw_usage
                    delta = _delta(chunk)
                    if delta:
                        yield delta
                    _accumulate_tool_calls(chunk, pending)
                for call in _finished_tool_calls(pending):
                    yield call
            finally:
                self._report_usage("stream", raw_usage)
                await _release(response)

        return _gen()

    async def _chunks(self, response: Any) -> AsyncIterator[Any]:
        """Yield raw chunks, bounding each read and mapping provider errors.

        The previous loop was ``async for chunk in response`` with no timeout
        and no ``except``: a provider that opened a stream and then stopped
        writing held the connection until something else gave up, and a rate
        limit that arrived mid-stream reached the route as a raw LiteLLM
        exception, which its ``except Exception`` turned into a generic
        ``CHAT_FAILED`` with the cause discarded.
        """
        taxonomy = _taxonomy()
        stall = self._profile.stream_stall_timeout_s
        iterator = response.__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(iterator.__anext__(), timeout=stall)
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                msg = f"the provider sent no token for {stall:g}s; stream abandoned"
                raise LLMUnavailableError(msg) from exc
            except taxonomy.auth as exc:
                raise LLMAuthError(_AUTH_MESSAGE) from exc
            except (taxonomy.timeout, *taxonomy.retryable) as exc:
                msg = f"the stream failed after it had started: {exc}"
                raise LLMUnavailableError(msg) from exc
            yield chunk
