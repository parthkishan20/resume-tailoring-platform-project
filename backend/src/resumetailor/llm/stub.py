"""The deterministic backend: no network, no key, the same answer every time.

This is what ``LLM_MOCK=true`` runs against and what the e2e stack uses. It
implements all three ports, so ``backend_api.create_stub_backend`` can hand the
same object to each one.

The fixture PDF lives here, inside the package, rather than in
``backend/tests/`` where it used to (PLAN.md D-64). ``.dockerignore`` excludes
the test tree from the image, so in the container the old path did not exist
and the first generation in the e2e stack died with ``FileNotFoundError`` —
which nothing had caught, because both tasks that built that stack ran without
a Docker daemon.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

_FIXTURE_PDF = Path(__file__).resolve().parent / "fixtures" / "mock.pdf"

# ── Tier 1 constants (PLAN.md §11) ─────────────────────────────────────────

MOCK_CHAT_RESULT: dict[str, Any] = {
    "text": (
        "I understand. Here's what I can help you with: editing your master "
        "resume, generating a tailored resume, or evaluating a resume against "
        "a job description."
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

MOCK_EVALUATION_RESULT: dict[str, Any] = {
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

# The en-dashes below are not a style choice: `backend/tests/helpers/llm_stub.py`
# imports this constant rather than keeping its own copy, so a change here is a
# change for both the pytest suite and the LLM_MOCK=true e2e stack.
MOCK_EXTRACTED_TEXT: str = (
    "John Mock\nmock@example.com\n+10000000000\nMock City, MC\n\n"
    "EDUCATION\nMock University — B.S. Computer Science, 2018–2022\n\n"  # noqa: RUF001
    "EXPERIENCE\nMock Corp — Software Engineer, 2022–present\n"  # noqa: RUF001
    "  • Built mock features using Python and React\n"
    "  • Deployed mock services with Docker\n\n"
    "SKILLS\nPython, TypeScript, React, Docker, Git, FastAPI, SQL"
)


# ── Tier 1: SimulatedBackendAPI ─────────────────────────────────────────────


class SimulatedBackendAPI:
    """Deterministic E2E mock. Activated when LLM_MOCK=true."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        system: str = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        if "ResumeTailor" in system:
            if response_format:
                return json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML})
            return MOCK_GENERATION_RESULT_YAML
        if "ResumeAuditor" in system:
            user_content: str = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            start = user_content.find("cv:")
            return user_content[start:] if start != -1 else MOCK_GENERATION_RESULT_YAML
        if "evaluation" in system.lower():
            return json.dumps(MOCK_EVALUATION_RESULT)
        # PDF import (has response_format schema) or chat
        if response_format:
            return json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML})
        return json.dumps(MOCK_CHAT_RESULT)

    async def stream(
        self,
        messages: list[dict[str, Any]],  # noqa: ARG002 — fixed answer
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            text: str = MOCK_CHAT_RESULT["text"]
            yield text

        return _gen()

    async def render(self, yaml_content: str) -> bytes:  # noqa: ARG002
        return _FIXTURE_PDF.read_bytes()

    async def extract(self, pdf_bytes: bytes) -> str:  # noqa: ARG002
        return MOCK_EXTRACTED_TEXT
