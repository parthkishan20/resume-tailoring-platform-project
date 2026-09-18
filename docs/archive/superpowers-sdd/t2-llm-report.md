# T2 LLM Engineer — Implementation Report

**Date:** 2026-07-06
**Status:** DONE

---

## Summary

All five tasks in `docs/superpowers/plans/2026-07-06-wave1-llm-engineer.md` are implemented, committed, and tested. The Wave 2 Backend API Engineer can import from `app.ports`, `app.adapters`, `app.simulator`, and `app.prompts` without modifications.

---

## Commits

| SHA | Subject |
|-----|---------|
| `3a4b2e0` | feat(llm): port protocols and exception hierarchy |
| `09eee69` | feat(llm): LiteLLM, rendercv, PyMuPDF adapters with error mapping |
| `5fa64c2` | feat(llm): Tier 1 SimulatedBackendAPI and mock PDF fixture |
| `0e3b9cc` | feat(llm): Tier 2 ConfigurableBackendAPI simulator — Wave 1 LLM complete |
| `342d122` | feat(llm): generation and critique system prompts |

---

## Test Summary

```
backend/tests/test_llm.py: 10 passed, 3 skipped (configurable tests await Wave 2)
backend/tests/test_database.py: 26 passed (pre-existing, unaffected)
Total: 36 passed, 3 skipped
```

Run: `cd backend && python -m pytest tests/test_llm.py -v`

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/app/ports.py` | `LLMPort`, `PDFRenderPort`, `PDFExtractPort` Protocol classes; exception hierarchy |
| `backend/app/adapters.py` | `LiteLLMAdapter`, `RenderCVAdapter`, `PyMuPDFAdapter` |
| `backend/app/simulator.py` | `SimulatedBackendAPI` (Tier 1) + 5 exported constants |
| `backend/app/prompts.py` | `GENERATION_SYSTEM_PROMPT`, `CRITIQUE_SYSTEM_PROMPT` |
| `backend/tests/conftest.py` | sys.modules stub for litellm (not installed yet) |
| `backend/tests/fixtures/mock.pdf` | Minimal valid PDF-1.4 (313 bytes, pure Python) |
| `backend/tests/fixtures/__init__.py` | Package marker |
| `backend/tests/helpers/__init__.py` | Package marker |
| `backend/tests/helpers/simulator.py` | `SimulatedLLMPort`, `SimulatedPDFRenderPort`, `SimulatedPDFExtractPort`, `ConfigurableBackendAPI` (Tier 2) |
| `backend/tests/test_llm.py` | Full test suite (13 tests) |

---

## Design Decisions and Deviations

### 1. `@pytest.mark.anyio` instead of `@pytest.mark.asyncio`
`pytest-asyncio` is not installed (and cannot be installed in the sandbox). `anyio` 4.12.0 is installed with a `pytest11` entry point that provides `@pytest.mark.anyio`. All async tests use this decorator and run against the asyncio backend. Wave 2 can add `asyncio_mode = "auto"` in `pyproject.toml` once `pytest-asyncio` is installed, but the tests will work as-is.

### 2. `sys.modules` litellm stub in `conftest.py`
Since `litellm` is not installed, importing `app.adapters` at collection time would fail. `conftest.py` registers a `ModuleType`-based stub with real Python exception subclasses under `sys.modules['litellm']` and `sys.modules['litellm.exceptions']` before any test module is imported. This lets:
- `adapters.py` compile and import cleanly (uses the stub)
- Adapter error-mapping tests raise and catch the stub exceptions correctly
- `patch("litellm.acompletion", ...)` calls work because `litellm.acompletion` is an attribute on the stub module object

When the real `litellm` is installed, `sys.modules.setdefault()` ensures the real module takes precedence on a fresh Python process; the stub only activates when litellm is absent.

### 3. `SimulatedBackendAPI.stream` wraps the async generator
The plan's `async def stream` was a generator (`yield`), but the test does `async for chunk in await sim.stream(...)`. An `async def` generator cannot be `await`ed. The implementation wraps the generator in an inner `async def _gen()` and returns its call result, which is an `AsyncIterable[str]` that the caller iterates with `async for`.

### 4. `ConfigurableBackendAPI` tests skip gracefully
`helpers/simulator.py` has a top-level `from app.backend_api import BackendAPI` that will `ImportError` until Wave 2 creates that module. The three configurable tests wrap the import in `try/except ImportError` and call `pytest.skip(...)` — they appear as `SKIPPED` rather than `ERROR`, which is the correct Wave-1 behavior.

---

## Interface Contract for Wave 2

```python
# Imports Wave 2 Backend API Engineer needs:
from app.ports import LLMPort, PDFRenderPort, PDFExtractPort
from app.ports import BackendError, LLMAuthError, LLMUnavailableError, RenderError, PDFExtractError
from app.adapters import LiteLLMAdapter, RenderCVAdapter, PyMuPDFAdapter
from app.simulator import (
    SimulatedBackendAPI,
    MOCK_CHAT_RESULT,
    MOCK_GENERATION_RESULT_YAML,
    MOCK_EVALUATION_RESULT,
    MOCK_IMPORT_YAML,
    MOCK_GENERATION_PROGRESS,
)
from app.prompts import GENERATION_SYSTEM_PROMPT, CRITIQUE_SYSTEM_PROMPT

# After Wave 2 creates app.backend_api.BackendAPI:
from tests.helpers.simulator import (
    ConfigurableBackendAPI,
    SimulatedLLMPort,
    SimulatedPDFRenderPort,
    SimulatedPDFExtractPort,
)
```

`MOCK_EVALUATION_RESULT["match_score"] == 72` — verified in tests, stable for Integration Tester assertions.

---

## Post-Implementation Fix — 2026-07-06

**Status:** DONE

Three issues identified after initial implementation and resolved in commit `1337355`.

### Issue 1: Top-level litellm imports in adapters.py

`backend/app/adapters.py` had `import litellm` and `import litellm.exceptions as llm_exc` at the module top level, and a module-level `_LLM_UNAVAILABLE` tuple that referenced `llm_exc`. This caused `ImportError` on any `import app.adapters` when litellm is not installed — breaking the "compile without deps" constraint.

**Fix:** Moved both imports and the `_LLM_UNAVAILABLE` tuple (now `_llm_unavailable`, local variable) inside `complete()` and `stream()`. Matching the pattern used by the existing `PyMuPDFAdapter.extract()` lazy import.

### Issue 2: stream() async generator vs awaitable convention mismatch

`LiteLLMAdapter.stream` and `SimulatedLLMPort.stream` were async generators (used `yield`), meaning callers had to write `async for chunk in port.stream(messages)` (no `await`). But `SimulatedBackendAPI.stream` used the `_gen()` wrapper so callers write `async for chunk in await sim.stream(messages)`. Wave 2 route handlers will inject the real adapter and expect the `await` convention.

**Fix:** Applied the `_gen()` wrapper pattern to both `LiteLLMAdapter.stream` and `SimulatedLLMPort.stream`. Each method is now a coroutine returning an async generator; callers use `async for chunk in await port.stream(messages)`.

For `SimulatedLLMPort.stream`, the call_count increment and messages capture happen eagerly (before `_gen()` is returned) so the observable state is set at await-time, not iteration-time.

### Issue 3: __pycache__ bytecode was committed

`backend/tests/helpers/__pycache__/__init__.cpython-313.pyc` and `simulator.cpython-313.pyc` were tracked in git.

**Fix:** `git rm -r --cached backend/tests/helpers/__pycache__/` removed them from tracking. Created `.gitignore` at the repository root covering `__pycache__/`, `*.pyc`, `.venv/`, `.env`, `.pytest_cache/`, `.mypy_cache/`, and other standard Python/macOS artifacts.

### Test Results

```
python -m pytest backend/tests/test_llm.py -v
============================= test session starts ==============================
platform darwin -- Python 3.13.5, pytest-8.4.2, pluggy-1.5.0
plugins: anyio-4.12.0, langsmith-0.4.59, cov-7.0.0
collected 13 items

backend/tests/test_llm.py::test_exception_hierarchy PASSED
backend/tests/test_llm.py::test_llm_port_is_protocol PASSED
backend/tests/test_llm.py::test_ports_are_runtime_checkable PASSED
backend/tests/test_llm.py::test_litellm_adapter_maps_auth_error[asyncio] PASSED
backend/tests/test_llm.py::test_litellm_adapter_maps_rate_limit_to_unavailable[asyncio] PASSED
backend/tests/test_llm.py::test_rendercv_adapter_maps_nonzero_exit_to_render_error[asyncio] PASSED
backend/tests/test_llm.py::test_simulator_stream_yields_chat_result[asyncio] PASSED
backend/tests/test_llm.py::test_simulator_render_returns_pdf_bytes[asyncio] PASSED
backend/tests/test_llm.py::test_simulator_extract_returns_text[asyncio] PASSED
backend/tests/test_llm.py::test_configurable_backend_llm_complete[asyncio] SKIPPED
backend/tests/test_llm.py::test_configurable_backend_llm_error[asyncio] SKIPPED
backend/tests/test_llm.py::test_configurable_backend_render_error[asyncio] SKIPPED
backend/tests/test_llm.py::test_mock_constants_match_plan PASSED

======================== 10 passed, 3 skipped in 0.02s =========================
```

### Commit

`1337355` — fix(llm): lazy litellm imports, stream() awaitable convention, remove __pycache__
