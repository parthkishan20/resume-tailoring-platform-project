"""The one LLM error `core.errors` does not already name.

It lives here rather than in `core/errors.py` for two reasons. The taxonomy in
`core/` is the set of errors the *application* raises, and this one is a
property of the provider boundary that only this package can detect. And
`core/errors.py` is being edited by task 2.4 for D-53 (splitting the
operator-facing detail from the client-facing message); adding a class to it
from a parallel worktree buys a conflict for no benefit.

Subclassing `LLMUnavailableError` is what makes that free. `install_error_handlers`
registers one handler per entry in `HTTP_MAPPED_ERRORS`, and Starlette resolves
a handler by walking the raised exception's MRO — so a subclass of an
already-mapped error is mapped too, and reaches the client through the same
envelope with its own `code`. Nothing has to be added to that tuple.
"""

from __future__ import annotations

from typing import ClassVar

from resumetailor.core.errors import LLMUnavailableError


class LLMEmptyResponseError(LLMUnavailableError):
    """The provider answered, and there was no text in the answer.

    `choices[0].message.content` is `None` on a refusal and on a pure
    tool-call response, and `""` when generation is cut off at zero tokens.
    All three used to be returned from a function annotated `-> str` and then
    handed to `json.loads`, which is PLAN.md D-59: two SSE paths turned into a
    generic error with no cause, and `import_pdf` became an unhandled 500.

    The inherited 503 is deliberate. A refusal is not really "service
    unavailable", but it is not the client's request that is malformed either,
    and the frontend already handles this status; the distinguishing signal is
    the `code`, which is the part a caller branches on.
    """

    code: ClassVar[str] = "LLM_EMPTY_RESPONSE"
