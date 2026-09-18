# backend/src/resumetailor/api/routers/resumes.py
from __future__ import annotations
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.database import (
    list_resumes, create_resume, get_resume, update_resume, delete_resume,
    get_master_resume, get_rules,
)
from resumetailor.deps import get_backend
from resumetailor.core.errors import LLMAuthError, LLMUnavailableError, RenderError, PDFExtractError
from resumetailor.prompts import GENERATION_SYSTEM_PROMPT, CRITIQUE_SYSTEM_PROMPT, rules_block
from resumetailor.resume_schema.normalize import normalize_to_rendercv

router = APIRouter()


def _db_path() -> str:
    return get_settings().DB_PATH


def _pdfs_dir() -> str:
    return get_settings().PDFS_DIR


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class GenerateRequest(BaseModel):
    job_description: str


class ResumeUpdate(BaseModel):
    name: str | None = None
    yaml_content: str | None = None


@router.get("/api/resumes")
async def list_generated(
    sort: str = "date", order: str = "desc", page: int = 1, limit: int = 20
):
    return await asyncio.to_thread(list_resumes, _db_path(), sort=sort, order=order, page=page, limit=limit)


@router.post("/api/resumes/stream")
async def generate_resume_stream(
    body: GenerateRequest,
    api: BackendAPI = Depends(get_backend),
):
    async def event_gen():
        try:
            # Fetch master resume
            master = await asyncio.to_thread(get_master_resume, _db_path())
            if master is None:
                yield _sse("error", {"error": "No master resume found", "code": "NO_MASTER_RESUME"})
                return

            yield _sse("progress", {"message": "Analyzing job description..."})

            # Normalise master resume to valid rendercv before feeding to the LLM
            master_yaml = normalize_to_rendercv(master["yaml_content"]).yaml

            # User-configured limits override the prompt's default counts
            rules_suffix = rules_block(await asyncio.to_thread(get_rules, _db_path()))

            # Pass 1: generate
            gen_response = await api.complete(
                [
                    {"role": "system", "content": GENERATION_SYSTEM_PROMPT + rules_suffix},
                    {"role": "user", "content": f"JD:\n{body.job_description}\n\nMaster:\n{master_yaml}"},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "tailored_resume",
                        "schema": {
                            "type": "object",
                            "properties": {"yaml_content": {"type": "string"}},
                            "required": ["yaml_content"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    },
                },
            )
            draft_yaml = normalize_to_rendercv(json.loads(gen_response)["yaml_content"]).yaml

            yield _sse("progress", {"message": "Tailoring content..."})

            # Pass 2: audit
            audit_response = await api.complete(
                [
                    {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT + rules_suffix},
                    {"role": "user", "content": f"Draft:\n{draft_yaml}\n\nMaster:\n{master_yaml}\n\nJD:\n{body.job_description}"},
                ]
            )
            # Strip AUDIT_START...AUDIT_END block
            if "AUDIT_END" in audit_response:
                final_yaml = audit_response.split("AUDIT_END", 1)[1].strip()
            else:
                final_yaml = audit_response.strip()
            final_yaml = normalize_to_rendercv(final_yaml).yaml

            yield _sse("progress", {"message": "Rendering PDF..."})

            # Render PDF
            pdf_bytes = await api.render(final_yaml)

            # Persist
            name = f"Resume — {body.job_description[:40]}"
            row = await asyncio.to_thread(
                create_resume, _db_path(), name, body.job_description, final_yaml
            )
            resume_id = row["id"]

            # Save PDF
            pdf_path = Path(_pdfs_dir()) / f"{resume_id}.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf_bytes)

            row = await asyncio.to_thread(
                update_resume, _db_path(), resume_id, pdf_path=f"{resume_id}.pdf"
            )

            yield _sse("done", {"result": row})
        except LLMAuthError as exc:
            yield _sse("error", {"error": str(exc), "code": "LLM_AUTH_ERROR"})
        except LLMUnavailableError as exc:
            yield _sse("error", {"error": str(exc), "code": "LLM_UNAVAILABLE"})
        except RenderError as exc:
            yield _sse("error", {"error": str(exc), "code": "RENDER_FAILED"})
        except PDFExtractError as exc:
            yield _sse("error", {"error": str(exc), "code": "PDF_EXTRACT_FAILED"})
        except Exception as exc:
            yield _sse("error", {"error": str(exc), "code": "GENERATION_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.get("/api/resumes/{resume_id}")
async def get_generated(resume_id: int):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return row


@router.patch("/api/resumes/{resume_id}")
async def patch_generated(resume_id: int, body: ResumeUpdate):
    row = await asyncio.to_thread(
        update_resume, _db_path(), resume_id,
        name=body.name, yaml_content=body.yaml_content,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return row


@router.get("/api/resumes/{resume_id}/pdf")
async def get_pdf(resume_id: int):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    if row is None or not row.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not found")
    pdf_path = Path(_pdfs_dir()) / row["pdf_path"]
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(str(pdf_path), media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


@router.post("/api/resumes/{resume_id}/render", status_code=200)
async def render_pdf(resume_id: int, api: BackendAPI = Depends(get_backend)):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    pdf_bytes = await api.render(row["yaml_content"])
    pdf_path = Path(_pdfs_dir()) / f"{resume_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    updated = await asyncio.to_thread(
        update_resume, _db_path(), resume_id, pdf_path=f"{resume_id}.pdf"
    )
    return updated


@router.delete("/api/resumes/{resume_id}", status_code=204)
async def delete_generated(resume_id: int):
    row = await asyncio.to_thread(get_resume, _db_path(), resume_id)
    deleted = await asyncio.to_thread(delete_resume, _db_path(), resume_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resume not found")
    if row and row.get("pdf_path"):
        pdf_path = Path(_pdfs_dir()) / row["pdf_path"]
        pdf_path.unlink(missing_ok=True)
