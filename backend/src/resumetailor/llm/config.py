"""What bounds one LLM call: time, attempts, and output tokens.

The values live in :class:`resumetailor.core.config.Settings` because the three
settings they join — ``OPENAI_API_KEY``, ``LLM_MODEL``, ``LLM_MOCK`` — are
already there, and a deployment that overrides one wants all of them in the
same place. This module is only the shape the adapter reads them through.

That indirection earns its keep in two ways. ``get_settings`` is
``lru_cache``d, so a test cannot change a field by setting an environment
variable after the first read; handing the adapter an :class:`LLMProfile`
sidesteps the cache entirely, the way ``RenderProfile`` is handed to
``RenderCVAdapter``. And the derived values — the hard-timeout backstop and the
backoff schedule — are computed once, here, rather than open-coded at each of
the two call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from resumetailor.core.config import get_settings

if TYPE_CHECKING:
    from resumetailor.core.config import Settings

#: How much longer the backstop waits than the per-attempt timeout it guards.
#:
#: LiteLLM's own ``timeout`` is the right mechanism — it reaches the provider
#: SDK and the underlying HTTP client, so a timed-out request is *cancelled*
#: rather than merely abandoned by its caller. But it is the provider's promise
#: to keep, and an unbounded call is exactly the defect being closed (D-46), so
#: an ``asyncio.wait_for`` sits outside it as a guarantee that does not depend
#: on any provider behaving. The margin is what keeps the backstop from firing
#: *instead* of the native timeout on a call that is merely at the line: the
#: native error says "the provider timed out", which is the more useful
#: message, and it wins as long as it arrives first. Proportional rather than a
#: fixed number of seconds so that one setting moves both limits together.
_HARD_TIMEOUT_FACTOR = 1.25


@dataclass(frozen=True, slots=True)
class LLMProfile:
    """The limits of one provider call. Every field is overridable from env."""

    #: Ceiling on a single attempt. A tailoring pass is a legitimate 30-60
    #: seconds of provider work, so this is not a latency target — it is the
    #: line past which a call is hung rather than slow.
    timeout_s: float = 60.0
    #: How many times a *transient* failure is tried in total, first try
    #: included. 1 disables retrying.
    max_attempts: int = 3
    #: The first backoff delay. Each further wait doubles it.
    backoff_base_s: float = 0.5
    #: Ceiling on generated tokens, which is the ceiling on cost per call.
    max_tokens: int = 8192
    #: How long a stream may go without delivering a token before it is
    #: treated as dead. Distinct from ``timeout_s``: a stream that is still
    #: producing text is working, however long it takes in total, and a stream
    #: that has gone quiet is not, however recently it started.
    stream_stall_timeout_s: float = 30.0

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> LLMProfile:
        """Read the profile out of process configuration."""
        resolved = settings if settings is not None else get_settings()
        return cls(
            timeout_s=resolved.LLM_TIMEOUT_S,
            max_attempts=resolved.LLM_MAX_ATTEMPTS,
            backoff_base_s=resolved.LLM_RETRY_BACKOFF_S,
            max_tokens=resolved.LLM_MAX_TOKENS,
            stream_stall_timeout_s=resolved.LLM_STREAM_STALL_TIMEOUT_S,
        )

    @property
    def hard_timeout_s(self) -> float:
        """The backstop timeout. See :data:`_HARD_TIMEOUT_FACTOR`."""
        return self.timeout_s * _HARD_TIMEOUT_FACTOR

    def backoff_delay(self, attempt: int) -> float:
        """How long to wait before attempt ``attempt + 1``. Exponential.

        No jitter. Jitter exists to desynchronise many clients retrying
        together, and this is a single-user application with one process; a
        deterministic schedule is worth more here because it is testable and
        because the worst-case added latency can be read off the settings.
        """
        return self.backoff_base_s * 2.0 ** (attempt - 1)

    def worst_case_seconds(self) -> float:
        """The longest a call can take before it fails, in seconds.

        Retries are only attempted on failures that arrive fast (a rate limit
        is a rejected request, not a slow one), so this is the bound an
        operator should read as "how long can a request be stuck for", not an
        estimate of anything normal. A timeout is deliberately not retried,
        which is what keeps this from being ``attempts x timeout``.
        """
        backoff = sum(self.backoff_delay(i) for i in range(1, self.max_attempts))
        return self.hard_timeout_s + backoff
