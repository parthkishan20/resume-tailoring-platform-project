"""Token counts, surfaced at the boundary that already has them.

Every provider response carries a ``usage`` object, and the adapter used to
read ``response.choices`` past it and drop it on the floor. Nothing downstream
could then answer "what did that generation cost", because the only place the
number ever existed had already returned a bare ``str``.

Cost tracking itself is not this task's job, and the port signature is fixed —
``complete`` returns ``str``, and every caller depends on that. So the data
leaves through a side channel instead of the return value: the adapter calls a
:data:`UsageSink` once per completed call. The default sink logs one structured
line, which `core.logging`'s JSON formatter emits with the request id attached,
so the numbers are greppable per request today. Whoever adds a cost column
passes their own sink to ``LiteLLMAdapter(..., on_usage=...)`` and writes rows;
nothing else has to change.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What one provider call consumed."""

    #: The model as configured, not as the provider echoed it back: this is
    #: the string an operator set and the one a price table is keyed by.
    model: str
    #: ``"complete"`` or ``"stream"``. Prompt-token cost dominates the first
    #: and completion-token cost the second, so they are worth telling apart.
    operation: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


#: Called once per completed call, from the adapter. Synchronous and expected
#: to be cheap: it runs on the event loop, and for a stream it runs while the
#: response is being torn down.
UsageSink = Callable[[TokenUsage], None]


def _field(raw: Any, name: str) -> int:
    """Read one integer field from a provider usage object, or 0.

    ``usage`` is a Pydantic model on every provider LiteLLM supports today,
    but it is a plain dict when a response is replayed from a cache or a proxy,
    and a field is absent rather than zero on a provider that does not report
    it. All three are the same question.
    """
    value = raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)
    return int(value) if isinstance(value, int | float) else 0


def parse_usage(model: str, operation: str, raw: Any) -> TokenUsage | None:
    """Build a :class:`TokenUsage` from a provider ``usage`` object.

    Returns ``None`` when there is nothing to report — a provider that omits
    usage, or a stream whose final chunk never arrived. An absent count is not
    a zero count, and recording it as one would put a free call in the ledger.
    """
    if raw is None:
        return None
    total = _field(raw, "total_tokens")
    prompt = _field(raw, "prompt_tokens")
    completion = _field(raw, "completion_tokens")
    if not (total or prompt or completion):
        return None
    return TokenUsage(
        model=model,
        operation=operation,
        prompt_tokens=prompt,
        completion_tokens=completion,
        # Some providers report only the two halves.
        total_tokens=total or prompt + completion,
    )


def log_usage(usage: TokenUsage) -> None:
    """The default sink: one structured line per call."""
    logger.info(
        "llm %s used %d tokens",
        usage.operation,
        usage.total_tokens,
        extra={"llm_usage": asdict(usage)},
    )
