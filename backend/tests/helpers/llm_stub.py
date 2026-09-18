"""The deterministic LLM stub: one canned response per prompt shape.

Why this file exists
--------------------
Two things in this project need a fake LLM, and until now they were two
separate fakes that could drift apart:

1. **pytest** wants the two-pass generate-then-audit pipeline exercised with no
   cost, no latency and no key.
2. **``LLM_MOCK=true``** is a *runtime* mode. The e2e stack boots the real
   application with a fake provider behind it.

Both need the same property: the same messages in, the same bytes out, every
time, on every machine. So the canned responses live here, in one table, keyed
by *prompt shape* rather than by call site. :func:`classify` is the whole of the
routing logic and :func:`respond` is the whole of the stub.

Self-contained on purpose
-------------------------
This module imports nothing from ``resumetailor``. The runtime stub it mirrors
(``resumetailor/simulator.py``, which task 1.3 is moving to ``llm/stub.py``) is
being restructured in a different worktree at the time of writing, so a test
harness that imported it would break on the merge rather than on a real defect.

The canned strings below are byte-identical to that module's ``MOCK_*``
constants. **Reconciling the two into one canonical stub is a follow-up for
whoever merges tasks 1.2, 1.3 and 1.5**: the runtime stub should import this
table, not keep a second copy of it. Until then, a change to one is a change to
both.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

Shape = Literal["generation", "audit", "evaluation", "extraction", "chat"]

# ── Canned responses ────────────────────────────────────────────────────────
#
# Deliberately boring and obviously fake. Every value is recognisable in a
# failure message ("Mock Corp", "Mock University") so a test that accidentally
# asserts against stub output instead of real output is easy to spot.

CANNED_RESUME_YAML: str = """\
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

CANNED_CHAT_RESULT: dict = {
    "text": (
        "I understand. Here's what I can help you with: editing your master resume, "
        "generating a tailored resume, or evaluating a resume against a job description."
    ),
    "action": None,
}

CANNED_EVALUATION_RESULT: dict = {
    "match_score": 72,
    "critique": (
        "The resume covers most required skills but lacks explicit mention of "
        "Kubernetes and CI/CD pipelines listed in the job description."
    ),
    "matched_keywords": ["Python", "REST API", "PostgreSQL"],
    "missing_keywords": ["Kubernetes", "CI/CD", "Docker Compose"],
}

# The en-dashes below are not a style choice: this string is byte-identical to
# `resumetailor.simulator`'s, and the two must stay that way until they are
# reconciled into one stub.
CANNED_EXTRACTED_TEXT: str = (
    "John Mock\nmock@example.com\n+10000000000\nMock City, MC\n\n"
    "EDUCATION\nMock University — B.S. Computer Science, 2018–2022\n\n"  # noqa: RUF001
    "EXPERIENCE\nMock Corp — Software Engineer, 2022–present\n"  # noqa: RUF001
    "  • Built mock features using Python and React\n"
    "  • Deployed mock services with Docker\n\n"
    "SKILLS\nPython, TypeScript, React, Docker, Git, FastAPI, SQL"
)


# ── Routing ─────────────────────────────────────────────────────────────────


def classify(messages: list[dict], response_format: dict | None = None) -> Shape:
    """Name the prompt shape a set of messages represents.

    The system prompt carries the caller's identity, so that is what we key on.
    ``response_format`` only disambiguates the two shapes that share a system
    prompt: structured extraction from an imported PDF, and free chat.
    """
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    if "ResumeTailor" in system:
        return "generation"
    if "ResumeAuditor" in system:
        return "audit"
    if "evaluation" in system.lower():
        return "evaluation"
    if response_format:
        return "extraction"
    return "chat"


def respond(messages: list[dict], response_format: dict | None = None) -> str:
    """The canned response for these messages. Pure: no I/O, no clock, no RNG."""
    shape = classify(messages, response_format)

    if shape == "generation":
        if response_format:
            return json.dumps({"yaml_content": CANNED_RESUME_YAML})
        return CANNED_RESUME_YAML

    if shape == "audit":
        # The auditor's contract is to return the resume it was handed, revised.
        # Echoing the input back is the identity case, and it keeps the two-pass
        # pipeline observable: a test can put a marker in the resume and assert
        # it survived both passes.
        user_content = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        start = user_content.find("cv:")
        return user_content[start:] if start != -1 else CANNED_RESUME_YAML

    if shape == "evaluation":
        return json.dumps(CANNED_EVALUATION_RESULT)

    if shape == "extraction":
        return json.dumps({"yaml_content": CANNED_RESUME_YAML})

    return json.dumps(CANNED_CHAT_RESULT)


class DeterministicLLM:
    """An :class:`LLMPort`-shaped stub over :func:`respond`.

    Duck-typed rather than subclassed: nothing here imports ``resumetailor``, so
    this keeps working across the module moves in tasks 1.2 and 1.3.

    Records every call so a test can assert on *what was asked*, which is
    usually the interesting half. ``complete_call_count == 2`` is how the
    generate-then-audit two-pass flow is pinned.
    """

    def __init__(self) -> None:
        self.complete_call_count: int = 0
        self.stream_call_count: int = 0
        self.last_complete_messages: list[dict] | None = None
        self.last_stream_messages: list[dict] | None = None
        self.shapes_seen: list[Shape] = []

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        self.complete_call_count += 1
        self.last_complete_messages = messages
        self.shapes_seen.append(classify(messages, response_format))
        return respond(messages, response_format)

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        self.stream_call_count += 1
        self.last_stream_messages = messages
        text = str(CANNED_CHAT_RESULT["text"])

        async def _gen() -> AsyncIterator[str]:
            yield text

        return _gen()
