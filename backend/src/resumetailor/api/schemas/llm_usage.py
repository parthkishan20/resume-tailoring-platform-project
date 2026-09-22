# backend/src/resumetailor/api/schemas/llm_usage.py
"""The rate-limit counter's body. See `db/repositories/llm_requests.py`."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["LLMUsageResponse"]


class LLMUsageResponse(BaseModel):
    """How much of the provider's rate limit this process has used, right now."""

    minute_count: int
    minute_limit: int
    day_count: int
    day_limit: int
