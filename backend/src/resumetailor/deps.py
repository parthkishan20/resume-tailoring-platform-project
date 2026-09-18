# backend/src/resumetailor/deps.py
#
# MOVED BY TASK 2.2 to api/deps.py (PLAN.md section 3.2). Left at the package
# root because every router imports it.
from __future__ import annotations

from functools import lru_cache

from resumetailor.backend_api import BackendAPI, create_real_backend, create_stub_backend
from resumetailor.core.config import get_settings


@lru_cache(maxsize=1)
def _backend() -> BackendAPI:
    settings = get_settings()
    if settings.LLM_MOCK:
        return create_stub_backend()
    return create_real_backend()


def get_backend() -> BackendAPI:
    return _backend()
