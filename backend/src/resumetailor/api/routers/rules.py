# backend/src/resumetailor/api/routers/rules.py
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from resumetailor.core.config import get_settings
from resumetailor.database import get_rules, upsert_rules, reset_rules

router = APIRouter()


def _db_path():
    return get_settings().DB_PATH


class RuleItem(BaseModel):
    section: str
    rule_key: str
    rule_value: str


class RulesBody(BaseModel):
    rules: list[RuleItem]


@router.get("/api/rules")
async def get():
    return await asyncio.to_thread(get_rules, _db_path())


@router.put("/api/rules")
async def update(body: RulesBody):
    return await asyncio.to_thread(
        upsert_rules, _db_path(), [r.model_dump() for r in body.rules]
    )


@router.delete("/api/rules")
async def reset():
    return await asyncio.to_thread(reset_rules, _db_path())
