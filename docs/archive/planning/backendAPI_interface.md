# Backend API Interface

Defines the unified Python contract the FastAPI backend uses to interact with all
external libraries (LiteLLM, render-cv, PyMuPDF). Backend route handlers import
`BackendAPI` and never call LiteLLM, render-cv, or PyMuPDF directly.

This allows the simulator (see `backend_simulator.md`) to be swapped in with zero
changes to route code.

---

## Design: Three Ports + One Facade

```
┌─────────────────────────────────────────────────────────┐
│  Route handlers                                         │
│  (only touch BackendAPI)                                │
└────────────────────────┬────────────────────────────────┘
                         │  api.complete() / api.stream()
                         │  api.render()   / api.extract()
                         ▼
┌─────────────────────────────────────────────────────────┐
│  BackendAPI  (facade)                                   │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │  LLMPort     │  │ PDFRenderPort │  │PDFExtractPort│ │
│  └──────┬───────┘  └───────┬───────┘  └──────┬───────┘ │
└─────────┼──────────────────┼─────────────────┼─────────┘
          │                  │                 │
    LiteLLMAdapter     RenderCVAdapter    PyMuPDFAdapter
    (or simulated)     (or simulated)     (or simulated)
```

Route code is simple: one import, flat method calls.  
Tests can swap individual ports by constructing `BackendAPI` with a simulated port.  
The E2E simulator implements the whole facade at once.

---

## Port Protocols

Defined using `typing.Protocol` so implementations need not inherit — structural
subtyping means any class with matching signatures satisfies the protocol.

```python
# backend/app/ports.py  (suggested location; backend agent decides final path)

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMPort(Protocol):
    """Async interface to a large language model."""

    async def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        """Non-streaming completion. Returns the full response text."""
        ...

    async def stream(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]:
        """Streaming completion. Yields string deltas as they arrive."""
        ...


@runtime_checkable
class PDFRenderPort(Protocol):
    """Renders a render-cv YAML string to PDF bytes."""

    async def render(self, yaml_content: str) -> bytes:
        """Returns raw PDF bytes. Raises ValueError on invalid YAML."""
        ...


@runtime_checkable
class PDFExtractPort(Protocol):
    """Extracts plain text from a PDF supplied as bytes."""

    async def extract(self, pdf_bytes: bytes) -> str:
        """Returns plain text. Raises ValueError on oversized or corrupt PDF."""
        ...
```

### Method contracts

| Method | Input | Return | Raises |
|--------|-------|--------|--------|
| `LLMPort.complete` | `messages`, optional `response_format` | Full response string | `LLMUnavailableError`, `LLMAuthError` |
| `LLMPort.stream` | `messages` | `AsyncIterator[str]` of deltas | `LLMUnavailableError`, `LLMAuthError` |
| `PDFRenderPort.render` | render-cv YAML string | Raw PDF bytes | `ValueError` (invalid YAML), `RenderError` |
| `PDFExtractPort.extract` | PDF bytes | Plain text string | `ValueError` (too large / corrupt) |

Define `LLMUnavailableError`, `LLMAuthError`, and `RenderError` as simple subclasses
of `Exception` in the same module so route handlers can catch them by name.

---

## BackendAPI Facade

```python
# backend/app/backend_api.py  (suggested location)

from __future__ import annotations

from typing import AsyncIterator

from .ports import LLMPort, PDFExtractPort, PDFRenderPort


class BackendAPI:
    """Single object that composes all backend capabilities.

    Route handlers receive one BackendAPI instance (e.g., via FastAPI dependency
    injection) and call methods on it directly without knowing which implementations
    are wired in.
    """

    def __init__(
        self,
        llm: LLMPort,
        pdf_render: PDFRenderPort,
        pdf_extract: PDFExtractPort,
    ) -> None:
        self._llm = llm
        self._pdf_render = pdf_render
        self._pdf_extract = pdf_extract

    # --- LLM pass-throughs ---

    async def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        return await self._llm.complete(messages, response_format)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        return await self._llm.stream(messages)

    # --- PDF pass-throughs ---

    async def render(self, yaml_content: str) -> bytes:
        return await self._pdf_render.render(yaml_content)

    async def extract(self, pdf_bytes: bytes) -> str:
        return await self._pdf_extract.extract(pdf_bytes)
```

---

## Real Adapters

### LiteLLMAdapter

```python
from __future__ import annotations

import os
from typing import AsyncIterator

import litellm
import litellm.exceptions as llm_exc

from .ports import LLMUnavailableError, LLMAuthError


class LiteLLMAdapter:
    """Wraps litellm.acompletion for OpenRouter."""

    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        os.environ["OPENROUTER_API_KEY"] = api_key  # litellm reads this env var

    async def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        kwargs: dict = {"model": self._model, "messages": messages}
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content
        except llm_exc.AuthenticationError as exc:
            raise LLMAuthError("Invalid OpenRouter API key") from exc
        except (
            llm_exc.RateLimitError,
            llm_exc.ServiceUnavailableError,
            llm_exc.APIConnectionError,
        ) as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                stream=True,
            )
        except llm_exc.AuthenticationError as exc:
            raise LLMAuthError("Invalid OpenRouter API key") from exc
        except (
            llm_exc.RateLimitError,
            llm_exc.ServiceUnavailableError,
            llm_exc.APIConnectionError,
        ) as exc:
            raise LLMUnavailableError(str(exc)) from exc

        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
```

### RenderCVAdapter

```python
import asyncio
import tempfile
from pathlib import Path

from .ports import RenderError


class RenderCVAdapter:
    """Renders render-cv YAML to PDF via the rendercv CLI subprocess."""

    async def render(self, yaml_content: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            yaml_path   = tmpdir_path / "resume.yaml"
            pdf_path    = tmpdir_path / "resume.pdf"

            yaml_path.write_text(yaml_content, encoding="utf-8")

            proc = await asyncio.create_subprocess_exec(
                "rendercv", "render", str(yaml_path),
                "--pdf-path",              str(pdf_path),
                "--dont-generate-markdown",
                "--dont-generate-html",
                "--dont-generate-png",
                "--dont-generate-typst",
                "--quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RenderError(
                    f"rendercv failed (exit {proc.returncode}): "
                    f"{stderr.decode('utf-8', errors='replace')}"
                )

            return pdf_path.read_bytes()
```

### PyMuPDFAdapter

```python
import pymupdf

from .ports import PDFExtractError


class PyMuPDFAdapter:
    """Extracts plain text from PDF bytes using PyMuPDF."""

    _MAX_BYTES = 10 * 1024 * 1024  # 10 MB  (PLAN.md constraint)
    _MAX_PAGES = 50                # PLAN.md constraint

    async def extract(self, pdf_bytes: bytes) -> str:
        if len(pdf_bytes) > self._MAX_BYTES:
            raise ValueError(
                f"PDF exceeds 10 MB limit ({len(pdf_bytes) / 1_048_576:.1f} MB)"
            )

        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"Cannot open PDF: {exc}") from exc

        if doc.page_count > self._MAX_PAGES:
            doc.close()
            raise ValueError(
                f"PDF has {doc.page_count} pages (max {self._MAX_PAGES})"
            )

        pages: list[str] = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages)
```

---

## Factory: `create_real_backend`

The single wiring point. FastAPI creates one instance at startup and injects it via
a dependency.

```python
# backend/app/backend_api.py  (add to the same file as BackendAPI)

import os

from .adapters import LiteLLMAdapter, PyMuPDFAdapter, RenderCVAdapter


def create_real_backend() -> BackendAPI:
    """Wire real adapters using environment variables."""
    api_key = os.environ["OPENROUTER_API_KEY"]
    model   = os.getenv("LLM_MODEL", "openrouter/openai/gpt-oss-120b:free")

    return BackendAPI(
        llm=LiteLLMAdapter(model=model, api_key=api_key),
        pdf_render=RenderCVAdapter(),
        pdf_extract=PyMuPDFAdapter(),
    )
```

---

## FastAPI Dependency Injection

```python
# backend/app/main.py

from functools import lru_cache
from fastapi import Depends, FastAPI

from .backend_api import BackendAPI, create_real_backend
from .config import settings


app = FastAPI()


@lru_cache(maxsize=1)
def _backend() -> BackendAPI:
    if settings.LLM_MOCK:
        from .simulator import SimulatedBackendAPI
        return SimulatedBackendAPI()
    return create_real_backend()


def get_backend() -> BackendAPI:
    return _backend()


# Route handler example:
@app.post("/api/chat/stream")
async def chat_stream(
    body: ChatRequest,
    api: BackendAPI = Depends(get_backend),
):
    async def event_generator():
        async for delta in await api.stream(body.messages):
            yield f"event: token\ndata: {json.dumps({'delta': delta})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

When `LLM_MOCK=true`, `_backend()` returns a `SimulatedBackendAPI` — routes are
unchanged.

---

## Exception Hierarchy

Define these in `ports.py` alongside the protocols:

```python
class BackendError(Exception):
    """Base for all backend port errors."""


class LLMAuthError(BackendError):
    """Invalid or missing API key."""


class LLMUnavailableError(BackendError):
    """Rate limit, service down, or network failure."""


class RenderError(BackendError):
    """render-cv PDF generation failed."""


class PDFExtractError(BackendError):
    """PyMuPDF could not open or read the PDF."""
```

Map these to HTTP status codes in a FastAPI exception handler:

```python
@app.exception_handler(LLMAuthError)
async def llm_auth_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc), "code": "LLM_AUTH_ERROR"})

@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request, exc):
    return JSONResponse(status_code=503, content={"error": str(exc), "code": "LLM_UNAVAILABLE"})

@app.exception_handler(RenderError)
async def render_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc), "code": "RENDER_FAILED"})
```
