# backend/src/resumetailor/api/routers/llm_usage.py
"""The rate-limit counter the frontend polls next to the assistant.

Read-only and cheap (one indexed count query): the actual limit is enforced
by the provider, not here (see `db/repositories/llm_requests.py`'s module
docstring for the "day" window's definition).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from resumetailor.api.schemas.llm_usage import LLMUsageResponse
from resumetailor.core.config import get_settings
from resumetailor.db.repositories import get_llm_request_counts

router = APIRouter()


@router.get("/api/llm/usage", response_model=LLMUsageResponse)
async def get_usage() -> LLMUsageResponse:
    settings = get_settings()
    minute_count, day_count = await asyncio.to_thread(
        get_llm_request_counts, settings.DB_PATH
    )
    return LLMUsageResponse(
        minute_count=minute_count,
        minute_limit=settings.LLM_RATE_LIMIT_PER_MINUTE,
        day_count=day_count,
        day_limit=settings.LLM_RATE_LIMIT_PER_DAY,
    )
