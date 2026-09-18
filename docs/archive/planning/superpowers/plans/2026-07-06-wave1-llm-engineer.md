# LLM Engineer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the port protocols, LiteLLM/rendercv/PyMuPDF adapters, both simulator tiers, the LLM prompts, and the mock PDF fixture the rest of the system depends on.

**Architecture:** Three `typing.Protocol` ports (`LLMPort`, `PDFRenderPort`, `PDFExtractPort`) backed by real adapters and two simulation tiers. Tier 1 (`SimulatedBackendAPI`) is activated by `LLM_MOCK=true` for E2E tests. Tier 2 (`ConfigurableBackendAPI`) is used by unit tests for individual route handlers.

**Tech Stack:** Python 3.12 stdlib + litellm + rendercv + pymupdf (adapters only). Tests use pytest.

## Global Constraints

- Reference docs: `planning/backendAPI_interface.md`, `planning/backend_simulator.md`, `planning/backend_API.md`, `planning/example-Prompt.md`
- The `backend_API.md` doc notes that rendercv v2.x uses **Typst** (pip dep), NOT LaTeX — adapters must use the CLI subprocess approach
- `mock.pdf` fixture is a minimal valid PDF created with pure Python (no external tool needed)
- Tier 1 `SimulatedBackendAPI` constants (`MOCK_CHAT_RESULT`, etc.) must match PLAN.md §11 **exactly** — Integration Tester imports and asserts against them
- All adapter errors map to domain exceptions defined in `ports.py`

---

## File Structure

```
backend/
├── app/
│   ├── ports.py            CREATE — protocols + exception hierarchy
│   ├── adapters.py         CREATE — LiteLLMAdapter, RenderCVAdapter, PyMuPDFAdapter
│   ├── simulator.py        CREATE — SimulatedBackendAPI (Tier 1)
│   └── prompts.py          CREATE — GENERATION_SYSTEM_PROMPT, CRITIQUE_SYSTEM_PROMPT
└── tests/
    ├── fixtures/
    │   └── mock.pdf        CREATE — minimal valid PDF (pure Python)
    ├── helpers/
    │   ├── __init__.py     CREATE — empty
    │   └── simulator.py    CREATE — ConfigurableBackendAPI + Simulated*Port (Tier 2)
    └── test_llm.py         CREATE — pytest unit tests
```

---

## Task 1: Port Protocols and Exception Hierarchy

**Files:**
- Create: `backend/app/ports.py`
- Create: `backend/tests/test_llm.py` (partial)

**Interfaces:**
- Produces: `LLMPort`, `PDFRenderPort`, `PDFExtractPort` protocols; `BackendError`, `LLMAuthError`, `LLMUnavailableError`, `RenderError`, `PDFExtractError` exceptions

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_llm.py
from app.ports import (
    LLMPort, PDFRenderPort, PDFExtractPort,
    LLMAuthError, LLMUnavailableError, RenderError, PDFExtractError, BackendError,
)


def test_exception_hierarchy():
    assert issubclass(LLMAuthError, BackendError)
    assert issubclass(LLMUnavailableError, BackendError)
    assert issubclass(RenderError, BackendError)
    assert issubclass(PDFExtractError, BackendError)


def test_llm_port_is_protocol():
    from typing import runtime_checkable, Protocol
    assert issubclass(LLMPort, Protocol)


def test_ports_are_runtime_checkable():
    # A class with the right shape satisfies the protocol
    class FakeLLM:
        async def complete(self, messages, response_format=None):
            return ""
        async def stream(self, messages):
            yield ""
    assert isinstance(FakeLLM(), LLMPort)
```

- [ ] **Step 2: Run — expect failure**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/backend
pip install pytest --quiet
python -m pytest tests/test_llm.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement ports.py**

```python
# backend/app/ports.py
from __future__ import annotations
from typing import AsyncIterator, Protocol, runtime_checkable


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


@runtime_checkable
class LLMPort(Protocol):
    async def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str: ...

    async def stream(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class PDFRenderPort(Protocol):
    async def render(self, yaml_content: str) -> bytes: ...


@runtime_checkable
class PDFExtractPort(Protocol):
    async def extract(self, pdf_bytes: bytes) -> str: ...
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_llm.py -v -k "port or exception or hierarchy"
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/ports.py backend/tests/test_llm.py
git commit -m "feat(llm): port protocols and exception hierarchy"
```

---

## Task 2: Real Adapters

**Files:**
- Create: `backend/app/adapters.py`
- Modify: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `LiteLLMAdapter(model, api_key)`, `RenderCVAdapter()`, `PyMuPDFAdapter()`
- Note: adapter unit tests only verify error mapping (no real LLM/PDF calls)

- [ ] **Step 1: Write failing tests for error mapping**

Add to `backend/tests/test_llm.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.ports import LLMAuthError, LLMUnavailableError, RenderError
from app.adapters import LiteLLMAdapter


@pytest.mark.asyncio
async def test_litellm_adapter_maps_auth_error():
    import litellm.exceptions as llm_exc
    adapter = LiteLLMAdapter(model="openrouter/test/model", api_key="key")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = llm_exc.AuthenticationError(
            "bad key", llm_provider="openrouter", model="test"
        )
        with pytest.raises(LLMAuthError):
            await adapter.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_litellm_adapter_maps_rate_limit_to_unavailable():
    import litellm.exceptions as llm_exc
    adapter = LiteLLMAdapter(model="openrouter/test/model", api_key="key")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = llm_exc.RateLimitError(
            "rate limited", llm_provider="openrouter", model="test"
        )
        with pytest.raises(LLMUnavailableError):
            await adapter.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_rendercv_adapter_maps_nonzero_exit_to_render_error():
    from app.adapters import RenderCVAdapter
    adapter = RenderCVAdapter()
    proc_mock = MagicMock()
    proc_mock.returncode = 1
    proc_mock.communicate = AsyncMock(return_value=(b"", b"YAML error"))
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with pytest.raises(RenderError):
            await adapter.render("bad: yaml")
```

- [ ] **Step 2: Run — expect failure**

```bash
pip install pytest-asyncio litellm rendercv pymupdf --quiet
python -m pytest tests/test_llm.py -v -k "adapter" 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.adapters'`

- [ ] **Step 3: Implement adapters.py**

```python
# backend/app/adapters.py
from __future__ import annotations
import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator

import litellm
import litellm.exceptions as llm_exc

from .ports import LLMAuthError, LLMUnavailableError, PDFExtractError, RenderError

_LLM_UNAVAILABLE = (
    llm_exc.RateLimitError,
    llm_exc.ServiceUnavailableError,
    llm_exc.APIConnectionError,
)


class LiteLLMAdapter:
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        os.environ["OPENROUTER_API_KEY"] = api_key

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        kwargs: dict = {"model": self._model, "messages": messages}
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content
        except llm_exc.AuthenticationError as exc:
            raise LLMAuthError("Invalid OpenRouter API key") from exc
        except _LLM_UNAVAILABLE as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        try:
            response = await litellm.acompletion(
                model=self._model, messages=messages, stream=True
            )
        except llm_exc.AuthenticationError as exc:
            raise LLMAuthError("Invalid OpenRouter API key") from exc
        except _LLM_UNAVAILABLE as exc:
            raise LLMUnavailableError(str(exc)) from exc
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class RenderCVAdapter:
    async def render(self, yaml_content: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            yaml_path = tmpdir_path / "resume.yaml"
            pdf_path = tmpdir_path / "resume.pdf"
            yaml_path.write_text(yaml_content, encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                "rendercv", "render", str(yaml_path),
                "--pdf-path", str(pdf_path),
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


class PyMuPDFAdapter:
    _MAX_BYTES = 10 * 1024 * 1024
    _MAX_PAGES = 50

    async def extract(self, pdf_bytes: bytes) -> str:
        if len(pdf_bytes) > self._MAX_BYTES:
            raise ValueError(
                f"PDF exceeds 10 MB limit ({len(pdf_bytes) / 1_048_576:.1f} MB)"
            )
        try:
            import pymupdf
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PDFExtractError(f"Cannot open PDF: {exc}") from exc
        if doc.page_count > self._MAX_PAGES:
            doc.close()
            raise ValueError(f"PDF has {doc.page_count} pages (max {self._MAX_PAGES})")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages)
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest tests/test_llm.py -v -k "adapter"
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters.py backend/tests/test_llm.py
git commit -m "feat(llm): LiteLLM, rendercv, PyMuPDF adapters with error mapping"
```

---

## Task 3: Mock PDF Fixture + Tier 1 Simulator

**Files:**
- Create: `backend/tests/fixtures/mock.pdf`
- Create: `backend/tests/fixtures/__init__.py`
- Create: `backend/app/simulator.py`
- Modify: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `MOCK_CHAT_RESULT`, `MOCK_GENERATION_RESULT_YAML`, `MOCK_EVALUATION_RESULT`, `MOCK_IMPORT_YAML` constants (imported by Integration Tester for assertions); `SimulatedBackendAPI` class

- [ ] **Step 1: Create the mock PDF fixture**

Write this Python script and run it once:

```python
# Run: python create_mock_pdf.py (from backend/ directory)
from pathlib import Path

# Minimal valid PDF — a blank single-page document
MOCK_PDF = b"""%PDF-1.4
1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj
2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj
3 0 obj<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>endobj
xref
0 4
0000000000 65535 f\r
0000000009 00000 n\r
0000000058 00000 n\r
0000000115 00000 n\r
trailer<</Size 4 /Root 1 0 R>>
startxref
190
%%EOF"""

out = Path("tests/fixtures/mock.pdf")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(MOCK_PDF)
print(f"Created {out} ({len(MOCK_PDF)} bytes)")
```

Run it, then delete the script:

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/backend
python create_mock_pdf.py
rm create_mock_pdf.py
touch tests/fixtures/__init__.py
```

- [ ] **Step 2: Write failing tests for Tier 1 simulator**

Add to `backend/tests/test_llm.py`:

```python
import asyncio
import json
from app.simulator import (
    SimulatedBackendAPI,
    MOCK_CHAT_RESULT,
    MOCK_GENERATION_RESULT_YAML,
    MOCK_EVALUATION_RESULT,
    MOCK_IMPORT_YAML,
)


def test_mock_constants_match_plan():
    assert MOCK_EVALUATION_RESULT["match_score"] == 72
    assert "Kubernetes" in MOCK_EVALUATION_RESULT["missing_keywords"]
    assert "Python" in MOCK_EVALUATION_RESULT["matched_keywords"]
    assert MOCK_CHAT_RESULT["action"] is None
    assert "cv:" in MOCK_GENERATION_RESULT_YAML
    assert MOCK_IMPORT_YAML == MOCK_GENERATION_RESULT_YAML


@pytest.mark.asyncio
async def test_simulator_stream_yields_chat_result():
    sim = SimulatedBackendAPI()
    chunks = []
    async for chunk in await sim.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)
    assert len(chunks) > 0
    combined = "".join(chunks)
    parsed = json.loads(combined)
    assert parsed == MOCK_CHAT_RESULT


@pytest.mark.asyncio
async def test_simulator_render_returns_pdf_bytes():
    sim = SimulatedBackendAPI()
    pdf = await sim.render("cv:\n  name: Test")
    assert pdf[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_simulator_extract_returns_text():
    sim = SimulatedBackendAPI()
    text = await sim.extract(b"%PDF-1.4 fake")
    assert "Mock" in text
```

- [ ] **Step 3: Run — expect failure**

```bash
python -m pytest tests/test_llm.py -v -k "simulator or mock_constant" 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.simulator'`

- [ ] **Step 4: Implement simulator.py**

```python
# backend/app/simulator.py
from __future__ import annotations
import json
from pathlib import Path
from typing import AsyncIterator

_FIXTURE_PDF = Path(__file__).parent.parent / "tests" / "fixtures" / "mock.pdf"

# ── Tier 1 constants (PLAN.md §11) ─────────────────────────────────────────

MOCK_CHAT_RESULT: dict = {
    "text": (
        "I understand. Here's what I can help you with: editing your master resume, "
        "generating a tailored resume, or evaluating a resume against a job description."
    ),
    "action": None,
}

MOCK_GENERATION_RESULT_YAML: str = """\
cv:
  name: Mock User
  email: mock@example.com
  phone: "+10000000000"
  location: Mock City, MC
  sections:
    education:
    - institution: Mock University
      area: Computer Science
      degree: Bachelor
      start_date: 2018-09
      end_date: 2022-05
    experience:
    - company: Mock Corp
      position: Software Engineer
      start_date: 2022-06
      end_date: present
      location: Mock City, MC
      highlights:
      - Built mock features using Python and React.
      - Deployed mock services with Docker and CI/CD pipelines.
      - Reduced mock latency by 30 percent through query optimization.
      - Collaborated with mock teams to deliver mock roadmap items.
    skills:
    - label: Languages
      details: Python, TypeScript, SQL
    - label: Tools
      details: Docker, Git, FastAPI, React
"""

MOCK_EVALUATION_RESULT: dict = {
    "match_score": 72,
    "critique": (
        "The resume covers most required skills but lacks explicit mention of "
        "Kubernetes and CI/CD pipelines listed in the job description."
    ),
    "matched_keywords": ["Python", "REST API", "PostgreSQL"],
    "missing_keywords": ["Kubernetes", "CI/CD", "Docker Compose"],
}

MOCK_IMPORT_YAML: str = MOCK_GENERATION_RESULT_YAML

MOCK_GENERATION_PROGRESS: list[str] = [
    "Analyzing job description...",
    "Tailoring content...",
    "Rendering PDF...",
]


# ── Tier 1: SimulatedBackendAPI ─────────────────────────────────────────────

class SimulatedBackendAPI:
    """Deterministic E2E mock. Activated when LLM_MOCK=true."""

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        system = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        if "ResumeTailor" in system:
            if response_format:
                return json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML})
            return MOCK_GENERATION_RESULT_YAML
        if "ResumeAuditor" in system:
            user_content = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            start = user_content.find("cv:")
            return user_content[start:] if start != -1 else MOCK_GENERATION_RESULT_YAML
        if "evaluation" in system.lower():
            return json.dumps(MOCK_EVALUATION_RESULT)
        # PDF import or chat
        return json.dumps(MOCK_CHAT_RESULT)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        yield json.dumps(MOCK_CHAT_RESULT)

    async def render(self, yaml_content: str) -> bytes:
        return _FIXTURE_PDF.read_bytes()

    async def extract(self, pdf_bytes: bytes) -> str:
        return (
            "John Mock\nmock@example.com\n+10000000000\nMock City, MC\n\n"
            "EDUCATION\nMock University — B.S. Computer Science, 2018–2022\n\n"
            "EXPERIENCE\nMock Corp — Software Engineer, 2022–present\n"
            "  • Built mock features using Python and React\n"
            "  • Deployed mock services with Docker\n\n"
            "SKILLS\nPython, TypeScript, React, Docker, Git, FastAPI, SQL"
        )
```

- [ ] **Step 5: Run — expect pass**

```bash
python -m pytest tests/test_llm.py -v -k "simulator or mock_constant"
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/simulator.py backend/tests/fixtures/ backend/tests/test_llm.py
git commit -m "feat(llm): Tier 1 SimulatedBackendAPI and mock PDF fixture"
```

---

## Task 4: Tier 2 Configurable Simulator

**Files:**
- Create: `backend/tests/helpers/__init__.py`
- Create: `backend/tests/helpers/simulator.py`
- Modify: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `SimulatedLLMPort`, `SimulatedPDFRenderPort`, `SimulatedPDFExtractPort`, `ConfigurableBackendAPI` — consumed by Backend API Engineer's route unit tests

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_llm.py`:

```python
@pytest.mark.asyncio
async def test_configurable_backend_llm_complete():
    from tests.helpers.simulator import ConfigurableBackendAPI
    api = ConfigurableBackendAPI()
    api.sim_llm.set_complete_response("hello world")
    result = await api.complete([{"role": "user", "content": "hi"}])
    assert result == "hello world"
    assert api.sim_llm.complete_call_count == 1


@pytest.mark.asyncio
async def test_configurable_backend_llm_error():
    from tests.helpers.simulator import ConfigurableBackendAPI
    from app.ports import LLMUnavailableError
    api = ConfigurableBackendAPI()
    api.sim_llm.set_complete_error(LLMUnavailableError("down"))
    with pytest.raises(LLMUnavailableError):
        await api.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_configurable_backend_render_error():
    from tests.helpers.simulator import ConfigurableBackendAPI
    from app.ports import RenderError
    api = ConfigurableBackendAPI()
    api.sim_pdf_render.set_error(RenderError("bad yaml"))
    with pytest.raises(RenderError):
        await api.render("bad yaml")
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest tests/test_llm.py -v -k "configurable" 2>&1 | head -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create helpers package and simulator**

`backend/tests/helpers/__init__.py` — empty file.

```python
# backend/tests/helpers/simulator.py
from __future__ import annotations
from typing import AsyncIterator

from app.backend_api import BackendAPI


class SimulatedLLMPort:
    def __init__(self) -> None:
        self._complete_response: str = ""
        self._complete_error: Exception | None = None
        self._stream_chunks: list[str] = []
        self._stream_error: Exception | None = None
        self.complete_call_count: int = 0
        self.stream_call_count: int = 0
        self.last_complete_messages: list[dict] | None = None
        self.last_stream_messages: list[dict] | None = None

    def set_complete_response(self, response: str) -> None:
        self._complete_response = response
        self._complete_error = None

    def set_complete_error(self, exc: Exception) -> None:
        self._complete_error = exc

    def set_stream_chunks(self, chunks: list[str]) -> None:
        self._stream_chunks = chunks
        self._stream_error = None

    def set_stream_error(self, exc: Exception) -> None:
        self._stream_error = exc

    async def complete(self, messages: list[dict], response_format: dict | None = None) -> str:
        self.complete_call_count += 1
        self.last_complete_messages = messages
        if self._complete_error:
            raise self._complete_error
        return self._complete_response

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        self.stream_call_count += 1
        self.last_stream_messages = messages
        if self._stream_error:
            raise self._stream_error
        for chunk in self._stream_chunks:
            yield chunk


class SimulatedPDFRenderPort:
    def __init__(self) -> None:
        self._response: bytes = b"%PDF-1.4 mock"
        self._error: Exception | None = None
        self.call_count: int = 0
        self.last_yaml_content: str | None = None

    def set_response(self, pdf_bytes: bytes) -> None:
        self._response = pdf_bytes
        self._error = None

    def set_error(self, exc: Exception) -> None:
        self._error = exc

    async def render(self, yaml_content: str) -> bytes:
        self.call_count += 1
        self.last_yaml_content = yaml_content
        if self._error:
            raise self._error
        return self._response


class SimulatedPDFExtractPort:
    def __init__(self) -> None:
        self._response: str = "Mock resume text"
        self._error: Exception | None = None
        self.call_count: int = 0
        self.last_pdf_bytes: bytes | None = None

    def set_response(self, text: str) -> None:
        self._response = text
        self._error = None

    def set_error(self, exc: Exception) -> None:
        self._error = exc

    async def extract(self, pdf_bytes: bytes) -> str:
        self.call_count += 1
        self.last_pdf_bytes = pdf_bytes
        if self._error:
            raise self._error
        return self._response


class ConfigurableBackendAPI(BackendAPI):
    """Tier 2 per-port configurable simulator for unit tests."""

    def __init__(self) -> None:
        self.sim_llm = SimulatedLLMPort()
        self.sim_pdf_render = SimulatedPDFRenderPort()
        self.sim_pdf_extract = SimulatedPDFExtractPort()
        super().__init__(
            llm=self.sim_llm,
            pdf_render=self.sim_pdf_render,
            pdf_extract=self.sim_pdf_extract,
        )
```

Note: `ConfigurableBackendAPI` imports `BackendAPI` from `app.backend_api` — that module is created by the Backend API Engineer in Wave 2. This file will have an import error until Wave 2 is complete. That is expected — these helpers are used by Wave 2 route tests.

- [ ] **Step 4: Run the tests that don't need BackendAPI**

```bash
python -m pytest tests/test_llm.py -v -k "not configurable"
```

Expected: all non-configurable tests PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/tests/helpers/ backend/tests/test_llm.py
git commit -m "feat(llm): Tier 2 ConfigurableBackendAPI simulator — Wave 1 LLM complete"
```

---

## Task 5: LLM Prompts

**Files:**
- Create: `backend/app/prompts.py`

**Interfaces:**
- Produces: `GENERATION_SYSTEM_PROMPT: str`, `CRITIQUE_SYSTEM_PROMPT: str`
- These are imported by route handlers in Wave 2

- [ ] **Step 1: Create prompts.py**

Copy exactly from `planning/example-Prompt.md`:

```python
# backend/app/prompts.py
GENERATION_SYSTEM_PROMPT = """\
You are ResumeTailor-v2, an expert ATS-optimization and resume rewriting system.


ROLE & MISSION


Your job: produce a tailored resume YAML in RenderCV format that:
1. Maximizes relevance to the job description (JD) using only content from the master resume.
2. Passes ATS screening by mirroring the JD's exact terminology and keyword patterns.
3. Satisfies all structural, formatting, and anti-hallucination rules below.


STEP 1 — READ & EXTRACT (internal reasoning, do not output)


Before writing any YAML, silently complete these four steps:

A. Extract the top 10 keywords/tech/tools from the JD. Note which are exact-match vs semantic.
B. Rank all experiences and projects by relevance to those keywords (1=highest).
C. Identify which master-resume bullets naturally contain those keywords.
D. Flag which bullets will need rewording to mirror JD terminology exactly.


STEP 2 — STRICT CONTENT RULES


 EXPERIENCE (work)
  - Select up to 2 entries. Use fewer only if relevance is genuinely low.
  - Exactly 4 bullet points per entry (no more, no fewer).
  - Sort bullets by relevance to JD (most relevant first).
  - Reword bullets to mirror exact JD terminology (e.g. if JD says "Next.js", use "Next.js").

 PROJECTS
  - Select up to 3 most relevant projects.
  - Exactly 3 bullet points per project (no more, no fewer).
  - Sort by relevance. Omit projects with no meaningful overlap with JD.

 SKILLS
  - Select 15–20 individual skills. Count each skill separately.
  - Organize into 2–4 labeled groups that match the JD's domain.
  - Each group uses the format:
      - label: "Frontend"
        details: "React, TypeScript, Next.js, Tailwind CSS, Redux Toolkit"
  - First group must contain the JD's most prominent technical keywords.
  - Prefer exact JD terminology over synonyms.

 CERTIFICATIONS
  - Keep 1–2 most relevant. Omit all others.
  - If none are relevant, omit the section entirely.

 EXTRA ACTIVITIES
  - Include 0–1 items only if genuinely impactful for this role.
  - Omit if irrelevant.

 EDUCATION
  - Copy verbatim from master resume. Do NOT modify institution, degree, dates, GPA, or highlights.

 CONTACT / HEADER
  - Copy verbatim: name, email, phone, location, website, social_networks.
  - Do NOT add, remove, or reorder these fields.
  - Leave the headline field commented out or absent (do not generate one).


STEP 3 — ANTI-HALLUCINATION RULES (ABSOLUTE)


You may ONLY:
   Reorder words and clauses within a bullet
   Substitute synonyms from the JD for equivalent terms in the original
   Trim filler phrases to make room for JD keywords
   Emphasize a subset of the original bullet's content

You may NEVER:
   Add a metric, percentage, or number not present in the original bullet
   Claim a technology or tool not mentioned in the original bullet
   Fabricate an outcome, result, or scope not present in the original
   Merge content from two different bullets into one
   Copy content from one experience/project into a different one


STEP 4 — BULLET POINT RULES (MANDATORY — USE CHARACTER COUNT SCRATCHPAD)


For EVERY bullet point, before writing it into the YAML, do this silently:

  DRAFT the bullet → COUNT characters → TRIM if >120 → VERIFY count ≤120 → WRITE

Rules:
  - Hard limit: ≤120 characters. NEVER exceed this.
  - Target: 105–118 characters. This is the sweet spot.
  - Must start with a past-tense action verb (Built, Engineered, Designed, etc.).
  - Must contain at least one measurable or specific claim from the original.
  - Must mirror at least one keyword from the JD if present in the original bullet.
  - No filler: avoid "Worked on", "Responsible for", "Helped to", "Various".
  - No redundancy: each bullet in an entry should cover a different capability.


STEP 5 — ATS KEYWORD STRATEGY


- Mirror the JD's exact terminology. If JD says "Next.js" use "Next.js", not "NextJS".
- Keyword priority order: technologies > frameworks > methodologies > outcomes.
- Spread keywords across experience, projects, AND skills — do not cluster in one section.
- Keyword density: aim for 60–70% of JD's major keywords appearing at least once.
- Do NOT stuff: each keyword should appear naturally within a meaningful sentence.


OUTPUT FORMAT — CRITICAL


- Output ONLY valid YAML. No markdown fences. No explanations. No comments.
- First line must be: cv:
- Last line must be the final YAML value. No trailing text.
- YAML must parse cleanly with yaml.safe_load().
- Use 2-space indentation throughout. Strings with special chars must be quoted.
- Multi-line bullets must use YAML block scalar (|-) or be single-line strings.
"""

CRITIQUE_SYSTEM_PROMPT = """\
You are ResumeAuditor-v2, an expert resume quality auditor with deep ATS knowledge.

You will receive:
  1. A DRAFT tailored resume YAML (generated by another AI system)
  2. The original master resume (source of truth)
  3. The job description

Your job: audit the draft against the rubric below, then output a CORRECTED final YAML.


AUDIT RUBRIC — CHECK EVERY ITEM


[STRUCTURE]
 S1  Does every bullet start with a past-tense action verb?
 S2  Does experience have exactly 4 bullets per entry? (not 3, not 5)
 S3  Does each project have exactly 3 bullets per entry?
 S4  Are there 15–20 skills total across all skill groups?
 S5  Is education copied verbatim (no modifications)?
 S6  Is contact info identical to master resume?

[LENGTH]
 L1  Is every bullet ≤120 characters? Count each one. Fix any that exceed.
 L2  Is every bullet ≥85 characters? (too-short bullets waste space)
 L3  Are bullets targeting the 105–118 character sweet spot?

[HALLUCINATION CHECK]
 H1  Do any bullets contain metrics, percentages, or numbers NOT in the master resume?
      → If yes: remove them or replace with the original value.
 H2  Do any bullets claim technologies NOT mentioned in the corresponding master resume entry?
      → If yes: remove those technology claims.
 H3  Is any content copied from one experience into a different one?
      → If yes: restore original boundaries.

[ATS / KEYWORDS]
 A1  Are the JD's top 5 keywords present in the output? List which are missing.
 A2  Is JD terminology mirrored exactly? (e.g. "Next.js" not "NextJS")
 A3  Are keywords spread across experience, projects, AND skills?

[SKILLS FORMAT]
 K1  Are skills organized into labeled groups (not one flat list)?
 K2  Does the first skill group lead with the JD's primary technical keywords?


OUTPUT INSTRUCTIONS


First: write a brief audit summary in this exact format (this will be stripped by the system):
  AUDIT_START
  [S1] PASS/FAIL — note
  [S2] PASS/FAIL — note
  ... (only include items that FAIL or need attention)
  Issues found: N
  AUDIT_END

Then: output the corrected final YAML.
  - If 0 issues: output the draft unchanged.
  - If issues found: output the fully corrected version.
  - Output starts immediately after AUDIT_END.
  - No markdown fences. No explanations after the YAML.
  - First YAML line: cv:
"""
```

- [ ] **Step 2: Verify prompts import cleanly**

```bash
python -c "from app.prompts import GENERATION_SYSTEM_PROMPT, CRITIQUE_SYSTEM_PROMPT; print('OK', len(GENERATION_SYSTEM_PROMPT), len(CRITIQUE_SYSTEM_PROMPT))"
```

Expected: `OK <number> <number>` (no error)

- [ ] **Step 3: Commit**

```bash
git add backend/app/prompts.py
git commit -m "feat(llm): generation and critique system prompts — Wave 1 LLM complete"
```

---

**Definition of done:** `python -m pytest backend/tests/test_llm.py -v -k "not configurable"` — all green. `mock.pdf` committed. `prompts.py` imports without error.
