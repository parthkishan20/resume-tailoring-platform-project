# Backend Simulator

Documents the two-tier simulation strategy for the `BackendAPI` interface defined in
`backendAPI_interface.md`. Neither tier calls LiteLLM, render-cv, or PyMuPDF.

---

## Why Two Tiers

| | Tier 1 — E2E Mock | Tier 2 — Configurable Simulator |
|---|---|---|
| **Purpose** | E2E / integration tests; `LLM_MOCK=true` | Unit tests for individual route handlers |
| **State** | Stateless, deterministic | Stateful per-port; configurable per-test |
| **Responses** | Fixed, matches PLAN.md §11 exactly | Set per-call via `set_response()` / `set_error()` |
| **Call tracking** | None | `call_count`, `last_call_args` per port |
| **PDF fixture** | Pre-committed static bytes | Configurable bytes |
| **Swapping** | Replaces whole `BackendAPI` | Can replace individual ports |

---

## Tier 1 — `SimulatedBackendAPI` (E2E Mock)

Implements `BackendAPI`'s interface directly. Activated when `LLM_MOCK=true`. Returns
the fixed payloads specified in PLAN.md §11. No configuration surface — every test gets
the same output.

### Fixed response payloads

These match PLAN.md §11 exactly. Define them as module-level constants so the E2E test
assertions have a single import to reference:

```python
# backend/app/simulator.py

MOCK_CHAT_RESULT = {
    "text": (
        "I understand. Here's what I can help you with: editing your master resume, "
        "generating a tailored resume, or evaluating a resume against a job description."
    ),
    "action": None,
}

MOCK_GENERATION_PROGRESS = [
    "Analyzing job description...",
    "Tailoring content...",
    "Rendering PDF...",
]

MOCK_GENERATION_RESULT_YAML = """\
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

MOCK_EVALUATION_RESULT = {
    "match_score": 72,
    "critique": (
        "The resume covers most required skills but lacks explicit mention of "
        "Kubernetes and CI/CD pipelines listed in the job description."
    ),
    "matched_keywords": ["Python", "REST API", "PostgreSQL"],
    "missing_keywords": ["Kubernetes", "CI/CD", "Docker Compose"],
}

MOCK_IMPORT_YAML = MOCK_GENERATION_RESULT_YAML  # same minimal YAML per PLAN.md §11
```

### PDF fixture

Commit a minimal valid PDF to the test fixtures directory. This file is returned by
`SimulatedBackendAPI.render()` without any PDF generation:

```
backend/tests/fixtures/mock.pdf   ← committed static file
```

To create the fixture initially (run once, commit the output):

```bash
# From the backend directory — requires rendercv to be installed
echo "Creating mock PDF fixture..."
python - <<'EOF'
from pathlib import Path
import tempfile, subprocess

yaml = Path("tests/fixtures/mock_resume.yaml")
out  = Path("tests/fixtures/mock.pdf")
yaml.parent.mkdir(parents=True, exist_ok=True)
yaml.write_text("""cv:
  name: Mock User
  email: mock@example.com
  sections:
    education:
    - institution: Mock University
      area: CS
      degree: Bachelor
      start_date: 2020-09
      end_date: 2024-05
""")
subprocess.run(
    ["rendercv", "render", str(yaml), "--pdf-path", str(out),
     "--dont-generate-markdown", "--dont-generate-html",
     "--dont-generate-png", "--dont-generate-typst", "--quiet"],
    check=True,
)
print(f"Fixture written: {out} ({out.stat().st_size} bytes)")
EOF
```

### `SimulatedBackendAPI` class

```python
# backend/app/simulator.py  (continued)

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator


_FIXTURE_PDF = Path(__file__).parent.parent / "tests" / "fixtures" / "mock.pdf"


class SimulatedBackendAPI:
    """Tier 1: deterministic E2E mock. Activated when LLM_MOCK=true.

    Returns the fixed payloads from PLAN.md §11. Stateless — safe to share
    across requests. No external calls.
    """

    # --- LLM ---

    async def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        """Return the appropriate fixed payload based on the system prompt content."""
        system_content = _extract_system_content(messages)

        if "ResumeAuditor" in system_content:
            # Audit pass for generation: return the draft unchanged
            user_content = _extract_user_content(messages)
            draft_start  = user_content.find("cv:")
            return user_content[draft_start:] if draft_start != -1 else MOCK_GENERATION_RESULT_YAML

        if "ResumeTailor" in system_content:
            # Generation pass: return YAML wrapped in the expected JSON schema structure
            if response_format:
                return json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML})
            return MOCK_GENERATION_RESULT_YAML

        if "ResumeAuditor" in system_content or "evaluation" in system_content.lower():
            return json.dumps(MOCK_EVALUATION_RESULT)

        # Chat or PDF import
        return json.dumps(MOCK_CHAT_RESULT)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield the full chat response as a single delta (no real streaming needed)."""
        payload = json.dumps(MOCK_CHAT_RESULT)
        yield payload

    # --- PDF ---

    async def render(self, yaml_content: str) -> bytes:
        """Return the pre-committed fixture PDF."""
        return _FIXTURE_PDF.read_bytes()

    async def extract(self, pdf_bytes: bytes) -> str:
        """Return a fixed sample resume text for LLM import."""
        return (
            "John Mock\nmock@example.com\n+10000000000\nMock City, MC\n\n"
            "EDUCATION\nMock University — B.S. Computer Science, 2018–2022\n\n"
            "EXPERIENCE\nMock Corp — Software Engineer, 2022–present\n"
            "  • Built mock features using Python and React\n"
            "  • Deployed mock services with Docker\n\n"
            "SKILLS\nPython, TypeScript, React, Docker, Git, FastAPI, SQL"
        )


# helpers

def _extract_system_content(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "system":
            return m.get("content", "")
    return ""


def _extract_user_content(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""
```

---

## Tier 2 — `ConfigurableBackendAPI` (Unit Test Simulator)

For unit tests that target individual route handlers. Each port is an independent
`SimulatedPort` object with configurable responses and call history. The facade is
constructed with one simulated port per capability.

### `SimulatedPort` — base building block

```python
# backend/tests/helpers/simulator.py

from __future__ import annotations

from typing import Any, AsyncIterator


class SimulatedLLMPort:
    """Configurable LLM port for unit tests."""

    def __init__(self) -> None:
        self._complete_response: str = ""
        self._complete_error: Exception | None = None
        self._stream_chunks: list[str] = []
        self._stream_error: Exception | None = None
        self.complete_call_count: int = 0
        self.stream_call_count: int = 0
        self.last_complete_messages: list[dict] | None = None
        self.last_complete_response_format: dict | None = None
        self.last_stream_messages: list[dict] | None = None

    def set_complete_response(self, response: str) -> None:
        """Configure what complete() returns on the next call."""
        self._complete_response = response
        self._complete_error = None

    def set_complete_error(self, exc: Exception) -> None:
        """Configure complete() to raise exc on the next call."""
        self._complete_error = exc

    def set_stream_chunks(self, chunks: list[str]) -> None:
        """Configure what stream() yields. Each string is one delta."""
        self._stream_chunks = chunks
        self._stream_error = None

    def set_stream_error(self, exc: Exception) -> None:
        """Configure stream() to raise exc before yielding."""
        self._stream_error = exc

    async def complete(
        self,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        self.complete_call_count += 1
        self.last_complete_messages = messages
        self.last_complete_response_format = response_format
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
    """Configurable PDF render port for unit tests."""

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
    """Configurable PDF extract port for unit tests."""

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
```

### `ConfigurableBackendAPI` — assembles the ports into a facade

```python
# backend/tests/helpers/simulator.py  (continued)

from app.backend_api import BackendAPI


class ConfigurableBackendAPI(BackendAPI):
    """Tier 2: per-port configurable simulator for unit tests.

    Exposes each port publicly so tests can configure and inspect it:

        api = ConfigurableBackendAPI()
        api.sim_llm.set_complete_response('{"yaml_content": "cv: ..."}')
        api.sim_pdf_render.set_error(RenderError("bad yaml"))
    """

    def __init__(self) -> None:
        self.sim_llm        = SimulatedLLMPort()
        self.sim_pdf_render = SimulatedPDFRenderPort()
        self.sim_pdf_extract = SimulatedPDFExtractPort()

        super().__init__(
            llm=self.sim_llm,
            pdf_render=self.sim_pdf_render,
            pdf_extract=self.sim_pdf_extract,
        )
```

---

## Usage Examples

### E2E test — Tier 1

E2E tests set `LLM_MOCK=true` in the environment before the container starts. The
`SimulatedBackendAPI` is wired in automatically via the dependency in `main.py`. No
test-side configuration is needed.

```python
# test/e2e/test_generation.py  (Playwright)

async def test_resume_generation(page):
    await page.goto("http://localhost:8000")

    # Set up master resume (pre-condition)
    await page.fill("[data-testid=yaml-editor]", SAMPLE_YAML)
    await page.click("[data-testid=save-master-resume]")

    # Trigger generation
    await page.fill("[data-testid=job-description]", "Software Engineer at Mock Corp")
    await page.click("[data-testid=generate-button]")

    # Wait for done event
    await page.wait_for_selector("[data-testid=resume-preview]")

    # Assert on the fixed mock name from PLAN.md §11
    title = await page.text_content("[data-testid=resume-name]")
    assert "Mock Resume" in title or "Mock User" in title
```

### Unit test — Tier 2, happy path

```python
# backend/tests/test_chat_route.py

import pytest
from httpx import AsyncClient

from tests.helpers.simulator import ConfigurableBackendAPI
from app.main import app, get_backend
import json


@pytest.fixture
def api():
    return ConfigurableBackendAPI()


@pytest.fixture
def client(api):
    app.dependency_overrides[get_backend] = lambda: api
    yield AsyncClient(app=app, base_url="http://test")
    app.dependency_overrides.clear()


async def test_chat_stream_returns_token_events(client, api):
    api.sim_llm.set_stream_chunks(["Hello ", "world!"])

    response = await client.post(
        "/api/chat/stream",
        json={"message": "Hi"},
    )

    assert response.status_code == 200
    events = parse_sse(response.text)
    token_events = [e for e in events if e["event"] == "token"]
    assert len(token_events) == 2
    assert token_events[0]["data"]["delta"] == "Hello "
    assert api.sim_llm.stream_call_count == 1
```

### Unit test — Tier 2, error path

```python
from app.ports import LLMUnavailableError


async def test_chat_stream_503_on_llm_unavailable(client, api):
    api.sim_llm.set_stream_error(LLMUnavailableError("OpenRouter down"))

    response = await client.post("/api/chat/stream", json={"message": "Hi"})

    events = parse_sse(response.text)
    error_event = next(e for e in events if e["event"] == "error")
    assert error_event["data"]["code"] == "LLM_UNAVAILABLE"
```

### Unit test — Tier 2, swapping one port (mixed real + simulated)

If you want real PDF rendering but a simulated LLM:

```python
from app.backend_api import BackendAPI
from app.adapters import RenderCVAdapter, PyMuPDFAdapter
from tests.helpers.simulator import SimulatedLLMPort


def make_partial_backend() -> BackendAPI:
    sim_llm = SimulatedLLMPort()
    sim_llm.set_complete_response('{"yaml_content": "cv:\\n  name: Test\\n"}')
    return BackendAPI(
        llm=sim_llm,
        pdf_render=RenderCVAdapter(),   # real render-cv
        pdf_extract=PyMuPDFAdapter(),   # real PyMuPDF
    )
```

---

## Summary

| Tier | Class | Location | When used |
|------|-------|----------|-----------|
| 1 | `SimulatedBackendAPI` | `backend/app/simulator.py` | `LLM_MOCK=true` (E2E, Docker) |
| 2 | `ConfigurableBackendAPI` | `backend/tests/helpers/simulator.py` | pytest unit tests |
| — | `SimulatedLLMPort` | `backend/tests/helpers/simulator.py` | Mixed backends |
| — | `SimulatedPDFRenderPort` | `backend/tests/helpers/simulator.py` | Mixed backends |
| — | `SimulatedPDFExtractPort` | `backend/tests/helpers/simulator.py` | Mixed backends |
