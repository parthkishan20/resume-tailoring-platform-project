"""The API contract, asserted against itself.

Four things have to stay true for the typed frontend client to be worth
anything, and none of them is visible in a normal route test:

1. **Every route declares its response.** D-54. A route with no
   ``response_model`` and no declared media type documents its body as ``{}``,
   which is what let the frontend's hand-written types go unchecked for the
   life of the project. :func:`test_every_route_declares_a_response_body`
   fails on the next one added without one, rather than waiting for someone to
   notice the generated types are missing a shape.

2. **The committed OpenAPI document matches the application.**
   ``frontend/src/lib/api/generated/`` holds the exported document and the
   TypeScript generated from it. They are build artifacts, so they can be
   stale, and a stale contract is worse than no contract: ``tsc`` would go on
   proving the client matches a server that no longer exists. Compared here as
   parsed JSON rather than bytes, because prettier owns the formatting of a
   file inside ``frontend/``.

3. **The published error vocabulary is complete.** ``ERROR_CODES`` is derived
   from the exception tree, and this asserts the derivation actually reaches
   every class, including the one that is mapped through an MRO rather than
   through ``HTTP_MAPPED_ERRORS``.

4. **The SSE frame models match what the routes emit.** The frames are
   documentation (``api/schemas/sse.py`` says so), so nothing would otherwise
   notice if a route's frame and its declared schema drifted apart. These
   tests drive the real routes and validate the frames they produce against
   the models, which is the only version of this check that cannot be fooled.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from resumetailor.api.openapi import build_openapi, render_openapi
from resumetailor.api.schemas.errors import (
    ERROR_CODES,
    SSE_ONLY_ERROR_CODES,
    UNREACHABLE_ERRORS,
)
from resumetailor.api.schemas.sse import STREAM_CONTRACTS
from resumetailor.core.errors import BackendError, LLMUnavailableError
from resumetailor.llm.errors import LLMEmptyResponseError
from resumetailor.main import app

#: Where the export lands, and what the TypeScript generator reads.
_COMMITTED_SPEC = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "lib"
    / "api"
    / "generated"
    / "openapi.json"
)

_REGENERATE = "run `npm run api:generate` in frontend/ and commit the result"

#: Routes whose 200 is not JSON, so ``response_model`` does not apply. Each
#: declares its real media type in the route decorator instead, which the
#: assertion below checks for rather than taking this list on trust.
_NON_JSON_ROUTES = {
    ("/api/master-resume/preview", "GET"): "application/pdf",
    ("/api/resumes/{resume_id}/pdf", "GET"): "application/pdf",
    ("/api/resumes/stream", "POST"): "text/event-stream",
    ("/api/chat/stream", "POST"): "text/event-stream",
    ("/api/evaluate/stream", "POST"): "text/event-stream",
}


def _api_routes() -> list[APIRoute]:
    """Every route this application serves, static mount excluded."""
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
    ]


def _frames(body: str) -> list[tuple[str, Any]]:
    """The ``(event, payload)`` pairs of an SSE response body."""
    parsed: list[tuple[str, Any]] = []
    event = "message"
    for line in body.split("\n"):
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            parsed.append((event, json.loads(line.removeprefix("data:").strip())))
    return parsed


# -- 1. every route declares its response ----------------------------------


def test_every_route_declares_a_response_body() -> None:
    """D-54: no route may leave its 200 undocumented."""
    undeclared = []
    for route in _api_routes():
        key = (route.path, next(iter(route.methods)))
        if 204 in {route.status_code}:
            continue
        if key in _NON_JSON_ROUTES:
            continue
        if route.response_model is None:
            undeclared.append(key)
    assert undeclared == [], (
        "these routes have no `response_model`, so the OpenAPI document "
        "describes their body as `{}` and the generated TypeScript has no "
        f"type for it: {undeclared}"
    )


@pytest.mark.parametrize(("key", "media_type"), sorted(_NON_JSON_ROUTES.items()))
def test_a_non_json_route_documents_its_media_type(
    key: tuple[str, str], media_type: str
) -> None:
    """A route exempt from ``response_model`` still has to say what it sends.

    Without this the exemption list above would be a way to opt out of D-54
    rather than a statement about five routes that genuinely do not return
    JSON.
    """
    path, method = key
    operation = build_openapi(app)["paths"][path][method.lower()]
    assert media_type in operation["responses"]["200"]["content"], (
        f"{method} {path} is exempt from `response_model` but its 200 does "
        f"not declare {media_type}"
    )


def test_every_route_with_a_path_parameter_documents_a_404() -> None:
    """A route that can answer "no such thing" has to say so.

    Every one of these raises ``HTTPException(404)`` in its body; an
    undocumented 404 is a branch a generated client cannot see.
    """
    spec = build_openapi(app)
    for route in _api_routes():
        if "{" not in route.path:
            continue
        for method in route.methods:
            responses = spec["paths"][route.path][method.lower()]["responses"]
            assert "404" in responses, f"{method} {route.path} documents no 404"


# -- 2. the committed document matches the application ---------------------


def test_the_committed_openapi_document_is_current() -> None:
    """The exported spec is what this application would export today."""
    assert _COMMITTED_SPEC.exists(), f"{_COMMITTED_SPEC} is missing: {_REGENERATE}"
    committed = json.loads(_COMMITTED_SPEC.read_text(encoding="utf-8"))
    assert committed == build_openapi(app), (
        "the committed OpenAPI document no longer matches the routes. The "
        f"generated TypeScript is therefore stale too: {_REGENERATE}"
    )


def test_the_export_is_stable_across_runs() -> None:
    """Two exports of one application produce identical text.

    If they did not, regenerating would produce a diff on every run and the
    check above would be unusable as a gate.
    """
    assert render_openapi(app) == render_openapi(app)


def test_every_streaming_route_has_a_frame_contract() -> None:
    """``STREAM_CONTRACTS`` and the routers cannot drift apart."""
    streaming = {
        path
        for (path, _), media in _NON_JSON_ROUTES.items()
        if media == "text/event-stream"
    }
    assert set(STREAM_CONTRACTS) == streaming


# -- 3. the published error vocabulary -------------------------------------


def _error_classes() -> set[type[BackendError]]:
    """Every class in the taxonomy, with every declaring module imported.

    The imports are the point. ``__subclasses__()`` only knows about a class
    whose module has been loaded, so a test that does not force the imports
    would pass for whichever classes the session happened to have reached and
    say nothing about the rest. Two of them live outside ``core.errors`` and
    are listed here by name for the same reason ``api/schemas/errors.py``
    imports them.
    """
    import resumetailor.db.migrate
    import resumetailor.llm.errors

    def walk(root: type[BackendError]) -> set[type[BackendError]]:
        found = {root}
        for subclass in root.__subclasses__():
            found |= walk(subclass)
        return found

    return walk(BackendError)


def test_every_error_class_is_either_published_or_declared_unreachable() -> None:
    """No error class may be silently absent from the published vocabulary.

    Both directions matter. A request-time error that is not published leaves
    the frontend unable to branch on it, and a startup-only error that *is*
    published puts a member in the frontend's ``ErrorCode`` union that no
    response can ever carry. A new class has to be a deliberate choice between
    the two, which is what this asserts.
    """
    unaccounted = {
        error
        for error in _error_classes()
        if error not in UNREACHABLE_ERRORS and error.code not in ERROR_CODES
    }
    assert unaccounted == set(), (
        "these error classes are neither published in ERROR_CODES nor named "
        "in UNREACHABLE_ERRORS, so the frontend cannot branch on them: "
        f"{sorted(error.__name__ for error in unaccounted)}"
    )

    published_but_unreachable = {
        error for error in UNREACHABLE_ERRORS if error.code in ERROR_CODES
    }
    assert published_but_unreachable == set(), (
        "these are declared unreachable but published anyway: "
        f"{sorted(error.__name__ for error in published_but_unreachable)}"
    )


def test_the_vocabulary_does_not_depend_on_import_order() -> None:
    """The defect this nearly shipped with.

    ``MigrationError`` is declared in ``db/migrate.py``, which ``main.py``
    imports lazily inside the lifespan. Before ``api/schemas/errors.py``
    imported it by name, the exported document and the document served by a
    process that had completed a boot listed different codes, and the check
    above only failed once a test had started the application.
    """
    from resumetailor.db.migrate import MigrationError

    assert MigrationError in UNREACHABLE_ERRORS
    assert MigrationError.code not in ERROR_CODES
    assert MigrationError in _error_classes()


def test_the_mro_mapped_error_is_in_the_vocabulary() -> None:
    """The case the derivation exists for.

    ``LLMEmptyResponseError`` is absent from ``HTTP_MAPPED_ERRORS`` on purpose
    (task 2.1 avoided editing a table task 2.4 was rewriting), so reading that
    tuple would have missed it.
    """
    assert issubclass(LLMEmptyResponseError, LLMUnavailableError)
    assert LLMEmptyResponseError.code in ERROR_CODES


def test_the_sse_only_codes_are_not_exception_attributes() -> None:
    """The four codes no class declares, so the list stays honest."""
    declared = {error.code for error in BackendError.__subclasses__()} | {
        BackendError.code
    }
    assert set(SSE_ONLY_ERROR_CODES).isdisjoint(declared)


def test_the_openapi_document_publishes_the_vocabulary() -> None:
    """The enum the frontend's `ErrorCode` union is generated from."""
    component = build_openapi(app)["components"]["schemas"]["ErrorCode"]
    assert component["enum"] == list(ERROR_CODES)


# -- 4. the frames match the models ----------------------------------------


@pytest.mark.anyio
async def test_the_generation_stream_frames_match_their_models(client, sim) -> None:
    """Drive the real route and validate every frame it sent."""
    from resumetailor.api.schemas.sse import GenerateDoneFrame, SseProgressFrame

    await client.put("/api/master-resume", json={"yaml_content": "cv:\n  name: T"})
    sim.sim_pdf_render.set_response(b"%PDF-1.4 fake")
    response = await client.post("/api/resumes/stream", json={"job_description": "jd"})

    models: dict[str, type[BaseModel]] = {
        "progress": SseProgressFrame,
        "done": GenerateDoneFrame,
    }
    frames = _frames(response.text)
    assert frames, "the stream produced no frames"
    for event, payload in frames:
        models[event].model_validate(payload)
    assert frames[-1][0] == "done"


@pytest.mark.anyio
async def test_the_chat_stream_frames_match_their_models(client, sim) -> None:
    from resumetailor.api.schemas.sse import ChatDoneFrame, SseTokenFrame

    sim.sim_llm.set_stream_chunks(["Hel", "lo"])
    response = await client.post("/api/chat/stream", json={"message": "hi"})

    models: dict[str, type[BaseModel]] = {
        "token": SseTokenFrame,
        "done": ChatDoneFrame,
    }
    frames = _frames(response.text)
    assert frames, "the stream produced no frames"
    for event, payload in frames:
        models[event].model_validate(payload)


@pytest.mark.anyio
async def test_the_evaluate_stream_frames_match_their_models(client, sim) -> None:
    from resumetailor.api.schemas.sse import EvaluateDoneFrame, SseProgressFrame

    response = await client.post(
        "/api/evaluate/stream",
        json={"yaml_content": "cv:\n  name: T", "job_description": "jd"},
    )

    models: dict[str, type[BaseModel]] = {
        "progress": SseProgressFrame,
        "done": EvaluateDoneFrame,
    }
    frames = _frames(response.text)
    assert frames, "the stream produced no frames"
    for event, payload in frames:
        models[event].model_validate(payload)


@pytest.mark.anyio
async def test_an_error_frame_matches_the_model_and_the_vocabulary(client, sim) -> None:
    """An ``event: error`` frame validates, and its code is a published one."""
    from resumetailor.api.schemas.sse import SseErrorFrame

    sim.sim_llm.set_stream_error(
        LLMUnavailableError("provider text, not for the client")
    )
    response = await client.post("/api/chat/stream", json={"message": "hi"})

    errors = [payload for event, payload in _frames(response.text) if event == "error"]
    assert len(errors) == 1
    frame = SseErrorFrame.model_validate(errors[0])
    assert frame.code in ERROR_CODES


# -- the SSE code literals, reconciled -------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/chat/stream", {"message": "hi"}),
        (
            "/api/evaluate/stream",
            {"yaml_content": "cv:\n  name: T", "job_description": "jd"},
        ),
    ],
)
async def test_a_subclassed_error_keeps_its_own_code_on_a_stream(
    client, sim, path: str, body: dict[str, str]
) -> None:
    """The defect the three routes' ``code`` literals caused, on each route.

    ``LLMEmptyResponseError`` derives from ``LLMUnavailableError`` so that it
    is HTTP-mapped through the MRO. That is also what made the literals wrong:
    ``except LLMUnavailableError`` caught it and the branch then named
    ``"LLM_UNAVAILABLE"`` by hand, so "the provider is down" and "the provider
    answered with nothing" reached the browser as the same frame, and the
    frontend could not tell them apart however carefully it branched.
    """
    sim.sim_llm.set_stream_error(LLMEmptyResponseError("finish_reason=content_filter"))
    sim.sim_llm.set_complete_error(
        LLMEmptyResponseError("finish_reason=content_filter")
    )

    response = await client.post(path, json=body)

    errors = [payload for event, payload in _frames(response.text) if event == "error"]
    assert errors == [
        {
            "error": LLMEmptyResponseError.client_message,
            "code": "LLM_EMPTY_RESPONSE",
        }
    ]


@pytest.mark.anyio
async def test_a_subclassed_error_keeps_its_own_code_on_the_generation_stream(
    client, sim
) -> None:
    """The same guarantee on the route that errors mid-pipeline."""
    await client.put("/api/master-resume", json={"yaml_content": "cv:\n  name: T"})
    sim.sim_llm.set_complete_error(LLMEmptyResponseError("finish_reason=length"))

    response = await client.post("/api/resumes/stream", json={"job_description": "jd"})

    errors = [payload for event, payload in _frames(response.text) if event == "error"]
    assert errors == [
        {
            "error": LLMEmptyResponseError.client_message,
            "code": "LLM_EMPTY_RESPONSE",
        }
    ]


@pytest.mark.anyio
async def test_a_stream_error_frame_is_still_inside_a_200(client, sim) -> None:
    """D-55, pinned rather than fixed.

    The status line is sent before the generator runs, so a failure cannot
    change it. This test exists so that the limitation is recorded as a
    deliberate state of the system: if a later task fixes it at the transport
    level, this test fails and has to be rewritten, which is the right way for
    that change to announce itself.
    """
    sim.sim_llm.set_stream_error(LLMUnavailableError("down"))
    response = await client.post("/api/chat/stream", json={"message": "hi"})
    assert response.status_code == 200
    assert any(event == "error" for event, _ in _frames(response.text))


# -- bounded pagination (D-10) ---------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": "-1"},
        {"limit": "0"},
        {"limit": "101"},
        {"page": "0"},
        {"page": "-5"},
        {"sort": "created_at"},
        {"order": "descending"},
    ],
)
async def test_the_list_route_refuses_a_parameter_outside_its_contract(
    client, params: dict[str, str]
) -> None:
    """D-10. The repository clamped these; the route now declares the bound.

    ``sort`` and ``order`` are the sharper half: the repository turns anything
    other than ``date`` into a sort by job description, so ``?sort=created_at``
    used to answer 200 with a page ordered by something else entirely.
    """
    response = await client.get("/api/resumes", params=params)
    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    "params",
    [
        {},
        {"limit": "1"},
        {"limit": "100"},
        {"page": "1"},
        {"sort": "date", "order": "desc"},
        {"sort": "jd", "order": "asc"},
    ],
)
async def test_the_list_route_accepts_everything_inside_its_contract(
    client, params: dict[str, str]
) -> None:
    response = await client.get("/api/resumes", params=params)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_the_documented_bounds_are_the_enforced_ones() -> None:
    """The OpenAPI document repeats the repository's own cap, not a guess."""
    from resumetailor.db.repositories.resumes import MAX_PAGE_SIZE

    parameters = build_openapi(app)["paths"]["/api/resumes"]["get"]["parameters"]
    by_name = {parameter["name"]: parameter["schema"] for parameter in parameters}
    assert by_name["limit"]["maximum"] == MAX_PAGE_SIZE
    assert by_name["limit"]["minimum"] == 1
    assert by_name["page"]["minimum"] == 1
    assert by_name["sort"]["enum"] == ["date", "jd"]
    assert by_name["order"]["enum"] == ["asc", "desc"]


# -- D-69 -----------------------------------------------------------------


@pytest.mark.anyio
async def test_the_patch_body_is_bounded(client) -> None:
    """D-69: the two fields task 2.4 left unbounded when it capped the rest."""
    from resumetailor.api.routers.resumes import MAX_RESUME_NAME_CHARS
    from resumetailor.core.security import MAX_RESUME_YAML_CHARS

    over_name = await client.patch(
        "/api/resumes/1", json={"name": "x" * (MAX_RESUME_NAME_CHARS + 1)}
    )
    assert over_name.status_code == 422

    over_yaml = await client.patch(
        "/api/resumes/1", json={"yaml_content": "x" * (MAX_RESUME_YAML_CHARS + 1)}
    )
    assert over_yaml.status_code == 422
