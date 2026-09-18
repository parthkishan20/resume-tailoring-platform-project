"""The deterministic LLM stub: one canned response per prompt shape.

Why this file exists
--------------------
Two things in this project need a fake LLM:

1. **pytest** wants the two-pass generate-then-audit pipeline exercised with no
   cost, no latency and no key.
2. **``LLM_MOCK=true``** is a *runtime* mode. The e2e stack boots the real
   application with a fake provider behind it.

Both need the same property: the same messages in, the same bytes out, every
time, on every machine. :func:`classify` is the whole of the routing logic and
:func:`respond` is the whole of the stub.

Reconciled with the runtime stub
---------------------------------
This module used to keep its own copy of the canned strings, deliberately, so
that a test harness built while task 1.3 was still moving
``resumetailor/simulator.py`` to ``llm/stub.py`` in a different worktree would
break on a real defect rather than on the merge. That move has landed.

The canned values now live in exactly one place: ``resumetailor.llm.stub``,
which ships inside the Docker image and answers ``LLM_MOCK=true`` at runtime.
This module imports them from there rather than the other way around, because
the dependency has to point in that direction: ``backend/tests/`` is excluded
from the image by ``.dockerignore`` (that exclusion is D-64 — the same bug
class this reconciliation avoids reintroducing in reverse). Production code
must never import from a test-only path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

from resumetailor.llm.stub import _echo_candidate_cv
from resumetailor.llm.stub import (
    MOCK_CHAT_RESULT as CANNED_CHAT_RESULT,
)
from resumetailor.llm.stub import (
    MOCK_EVALUATION_RESULT as CANNED_EVALUATION_RESULT,
)
from resumetailor.llm.stub import (
    MOCK_EXTRACTED_TEXT as CANNED_EXTRACTED_TEXT,
)
from resumetailor.llm.stub import (
    MOCK_GENERATION_RESULT_YAML as CANNED_RESUME_YAML,
)

Shape = Literal["generation", "audit", "evaluation", "extraction", "chat"]


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
        return _echo_candidate_cv(user_content)

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

    async def stream(
        self, messages: list[dict], tools: object | None = None
    ) -> AsyncIterator[str]:
        del tools  # accepted for LLMPort-shape parity; this stub never calls a tool
        self.stream_call_count += 1
        self.last_stream_messages = messages
        text = str(CANNED_CHAT_RESULT["text"])

        async def _gen() -> AsyncIterator[str]:
            yield text

        return _gen()
