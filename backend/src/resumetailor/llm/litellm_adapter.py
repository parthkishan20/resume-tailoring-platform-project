"""The real LLM provider, reached through LiteLLM.

One behaviour changed when this moved out of ``adapters.py``. The constructor
used to do ``os.environ["OPENAI_API_KEY"] = api_key`` — it wrote the user's
provider key into the process environment, from which every child process
inherited it, including the ``rendercv`` subprocess, which has no use for a
provider key and no business holding one (PLAN.md D-49). The key is passed
explicitly on each call now and never leaves this object.

Timeouts, retry with backoff and token accounting are task 2.1's; this module
is where they land.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from resumetailor.core.errors import LLMAuthError, LLMUnavailableError


def _llm_exceptions() -> tuple[type[Exception], tuple[type[Exception], ...]]:
    """Return ``(auth_error, unavailable_errors)``. Lazy: litellm is slow to import."""
    import litellm.exceptions as llm_exc

    return llm_exc.AuthenticationError, (
        llm_exc.RateLimitError,
        llm_exc.ServiceUnavailableError,
        llm_exc.APIConnectionError,
    )


_AUTH_MESSAGE = "Invalid LLM API key (check OPENAI_API_KEY)"


class LiteLLMAdapter:
    """Calls a provider through LiteLLM and maps its errors to domain errors."""

    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key

    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        import litellm  # lazy: litellm is about a second to import

        auth_error, unavailable = _llm_exceptions()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "api_key": self._api_key,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = await litellm.acompletion(**kwargs)
        except auth_error as exc:
            raise LLMAuthError(_AUTH_MESSAGE) from exc
        except unavailable as exc:
            raise LLMUnavailableError(str(exc)) from exc
        content: str = response.choices[0].message.content
        return content

    async def stream(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        import litellm  # lazy: litellm is about a second to import

        auth_error, unavailable = _llm_exceptions()
        model = self._model
        api_key = self._api_key

        async def _gen() -> AsyncIterator[str]:
            try:
                response = await litellm.acompletion(
                    model=model, messages=messages, api_key=api_key, stream=True
                )
            except auth_error as exc:
                raise LLMAuthError(_AUTH_MESSAGE) from exc
            except unavailable as exc:
                raise LLMUnavailableError(str(exc)) from exc
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        return _gen()
