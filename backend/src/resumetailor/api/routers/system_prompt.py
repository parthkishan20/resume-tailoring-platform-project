# backend/src/resumetailor/api/routers/system_prompt.py
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from resumetailor.core.config import get_settings
from resumetailor.database import (
    get_system_prompt,
    upsert_system_prompt,
    reset_system_prompt,
)

router = APIRouter()


def _db_path():
    return get_settings().DB_PATH


class SystemPromptBody(BaseModel):
    content: str


@router.get("/api/system-prompt")
async def get():
    row = await asyncio.to_thread(get_system_prompt, _db_path())
    if row is None:
        raise HTTPException(status_code=404, detail="System prompt not found")
    return row


@router.put("/api/system-prompt")
async def update(body: SystemPromptBody):
    return await asyncio.to_thread(upsert_system_prompt, _db_path(), body.content)


@router.delete("/api/system-prompt")
async def reset():
    return await asyncio.to_thread(reset_system_prompt, _db_path())
