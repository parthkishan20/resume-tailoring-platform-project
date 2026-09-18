# backend/src/resumetailor/api/routers/rules.py
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from resumetailor.api.schemas.errors import error_responses
from resumetailor.core.config import get_settings
from resumetailor.db.models import GenerationRule
from resumetailor.db.repositories import get_rules, upsert_rules, reset_rules

router = APIRouter()


def _db_path():
    return get_settings().DB_PATH


class RuleItem(BaseModel):
    section: str
    rule_key: str
    rule_value: str


class RulesBody(BaseModel):
    rules: list[RuleItem]


@router.get("/api/rules", response_model=list[GenerationRule])
async def get():
    return await asyncio.to_thread(get_rules, _db_path())


@router.put(
    "/api/rules",
    response_model=list[GenerationRule],
    responses=error_responses(413, 422),
)
async def update(body: RulesBody):
    return await asyncio.to_thread(
        upsert_rules, _db_path(), [r.model_dump() for r in body.rules]
    )


@router.delete("/api/rules", response_model=list[GenerationRule])
async def reset():
    """Reset to the default rules. 200 with the new state, not 204 (D-58).

    This is a reset, not a delete: `generation_rules` still exists and is
    non-empty afterwards, so returning 204 would say "gone" about a resource
    that immediately has a new value the caller has to re-fetch to see. See
    `system_prompt.py::reset` (the other one) and
    `docs/adr/0007-delete-verb-status-code-convention.md`.
    """
    return await asyncio.to_thread(reset_rules, _db_path())
