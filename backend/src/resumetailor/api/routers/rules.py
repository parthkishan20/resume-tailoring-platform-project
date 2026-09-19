# backend/src/resumetailor/api/routers/rules.py
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel, Field
from resumetailor.api.schemas.errors import error_responses
from resumetailor.core.config import get_settings
from resumetailor.db.models import GenerationRule
from resumetailor.db.repositories import get_rules, upsert_rules, reset_rules

router = APIRouter()

# D-70: the same class of gap D-69 closed on `resumes.py`. 200 per field
# matches `_RuleArg` in `domain/assistant.py`, which already bounds the
# assistant's own rule-editing tool this way so a model-authored rule list is
# not a way around a limit this HTTP route lacked -- these three fields are
# short labels, not documents, so none of the four `MAX_*_CHARS` in
# `core/security.py` fit. 50 for the list matches
# `_UpdateGenerationRulesArgs.rules` there too: `DEFAULT_RULES` seeds 12, so
# 50 is a generous multiple of the realistic case.
MAX_RULE_FIELD_CHARS = 200
MAX_RULES_PER_REQUEST = 50


def _db_path():
    return get_settings().DB_PATH


class RuleItem(BaseModel):
    section: str = Field(max_length=MAX_RULE_FIELD_CHARS)
    rule_key: str = Field(max_length=MAX_RULE_FIELD_CHARS)
    rule_value: str = Field(max_length=MAX_RULE_FIELD_CHARS)


class RulesBody(BaseModel):
    rules: list[RuleItem] = Field(max_length=MAX_RULES_PER_REQUEST)


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
