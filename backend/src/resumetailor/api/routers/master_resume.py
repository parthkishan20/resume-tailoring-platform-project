# backend/src/resumetailor/api/routers/master_resume.py
from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.db.repositories import (
    get_master_resume,
    upsert_master_resume,
    delete_master_resume,
)
from resumetailor.deps import get_backend
from resumetailor.core.errors import RenderError
from resumetailor.core.security import MAX_RESUME_YAML_CHARS, read_upload_capped
from resumetailor.resume_schema.normalize import normalize_to_rendercv
from resumetailor.resume_schema.prompt import IMPORT_SYSTEM_PROMPT

router = APIRouter()


def _db_path() -> str:
    return get_settings().DB_PATH


class MasterResumeBody(BaseModel):
    yaml_content: str = Field(max_length=MAX_RESUME_YAML_CHARS)


@router.get("/api/master-resume")
async def get_resume():
    row = await asyncio.to_thread(get_master_resume, _db_path())
    if row is None:
        raise HTTPException(status_code=404, detail="No master resume found")
    return row


@router.put("/api/master-resume")
async def save_resume(body: MasterResumeBody):
    row = await asyncio.to_thread(upsert_master_resume, _db_path(), body.yaml_content)
    return row


@router.delete("/api/master-resume", status_code=204)
async def remove_resume():
    deleted = await asyncio.to_thread(delete_master_resume, _db_path())
    if not deleted:
        raise HTTPException(status_code=404, detail="No master resume to delete")


@router.get("/api/master-resume/preview")
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


@router.post("/api/master-resume/import")
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
