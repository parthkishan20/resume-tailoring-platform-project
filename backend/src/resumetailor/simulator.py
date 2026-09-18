# MOVED BY TASK 1.3. This becomes llm/stub.py, the deterministic stub used by
# the tests and by LLM_MOCK. See PLAN.md section 3.2.
#
# `_FIXTURE_PDF` still points into `backend/tests/`, which is where it pointed
# before the move. That is a real problem and 1.3 should fix it: `.dockerignore`
# excludes `backend/tests/`, so inside the image this path does not exist and
# LLM_MOCK render fails with FileNotFoundError. See the 1.1 report.
from __future__ import annotations
import json
from typing import AsyncIterator

from resumetailor.core.config import BACKEND_ROOT

_FIXTURE_PDF = BACKEND_ROOT / "tests" / "fixtures" / "mock.pdf"

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
        # PDF import (has response_format schema) or chat
        if response_format:
            return json.dumps({"yaml_content": MOCK_GENERATION_RESULT_YAML})
        return json.dumps(MOCK_CHAT_RESULT)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            yield MOCK_CHAT_RESULT["text"]

        return _gen()

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
