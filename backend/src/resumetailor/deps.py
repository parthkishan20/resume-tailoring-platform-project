# backend/src/resumetailor/deps.py
#
# MOVED BY TASK 2.2 to api/deps.py (PLAN.md section 3.2). Left at the package
# root by 1.1 because every router imports it and 1.3 rewrites those imports
# anyway.
from functools import lru_cache
from resumetailor.backend_api import BackendAPI, create_real_backend
from resumetailor.core.config import get_settings


@lru_cache(maxsize=1)
def _backend() -> BackendAPI:
    settings = get_settings()
    if settings.LLM_MOCK:
        from resumetailor.simulator import SimulatedBackendAPI
        return SimulatedBackendAPI()
    return create_real_backend()


def get_backend() -> BackendAPI:
    return _backend()
