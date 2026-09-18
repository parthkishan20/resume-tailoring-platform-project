# backend/src/resumetailor/api/routers/health.py
from fastapi import APIRouter

from resumetailor.api.schemas.health import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}
