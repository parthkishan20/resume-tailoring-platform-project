"""The OpenAPI document: built, corrected, and exportable as a file.

FastAPI generates a document from the routes on its own. Two things it cannot
generate are added here, and one build step is added around it.

**The streaming routes.** A ``StreamingResponse`` has no ``response_model``, so
all three SSE routes were documented as ``application/json`` returning ``{}``.
:func:`_describe_streams` replaces each one's 200 with the real media type and
a ``oneOf`` over the frame payloads declared in
:data:`~resumetailor.api.schemas.sse.STREAM_CONTRACTS`, which also puts those
payload models in ``components.schemas`` where the TypeScript generator can
reach them.

**D-55, in the one place a client will read it.** All three streams answer 200
and then report failure in an ``event: error`` frame, so nothing that reads
only the status line can tell a total provider outage from a successful
generation. That is a property of SSE and of where the status line is sent,
not an oversight, and the fix that would remove it is a transport change
rather than a schema change. Until then it is written into the document's
description and into each streaming route's 200 description, because a client
author who does not know it will write a health check that always passes.

**Export.** ``python -m resumetailor.api.openapi <path>`` writes the document
as JSON. It is a build step, not a server call: it imports the application,
never starts it, needs no port and no database, and is what generates
``frontend/src/lib/api/openapi.json`` and from there the TypeScript types. The
output is stable across runs (two-space indent, sorted keys) so that
regenerating it produces either no diff or a diff that is the contract change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi
from pydantic.json_schema import models_json_schema

from resumetailor.api.schemas.errors import ERROR_CODES
from resumetailor.api.schemas.sse import STREAM_CONTRACTS

if TYPE_CHECKING:
    from fastapi import FastAPI
    from pydantic import BaseModel

__all__ = [
    "API_DESCRIPTION",
    "API_TITLE",
    "API_VERSION",
    "build_openapi",
    "install_openapi",
    "render_openapi",
]

API_TITLE = "ResumeTailor API"

#: Tracks ``backend/pyproject.toml``'s ``version``, and is the version a
#: generated client is generated against. Not read from package metadata:
#: ``uv.lock`` declares this project virtual, so the package is never installed
#: and ``importlib.metadata`` has nothing to look up.
API_VERSION = "0.1.0"

API_DESCRIPTION = """
The ResumeTailor HTTP API.

**Errors come in three shapes.** A domain error answers `{"error", "code"}`;
an `HTTPException` raised inside a route answers `{"detail": "<sentence>"}`;
a request that fails validation before reaching a handler answers
`{"detail": [...]}`. Every documented error status lists all three, because
422 in particular can arrive as any of them. Branch on `code` where there is
one, and never on the human-readable text, which is fixed per error class and
deliberately says nothing about the inside of the server.

**The three streaming routes always answer 200.** `POST /api/resumes/stream`,
`POST /api/chat/stream` and `POST /api/evaluate/stream` send their status line
before the work starts, so a failure arrives as an `event: error` frame inside
a successful response rather than as an HTTP error status. A load balancer, an
uptime check, or any client that reads only the status line will see a
complete provider outage as 100% success. Read the frames. A client is done
with one of these responses when it has seen an `event: done` or an
`event: error` frame, not when the body ends.
""".strip()

#: Wording reused on each streaming route's 200, so the limitation above is
#: also stated where a generated client's own comment for that route will be.
_STREAM_200_NOTE = (
    "Server-sent events. Always 200, including on failure: the status line is "
    "sent before the work starts, so an error arrives as an `event: error` "
    "frame in this body. Read the frames, not the status."
)


def _frame_schemas(models: list[type[BaseModel]]) -> dict[str, Any]:
    """The JSON schema of every frame payload, and of everything they nest.

    ``models_json_schema`` rather than one ``model_json_schema`` call per
    model: the frames share nested models, and asking each one separately
    produces a private copy of every shared definition under a different name.

    Serialization mode, because these describe a response body. For these
    models the two modes agree, which is why the names stay plain (no
    ``-Input``/``-Output`` suffix) and merge cleanly with what FastAPI emits
    for the non-streaming routes.
    """
    _, top_level = models_json_schema(
        [(model, "serialization") for model in models],
        ref_template="#/components/schemas/{model}",
    )
    return dict(top_level.get("$defs", {}))


def _declare_error_codes(schema: dict[str, Any]) -> None:
    """Publish the ``code`` vocabulary as a schema component.

    A component rather than an ``enum`` on ``ErrorEnvelope.code``: the client
    must keep working when it meets a code it has never heard of, so the
    *field* stays an open ``string`` and the vocabulary is published beside it.
    Declared this way the TypeScript generator emits a union of string
    literals, which is what makes ``if (error.code === "LLM_ATUH_ERROR")`` a
    compile error in the frontend instead of a branch that never runs.

    Nothing references this component. That is deliberate and is why it has to
    be added by hand: FastAPI only emits components something refers to.
    """
    schema.setdefault("components", {}).setdefault("schemas", {})["ErrorCode"] = {
        "type": "string",
        "enum": list(ERROR_CODES),
        "description": (
            "Every `code` this API can send, on an HTTP error body or in an "
            "SSE `event: error` frame. Compare against it; do not assume it "
            "is exhaustive at runtime, since a server newer than the client "
            "can send one that is not listed here."
        ),
    }


def _describe_streams(schema: dict[str, Any]) -> None:
    """Give each streaming route a real 200, in place.

    Raises:
        KeyError: if a path in ``STREAM_CONTRACTS`` is not a POST route on this
            application. That means the contract table and the routers have
            drifted, which is exactly the failure this module exists to make
            impossible, so it fails the build rather than quietly documenting
            two of the three streams.
    """
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    frames = {
        model
        for contract in STREAM_CONTRACTS.values()
        for model in contract.frames.values()
    }
    ordered = sorted(frames, key=lambda model: model.__name__)
    for name, definition in _frame_schemas(ordered).items():
        components.setdefault(name, definition)

    for path, contract in STREAM_CONTRACTS.items():
        operation = schema["paths"][path]["post"]
        events = ", ".join(f"`event: {name}`" for name in contract.frames)
        operation["responses"]["200"] = {
            "description": f"{_STREAM_200_NOTE}\n\nFrames, in order: {events}.",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "description": (
                            "The JSON after `data:` on one frame. Which schema "
                            "applies is decided by the preceding `event:` line, "
                            "which is not part of the payload: "
                            + "; ".join(
                                f"`{name}` is `{model.__name__}`"
                                for name, model in contract.frames.items()
                            )
                            + "."
                        ),
                        "oneOf": [
                            {"$ref": f"#/components/schemas/{model.__name__}"}
                            for model in contract.frames.values()
                        ],
                    }
                }
            },
        }


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """The document for ``app``, streaming routes included.

    Pure with respect to the application: it reads ``app.routes`` and returns
    a new dict, so the export script and the served ``/openapi.json`` produce
    the same bytes.
    """
    schema = get_openapi(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        routes=app.routes,
    )
    _declare_error_codes(schema)
    _describe_streams(schema)
    return schema


def install_openapi(app: FastAPI) -> None:
    """Make ``app.openapi()`` and ``/openapi.json`` serve the corrected document.

    FastAPI caches in ``app.openapi_schema``; this keeps that behaviour, so the
    document is still built once per process.
    """

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def render_openapi(app: FastAPI) -> str:
    """The document as the bytes that get written to disk.

    Sorted keys and a trailing newline: regenerating an unchanged contract must
    produce an empty diff, or the ``contract`` gate in CI cannot tell a stale
    checked-in document from a reordered one.
    """
    return json.dumps(build_openapi(app), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    """Write the document to ``argv[0]``. See the module docstring."""
    if len(argv) != 1:
        sys.stderr.write("usage: python -m resumetailor.api.openapi <output.json>\n")
        return 2

    from resumetailor.main import app

    destination = Path(argv[0])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_openapi(app), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
