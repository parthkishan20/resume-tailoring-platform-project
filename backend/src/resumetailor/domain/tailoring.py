"""The two-pass generate-then-audit pipeline, with no HTTP in it.

This was a 90-line ``async def event_gen()`` inside
``api/routers/resumes.py``: master-resume fetch, YAML normalization, rules-to-
prompt assembly, two LLM calls, response parsing, PDF render and two database
writes, interleaved with the ``event: progress`` frames that narrate them. A
pipeline that can only be reached through an SSE response cannot be tested
without one, which is the root cause behind D-04 and D-57 — nothing validated
on the way in and the render-only path grew a different normalization story,
because there was no one place where either rule could live.

Two functions, in the order a caller uses them:

* :func:`tailor` is the pipeline. It takes YAML, a job description and the
  user's rules, and yields a :class:`Stage` before each step it is about to
  take, then one :class:`TailoredResume` as its last event. It touches no
  database and no filesystem.
* :func:`store_tailored_resume` is the write. It is synchronous and blocking on
  purpose — the caller hands it to ``asyncio.to_thread`` once, rather than
  making three trips for two database statements and a file write.

**Progress reporting.** The stages are an enum, not strings. The user-visible
message text is part of the SSE contract the frontend already depends on, so it
stays with the route that writes the frames (see ``_PROGRESS_MESSAGES`` in
``api/routers/resumes.py``); what the domain knows is that there are three
steps and which one is next.

**D-04, on this path.** The YAML this pipeline stores has been through
``normalize_to_rendercv`` and then through an actual render before
``create_resume`` sees it, so a row is only written for a document that
demonstrably produces a PDF. That is a stronger guarantee than
``resume_schema.validate`` gives and it is the same code path, so this module
deliberately does not also call ``validate``: duplicating the check would only
add a second opinion about the same document. The write paths with no render
behind them are where ``validate`` belongs, and ``PATCH /api/resumes/{id}``
now calls it (``PUT /api/master-resume`` is the other one, in a file this task
does not own — see PLAN.md D-04).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from resumetailor.backend_api import BackendAPI
from resumetailor.db.models import GeneratedResume, GenerationRule
from resumetailor.db.repositories import create_resume, update_resume
from resumetailor.prompts import (
    CRITIQUE_SYSTEM_PROMPT,
    GENERATION_SYSTEM_PROMPT,
    rules_block,
)
from resumetailor.resume_schema.normalize import DroppedField, normalize_to_rendercv

__all__ = [
    "Stage",
    "TailoredResume",
    "TailoringEvent",
    "store_tailored_resume",
    "tailor",
]

#: The generation pass answers with one JSON field holding the YAML document.
#: Unchanged from the route this moved out of, deliberately: the schema is part
#: of what the deterministic LLM stub branches on.
_DRAFT_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "tailored_resume",
        "schema": {
            "type": "object",
            "properties": {"yaml_content": {"type": "string"}},
            "required": ["yaml_content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

#: The audit pass prefixes its YAML with a human-readable rubric report between
#: ``AUDIT_START`` and this marker. Everything up to and including it is the
#: auditor talking to us, not part of the document.
_AUDIT_END = "AUDIT_END"

#: How much of the job description becomes the resume's name.
_NAME_JD_CHARS = 40


class Stage(Enum):
    """The step :func:`tailor` is about to take.

    Yielded *before* the work, so a caller can tell the user what is happening
    rather than what has happened.
    """

    ANALYZING = "analyzing"
    TAILORING = "tailoring"
    RENDERING = "rendering"


@dataclass(frozen=True)
class TailoredResume:
    """A finished tailored resume: the document, the PDF, and what it cost.

    Attributes:
        yaml_content: The normalized document that produced ``pdf_bytes``.
            This is what gets stored, so the stored YAML and the stored PDF
            are always the same document.
        pdf_bytes: The rendered PDF.
        dropped: Every field the normalizer removed on the way here, across
            all three normalization passes (PLAN.md D-08). Nothing surfaces
            these to the user yet: the ``event: done`` payload shape is the
            API contract task 2.2 owns, and displaying them is 3.1's. They are
            carried here so that work does not have to re-run the pipeline to
            find out what went missing.
    """

    yaml_content: str
    pdf_bytes: bytes
    dropped: list[DroppedField] = field(default_factory=list)


#: What :func:`tailor` yields: a stage marker before each step, then exactly one
#: result as the final event.
TailoringEvent = Stage | TailoredResume


def _strip_audit_report(response: str) -> str:
    """Return the YAML the auditor emitted, without its rubric report."""
    if _AUDIT_END in response:
        return response.split(_AUDIT_END, 1)[1].strip()
    return response.strip()


async def tailor(
    api: BackendAPI,
    *,
    master_yaml: str,
    job_description: str,
    rules: Sequence[GenerationRule],
) -> AsyncIterator[TailoringEvent]:
    """Tailor ``master_yaml`` to ``job_description``, narrating as it goes.

    Args:
        api: The port facade. Two ``complete`` calls and one ``render``.
        master_yaml: The master resume, as stored. Normalized here rather than
            by the caller, so every entry to this pipeline gets the same
            document the renderer would accept.
        job_description: The job to tailor against.
        rules: The user's per-section limits, which override the counts in the
            system prompts.

    Yields:
        A :class:`Stage` before each of the three steps, then one
        :class:`TailoredResume`. The generator is exhausted after the result.
    """
    yield Stage.ANALYZING

    master = normalize_to_rendercv(master_yaml)
    # `rules_block` takes dicts and the repository returns models; `prompts.py`
    # belongs to another task.
    rules_suffix = rules_block([rule.model_dump() for rule in rules])

    draft_response = await api.complete(
        [
            {
                "role": "system",
                "content": GENERATION_SYSTEM_PROMPT + rules_suffix,
            },
            {
                "role": "user",
                "content": f"JD:\n{job_description}\n\nMaster:\n{master.yaml}",
            },
        ],
        response_format=_DRAFT_RESPONSE_FORMAT,
    )
    draft = normalize_to_rendercv(json.loads(draft_response)["yaml_content"])

    yield Stage.TAILORING

    audit_response = await api.complete(
        [
            {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT + rules_suffix},
            {
                "role": "user",
                "content": (
                    f"Draft:\n{draft.yaml}\n\nMaster:\n{master.yaml}\n\n"
                    f"JD:\n{job_description}"
                ),
            },
        ]
    )
    final = normalize_to_rendercv(_strip_audit_report(audit_response))

    yield Stage.RENDERING

    pdf_bytes = await api.render(final.yaml)

    yield TailoredResume(
        yaml_content=final.yaml,
        pdf_bytes=pdf_bytes,
        dropped=[*master.dropped, *draft.dropped, *final.dropped],
    )


def store_tailored_resume(
    db_path: str,
    pdfs_dir: str,
    *,
    job_description: str,
    result: TailoredResume,
) -> GeneratedResume:
    """Persist a finished resume: the row, the PDF file, then the row again.

    **D-20 lives here** (PLAN.md section 2.1, "partial-failure orphans"). The
    three steps below are not one transaction, and this function is where that
    is now visible in one place rather than spread down a route handler: a
    crash after ``create_resume`` leaves a row whose ``pdf_path`` is ``NULL``
    and whose PDF never existed; a crash after ``write_bytes`` leaves a file
    on disk that no row references. Nothing reaps either. Fixing it needs a
    transactional boundary across the database and the filesystem, which
    belongs with the ``data`` role and task 3.5's orphan reaper, not here.

    Synchronous on purpose: two SQLite statements and one file write behind a
    single ``asyncio.to_thread`` hop, rather than three hops with a blocking
    ``write_bytes`` on the event loop in between.

    Returns:
        The stored resume, with ``pdf_path`` set.
    """
    # Kept verbatim from the route this moved out of, em dash included. It is a
    # user-visible string and DESIGN-SYSTEM.md section 7 forbids the character,
    # but changing it renames every resume generated from here on, which is a
    # copy decision and a data change rather than a refactor.
    name = f"Resume — {job_description[:_NAME_JD_CHARS]}"
    row = create_resume(db_path, name, job_description, result.yaml_content)

    pdf_path = Path(pdfs_dir) / f"{row.id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(result.pdf_bytes)

    updated = update_resume(db_path, row.id, pdf_path=f"{row.id}.pdf")
    # `update_resume` answers `None` only for a row that is not there, and this
    # one was inserted two statements ago.
    return updated if updated is not None else row
