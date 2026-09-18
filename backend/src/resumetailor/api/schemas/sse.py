"""The server-sent-event frames, as models.

``response_model`` cannot describe a streaming route: the response body is a
sequence of frames, not one document, so FastAPI has nothing to validate and
the OpenAPI document said ``application/json`` and ``{}`` for all three
streams. These models are the missing half. They describe the JSON that
follows ``data:`` on each frame, they are what
:mod:`resumetailor.api.openapi` turns into ``components.schemas`` entries, and
they are therefore what the generated TypeScript gives the frontend to
validate a frame against.

**A frame's event name is not in its payload.** SSE puts it on the preceding
``event:`` line, so no field here can discriminate the union and a client has
to pick the schema by the event name it just read. :data:`STREAM_CONTRACTS` is
that mapping, per route, in one place; ``frontend/src/lib/api/sse.ts`` is its
counterpart and ``tests/test_api_contract.py`` pins the two together.

**What these models do not do.** They are documentation, not enforcement. The
routes build their frames with ``json.dumps`` on a hand-built dict and are
deliberately left that way: making a route serialise through these models
would be a behaviour change to code task 2.5 has just rewritten, and the frame
shapes are pinned by that task's tests. The contract test asserts the two
agree instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, Field

from resumetailor.db.models import GeneratedResume
from resumetailor.domain.evaluation import EvaluationResult

__all__ = [
    "STREAM_CONTRACTS",
    "ChatDoneFrame",
    "ChatResult",
    "EvaluateDoneFrame",
    "GenerateDoneFrame",
    "SseErrorFrame",
    "SseProgressFrame",
    "SseTokenFrame",
    "StreamContract",
]


class SseProgressFrame(BaseModel):
    """``event: progress`` -- the step the server is about to take.

    The message strings are the wire contract and live in the routes (see
    ``_PROGRESS_MESSAGES`` in ``api/routers/resumes.py``), not here.
    """

    message: str


class SseTokenFrame(BaseModel):
    """``event: token`` -- one chunk of assistant text, to append verbatim."""

    delta: str


class SseErrorFrame(BaseModel):
    """``event: error`` -- the same body an HTTP error would have carried.

    Identical in shape to
    :class:`~resumetailor.api.schemas.errors.ErrorEnvelope`, and deliberately
    so: a streaming failure and a non-streaming one should be one thing for
    the client to handle. ``error`` is the raising class's ``client_message``
    and ``code`` is ``exc.code`` -- as of task 2.2 on all three routes, where
    two of them previously emitted a literal that could disagree with the
    exception actually raised.

    This is the frame D-55 is about: it arrives inside a 200 response,
    because the status line was sent before the generator produced anything.
    """

    error: str = Field(description="One sentence, safe to show a user.")
    code: str = Field(description="Machine-readable. One of ERROR_CODES.")


class ChatAction(BaseModel):
    """A follow-up the assistant asks the UI to perform.

    Declared because the field exists on the wire and the frontend's type
    vocabulary already names it. Nothing emits a non-null ``action`` today;
    the assistant tab that will is task 3.2's.
    """

    type: str
    resume_id: int | None = None


class ChatResult(BaseModel):
    """The assembled assistant turn, sent once the stream is complete.

    ``text`` is every ``delta`` concatenated, so a client that accumulated the
    tokens itself can ignore it and one that did not does not have to.
    """

    text: str
    action: ChatAction | None = None


class ChatDoneFrame(BaseModel):
    """``event: done`` on ``POST /api/chat/stream``."""

    result: ChatResult


class GenerateDoneFrame(BaseModel):
    """``event: done`` on ``POST /api/resumes/stream``: the stored row.

    The full :class:`~resumetailor.db.models.GeneratedResume`, ``yaml_content``
    included, because the row has just been written and the client would
    otherwise fetch it back immediately.
    """

    result: GeneratedResume


class EvaluateDoneFrame(BaseModel):
    """``event: done`` on ``POST /api/evaluate/stream``: the score."""

    result: EvaluationResult


@dataclass(frozen=True)
class StreamContract:
    """Every frame one streaming route can emit, by event name.

    A dataclass rather than a model: it holds model *classes*, and it is read
    at import time by the OpenAPI builder and by a test. Nothing validates it
    at runtime because nothing receives it over a wire.

    ``frames`` is ordered the way a successful stream emits them, which is also
    the order the OpenAPI ``oneOf`` lists them in, so the generated types read
    in the order a consumer meets them.
    """

    summary: str
    frames: dict[str, type[BaseModel]]


#: Route path -> what that route streams. The one place the three SSE contracts
#: are written down. ``api/openapi.py`` reads this to document each streaming
#: route's 200; ``tests/test_api_contract.py`` reads it to assert every route
#: that returns ``text/event-stream`` appears here and nothing else does.
STREAM_CONTRACTS: Final[dict[str, StreamContract]] = {
    "/api/resumes/stream": StreamContract(
        summary="Tailor the master resume to a job description.",
        frames={
            "progress": SseProgressFrame,
            "done": GenerateDoneFrame,
            "error": SseErrorFrame,
        },
    ),
    "/api/chat/stream": StreamContract(
        summary="One assistant turn, token by token.",
        frames={
            "token": SseTokenFrame,
            "done": ChatDoneFrame,
            "error": SseErrorFrame,
        },
    ),
    "/api/evaluate/stream": StreamContract(
        summary="Score one resume against one job description.",
        frames={
            "progress": SseProgressFrame,
            "done": EvaluateDoneFrame,
            "error": SseErrorFrame,
        },
    ),
}
