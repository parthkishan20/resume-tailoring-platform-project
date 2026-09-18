# backend/src/resumetailor/api/routers/master_resume.py
from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.db.repositories import (
    get_master_resume,
    upsert_master_resume,
    delete_master_resume,
)
from resumetailor.deps import get_backend
from resumetailor.ports import RenderError
from resumetailor.yaml_utils import normalize_to_rendercv

router = APIRouter()

_IMPORT_SYSTEM_PROMPT = """\
You are a resume parser. Convert the resume text to EXACTLY this rendercv YAML schema.

SCHEMA (copy field names verbatim — do not invent new keys):

cv:
  name: Full Name
  email: email@example.com
  phone: "+1-555-000-0000"
  location: City, State
  website: example.com          # omit if not present
  social_networks:              # omit entire block if no socials
    - network: LinkedIn         # must be exactly "LinkedIn" or "GitHub"
      username: handle-only     # username only, no URL prefix
    - network: GitHub
      username: handle-only
  sections:
    experience:
      - company: Company Name
        position: Job Title
        location: City, State
        start_date: "2023-01"   # YYYY-MM format
        end_date: "2024-08"     # YYYY-MM or "present"
        highlights:
          - Past-tense bullet describing achievement (one sentence)
    education:
      - institution: University Name
        area: Field of Study
        degree: "MS"            # short form: BS, MS, PhD, etc.
        start_date: "2024-09"
        end_date: "2026-05"
        highlights:
          - "GPA: 3.9/4.0"
    projects:
      - name: Project Name
        date: "2024"
        url: https://...        # omit if not present
        highlights:
          - Past-tense bullet
    skills:
      - label: "Category Name"
        details: "Skill1, Skill2, Skill3"
    certifications:             # omit section if none
      - name: Cert Name
        date: "2023"
design:
  theme: classic

RULES:
- Output ONLY the YAML above — no markdown fences, no prose.
- First line must be: cv:
- All section entries go under cv.sections — NEVER directly under cv.
- social_networks username must be the handle only, strip any URL.
- dates must be YYYY-MM (e.g. "2023-01"). Use "present" for current roles.
- highlights must be a list of strings, one bullet per line.
- Omit optional fields (url, website, certifications) when not in source.
- Omit phone entirely if no phone number appears in the source — never invent one.
"""


def _db_path() -> str:
    return get_settings().DB_PATH


class MasterResumeBody(BaseModel):
    yaml_content: str


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
        pdf_bytes = await backend.render(normalize_to_rendercv(row.yaml_content))
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post("/api/master-resume/import")
async def import_pdf(
    file: UploadFile = File(...),
    api: BackendAPI = Depends(get_backend),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
    pdf_bytes = await file.read()
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
            {"role": "system", "content": _IMPORT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Resume text:\n{text}"},
        ],
        response_format=response_format,
    )
    yaml_content = normalize_to_rendercv(json.loads(result_str)["yaml_content"])
    row = await asyncio.to_thread(upsert_master_resume, _db_path(), yaml_content)
    return row
