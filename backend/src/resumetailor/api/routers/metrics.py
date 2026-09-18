# backend/src/resumetailor/api/routers/metrics.py
"""`GET /api/metrics`: the Prometheus exposition, unconditionally.

Same trust boundary as every other route (see `core/security.py`'s "On
authentication"): there is no auth model yet (D4/B-03), and metrics is not
material new exposure on a loopback-only, single-user deployment — it is
counts and durations, no request or response content. Gated the same way
`/docs` is (`Settings.API_DOCS_ENABLED`) would be a different lever for a
different audience (operators' scrapers vs. developers' browsers); left
ungated for now and revisited together with D4, same as everything else in
this module's boundary.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/api/metrics", include_in_schema=False)
async def metrics() -> Response:
    """The Prometheus text exposition format. Not JSON, so no `response_model`."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
