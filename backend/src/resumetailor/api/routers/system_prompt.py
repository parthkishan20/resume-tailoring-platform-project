# backend/src/resumetailor/api/routers/system_prompt.py
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from resumetailor.api.schemas.errors import error_responses
from resumetailor.core.config import get_settings
from resumetailor.core.security import MAX_SYSTEM_PROMPT_CHARS
from resumetailor.db.models import SystemPrompt
from resumetailor.db.repositories import (
    get_system_prompt,
    upsert_system_prompt,
    reset_system_prompt,
)

router = APIRouter()


def _db_path():
    return get_settings().DB_PATH


class SystemPromptBody(BaseModel):
    content: str = Field(max_length=MAX_SYSTEM_PROMPT_CHARS)


@router.get(
    "/api/system-prompt",
    response_model=SystemPrompt,
    responses=error_responses(404),
)
async def get():
    row = await asyncio.to_thread(get_system_prompt, _db_path())
    if row is None:
        raise HTTPException(status_code=404, detail="System prompt not found")
    return row


@router.put(
    "/api/system-prompt",
    response_model=SystemPrompt,
    responses=error_responses(413, 422),
)
async def update(body: SystemPromptBody):
    return await asyncio.to_thread(upsert_system_prompt, _db_path(), body.content)


@router.delete("/api/system-prompt", response_model=SystemPrompt)
async def reset():
    """Reset to the default system prompt. 200 with the new state (D-58).

    Same convention as `rules.py::reset`: this row still exists after the
    call, with a new value, so the response is 200 and the body, not 204.
    """
    return await asyncio.to_thread(reset_system_prompt, _db_path())
