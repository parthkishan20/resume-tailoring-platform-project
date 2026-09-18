# backend/src/resumetailor/api/routers/master_resume.py
from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from resumetailor.api.schemas.errors import error_responses, pdf_response
from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.db.models import MasterResume
from resumetailor.db.repositories import (
    get_master_resume,
    upsert_master_resume,
    delete_master_resume,
)
from resumetailor.deps import get_backend
from resumetailor.core.errors import RenderError
from resumetailor.core.security import MAX_RESUME_YAML_CHARS, read_upload_capped
from resumetailor.rendering.errors import RenderIssue
from resumetailor.resume_schema.normalize import normalize_to_rendercv
from resumetailor.resume_schema.prompt import IMPORT_SYSTEM_PROMPT
from resumetailor.resume_schema.validate import validate

router = APIRouter()


def _issue_detail(issues: list[RenderIssue]) -> str:
    """The validation failures, as one line the user can act on.

    Same shape as `api/routers/resumes.py`'s helper of the same name (D-04's
    other route) -- kept local rather than imported, since a two-line string
    formatter is not worth coupling one route module to another's internals
    for.
    """
    return "This resume is not valid: " + "; ".join(
        f"{issue.path}: {issue.message}" for issue in issues
    )


def _db_path() -> str:
    return get_settings().DB_PATH


class MasterResumeBody(BaseModel):
    yaml_content: str = Field(max_length=MAX_RESUME_YAML_CHARS)


@router.get(
    "/api/master-resume",
    response_model=MasterResume,
    responses=error_responses(404),
)
async def get_resume():
    row = await asyncio.to_thread(get_master_resume, _db_path())
    if row is None:
        raise HTTPException(status_code=404, detail="No master resume found")
    return row


@router.put(
    "/api/master-resume",
    response_model=MasterResume,
    responses=error_responses(413, 422),
)
async def save_resume(body: MasterResumeBody):
    """Save the master resume, replacing whatever was there.

    D-04, closed here for the last route it was still open on: task 2.5
    closed it for `PATCH /api/resumes/{id}` and named this route as the
    other half, left alone because it did not own this file. Same check,
    same theme as the renderer would report: refuse to store a document that
    will not render, rather than storing it and surfacing the problem later
    at `GET /api/master-resume/preview` or a `POST /api/resumes/stream` that
    reads this row back out.
    """
    _, issues = await asyncio.to_thread(validate, body.yaml_content)
    if issues:
        raise HTTPException(status_code=422, detail=_issue_detail(issues))

    row = await asyncio.to_thread(upsert_master_resume, _db_path(), body.yaml_content)
    return row


@router.delete("/api/master-resume", status_code=204, responses=error_responses(404))
async def remove_resume():
    """Delete the master resume. 204: the row is gone, not reset (D-58)."""
    deleted = await asyncio.to_thread(delete_master_resume, _db_path())
    if not deleted:
        raise HTTPException(status_code=404, detail="No master resume to delete")


@router.get(
    "/api/master-resume/preview",
    response_class=Response,
    responses={
        **pdf_response("The master resume, rendered."),
        **error_responses(404, 422),
    },
)
async def preview_master_resume(
    backend: BackendAPI = Depends(get_backend),
):
    """Render the current master resume YAML to PDF and return it."""
    db_path = _db_path()
    row = await asyncio.to_thread(get_master_resume, db_path)
    if row is None:
        raise HTTPException(status_code=404, detail="No master resume found")

    try:
        pdf_bytes = await backend.render(normalize_to_rendercv(row.yaml_content).yaml)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=exc.client_message)

    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post(
    "/api/master-resume/import",
    response_model=MasterResume,
    responses=error_responses(400, 413, 422, 429, 500, 503),
)
async def import_pdf(
    file: UploadFile = File(...),
    api: BackendAPI = Depends(get_backend),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
    # D-48: bounded chunks with a running total, not `await file.read()`,
    # which materialised the whole body before any size check ran.
    pdf_bytes = await read_upload_capped(file)
    text = await api.extract(pdf_bytes)
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "imported_resume",
            "schema": {
                "type": "object",
                "properties": {"yaml_content": {"type": "string"}},
                "required": ["yaml_content"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    result_str = await api.complete(
        [
            {"role": "system", "content": IMPORT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Resume text:\n{text}"},
        ],
        response_format=response_format,
    )
    yaml_content = normalize_to_rendercv(json.loads(result_str)["yaml_content"]).yaml
    row = await asyncio.to_thread(upsert_master_resume, _db_path(), yaml_content)
    return row
