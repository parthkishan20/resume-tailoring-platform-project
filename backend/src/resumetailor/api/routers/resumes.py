# backend/src/resumetailor/api/routers/resumes.py
from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal

from resumetailor.api.schemas.errors import error_responses, pdf_response
from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.db.models import GeneratedResume, ResumePage
from resumetailor.db.repositories import (
    list_resumes, get_resume, update_resume, delete_resume,
    get_master_resume, get_rules,
)
from resumetailor.db.repositories.resumes import MAX_PAGE_SIZE
from resumetailor.deps import get_backend
from resumetailor.core.errors import BackendError
from resumetailor.core.security import MAX_JOB_DESCRIPTION_CHARS, MAX_RESUME_YAML_CHARS, resolve_within
from resumetailor.domain.tailoring import Stage, TailoredResume, store_tailored_resume, tailor
from resumetailor.rendering.errors import RenderIssue
from resumetailor.resume_schema.normalize import normalize_to_rendercv
from resumetailor.resume_schema.validate import validate

router = APIRouter()
logger = logging.getLogger(__name__)

# The SSE contract. The frontend matches on these strings, so they live at the
# wire boundary and the pipeline yields `Stage` members instead (D-04's
# extraction; see domain/tailoring.py).
_PROGRESS_MESSAGES: dict[Stage, str] = {
    Stage.ANALYZING: "Analyzing job description...",
    Stage.TAILORING: "Tailoring content...",
    Stage.RENDERING: "Rendering PDF...",
}


# D-69's other half. Every other input cap in this application lives in
# `core/security.py`, which task 2.4 built as the one place the numbers are;
# this one is here because that file is not this task's to write and a blocker
# for a single integer would have cost more than it bought. It belongs there,
# next to the other four `MAX_*_CHARS`, and moving it is a one-line change for
# whoever next owns that file.
#
# 200 rather than something nearer the YAML cap because a name is a label in a
# list view: the generator's own template produces about 60 characters.
MAX_RESUME_NAME_CHARS = 200


def _db_path() -> str:
    return get_settings().DB_PATH


def _pdfs_dir() -> str:
    return get_settings().PDFS_DIR


def _jsonable(value: object) -> object:
    """Serialise a repository model inside an SSE frame.

    Repositories return Pydantic models rather than dicts now; `json.dumps`
    does not know how to encode one. The frame's contents are unchanged: a
    model dumps to exactly the keys the raw `sqlite3.Row` dict carried.
    """
    if isinstance(value, BaseModel):
        return value.model_dump()
    raise TypeError(type(value))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=_jsonable)}\n\n"


def _error_frame(exc: BackendError) -> str:
    """One SSE error frame, and the log line that keeps the detail.

    D-53, on the streaming path. An SSE error never reaches the exception
    handler in `core/errors.py`, so both halves of that fix have to happen
    here: the client gets the class's fixed `client_message`, and the operator
    gets `str(exc)` — the render subprocess's output, the provider's exception
    text — at ERROR, with the request id `core/logging.py` attaches.

    Task 2.2 removed the `code` parameter. Task 2.5 left the wire code a
    literal at each call site, matched by hand to the exception the branch
    caught, which held only as long as no exception class was ever a subclass
    of another. `LLMEmptyResponseError` already is (D-59: it derives from
    `LLMUnavailableError` so that it is HTTP-mapped through the MRO), so
    `except LLMUnavailableError` caught it and reported the base class's
    `LLM_UNAVAILABLE` — the same frame for "the provider is down" and "the
    provider refused to answer", which the frontend is supposed to be able to
    tell apart. Reading `exc.code` is the only version of this that cannot
    drift.
    """
    logger.error(
        "sse domain error: %s",
        exc.code,
        exc_info=exc,
        extra={"error_code": exc.code, "error_detail": exc.detail},
    )
    return _sse("error", {"error": exc.client_message, "code": exc.code})


def _issue_detail(issues: list[RenderIssue]) -> str:
    """The validation failures, as one line the user can act on.

    Safe to return, unlike a `RenderError`'s text (D-53): these describe the
    submitted document, field by field, and say nothing about the inside of
    the process.
    """
    return "This resume is not valid: " + "; ".join(
        f"{issue.path}: {issue.message}" for issue in issues
    )


class GenerateRequest(BaseModel):
    job_description: str = Field(max_length=MAX_JOB_DESCRIPTION_CHARS)


class ResumeUpdate(BaseModel):
    """Either field, or both. D-69: both are bounded now.

    These were the two bare `str` fields task 2.4 missed when it capped the
    other five for D-47, so until now only the 1 MiB JSON body cap stood
    between a caller and a 900 KB resume name. `name` is bounded well below
    the YAML cap because it is a label in a list, not a document.
    """

    name: str | None = Field(default=None, max_length=MAX_RESUME_NAME_CHARS)
    yaml_content: str | None = Field(default=None, max_length=MAX_RESUME_YAML_CHARS)


@router.get("/api/resumes", response_model=ResumePage, responses=error_responses(422))
async def list_generated(
    sort: Literal["date", "jd"] = "date",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    """One page of the library.

    D-10. The repository has clamped `page` and `limit` since task 1.2, so
    `?limit=-1` stopped returning the whole table then; what was still missing
    is that the *documented* contract said `int`, so a generated client had no
    way to know the bound existed and a caller learned it by being silently
    given something else. These four constraints are the same bound, declared:
    an out-of-range value is now a 422 naming the field.

    `sort` and `order` were the sharper half of the same gap. Both reached a
    repository that turns anything other than `date` into a sort by job
    description and anything other than `desc` into ascending, so `?sort=nmae`
    answered 200 with a page sorted by something the caller did not ask for.
    The two `Literal`s are what the frontend has always sent.
    """
    return await asyncio.to_thread(list_resumes, _db_path(), sort=sort, order=order, page=page, limit=limit)


@router.post(
    "/api/resumes/stream",
    response_class=StreamingResponse,
    responses=error_responses(413, 422, 429),
)
async def generate_resume_stream(
    body: GenerateRequest,
    api: BackendAPI = Depends(get_backend),
):
    """Run the tailoring pipeline, narrating it as server-sent events.

    The work is `domain.tailoring`; this handler reads what the pipeline needs,
    turns each `Stage` into the progress frame the frontend expects, and hands
    the result to the one function that writes it.
    """
    async def event_gen():
        try:
            master = await asyncio.to_thread(get_master_resume, _db_path())
            if master is None:
                yield _sse("error", {"error": "No master resume found", "code": "NO_MASTER_RESUME"})
                return

            rules = await asyncio.to_thread(get_rules, _db_path())

            async for event in tailor(
                api,
                master_yaml=master.yaml_content,
                job_description=body.job_description,
                rules=rules,
            ):
                if isinstance(event, TailoredResume):
                    row = await asyncio.to_thread(
                        store_tailored_resume,
                        _db_path(), _pdfs_dir(),
                        job_description=body.job_description, result=event,
                    )
                    yield _sse("done", {"result": row})
                else:
                    yield _sse("progress", {"message": _PROGRESS_MESSAGES[event]})
        # D-53: the client gets `exc.client_message`, never `str(exc)`. See
        # `_error_frame`. One branch rather than the four this replaces,
        # because every one of them did the same thing and the only thing that
        # differed was a code literal that is now read off the exception. A new
        # domain error, or a subclass of an existing one, reaches the browser
        # with its own code and without a branch being added here.
        except BackendError as exc:
            yield _error_frame(exc)
        except Exception:
            # Not a domain error, so there is no vetted sentence to send: the
            # text of an unexpected exception is exactly what must not travel.
            logger.exception("sse generation failed", extra={"error_code": "GENERATION_FAILED"})
            yield _sse("error", {"error": BackendError.client_message, "code": "GENERATION_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.get(
    "/api/resumes/{resume_id}",
    response_model=GeneratedResume,
    responses=error_responses(404, 422),
)
async def get_generated(resume_id: int):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return row


@router.patch(
    "/api/resumes/{resume_id}",
    response_model=GeneratedResume,
    responses=error_responses(404, 413, 422),
)
async def patch_generated(resume_id: int, body: ResumeUpdate):
    """Rename a resume, or replace its YAML.

    D-04: a write path that stores a document refuses one that will not
    render, instead of storing it and surfacing the problem at render time.
    The check is `resume_schema.validate` — the same schema, the same theme
    and the same issue objects the renderer reports — run off the event loop
    because it builds RenderCV's model.

    D-57's other half is still open here: a successful YAML replacement leaves
    `pdf_path` pointing at a PDF rendered from the previous document. Calling
    `POST /api/resumes/{id}/render` after a PATCH is the current answer.
    """
    if body.yaml_content is not None:
        _, issues = await asyncio.to_thread(validate, body.yaml_content)
        if issues:
            raise HTTPException(status_code=422, detail=_issue_detail(issues))

    row = await asyncio.to_thread(
        update_resume, _db_path(), resume_id,
        name=body.name, yaml_content=body.yaml_content,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return row


@router.get(
    "/api/resumes/{resume_id}/pdf",
    response_class=FileResponse,
    responses={
        **pdf_response("The stored PDF, inline."),
        **error_responses(404, 422),
    },
)
async def get_pdf(resume_id: int):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    if row is None or not row.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    # D-25: a stored filename joined to PDFS_DIR must stay inside it. 404, not
    # 403: a 403 would confirm the path exists and that a check refused it.
    pdf_path = resolve_within(_pdfs_dir(), row.pdf_path)
    if pdf_path is None or not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(str(pdf_path), media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


@router.post(
    "/api/resumes/{resume_id}/render",
    status_code=200,
    response_model=GeneratedResume,
    responses=error_responses(404, 422, 500),
)
async def render_pdf(resume_id: int, api: BackendAPI = Depends(get_backend)):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    # D-57: normalize first, exactly as the generation pipeline and
    # `GET /api/master-resume/preview` do. This route used to hand
    # `row.yaml_content` to the renderer untouched, so the same document could
    # render through one path and fail through the other.
    pdf_bytes = await api.render(normalize_to_rendercv(row.yaml_content).yaml)
    pdf_path = Path(_pdfs_dir()) / f"{resume_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    updated = await asyncio.to_thread(
        update_resume, _db_path(), resume_id, pdf_path=f"{resume_id}.pdf"
    )
    return updated


@router.delete(
    "/api/resumes/{resume_id}",
    status_code=204,
    responses=error_responses(404, 422),
)
async def delete_generated(resume_id: int):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    deleted = await asyncio.to_thread(delete_resume, _db_path(), resume_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resume not found")
    if row and row.pdf_path:
        # D-25, as above: never unlink outside PDFS_DIR.
        pdf_path = resolve_within(_pdfs_dir(), row.pdf_path)
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)
