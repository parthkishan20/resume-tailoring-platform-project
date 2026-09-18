"""The schema text the LLM is shown, generated from the models it must satisfy.

This is the other half of D-22. The import prompt used to carry a hand-written
copy of the RenderCV schema that had drifted from the normalizer — it told the
model to emit ``design: theme: classic``, which the normalizer then stripped,
and it listed ``LinkedIn`` and ``GitHub`` as the only permitted networks when
RenderCV accepts seventeen.

Everything below is derived from :mod:`resumetailor.resume_schema.models`,
which is derived from RenderCV. Field names, which fields are required, the
example values, and the list of social networks all come from RenderCV's own
Pydantic models, so the prompt cannot drift from what the normalizer accepts or
from what the renderer validates.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from resumetailor.resume_schema.models import (
    SECTION_TO_ENTRY,
    SOCIAL_NETWORKS,
    Cv,
    required_fields,
)

__all__ = ["IMPORT_SYSTEM_PROMPT", "schema_block"]

#: CV fields the prompt does not mention. Both are real RenderCV fields;
#: neither can be recovered from the text of a resume, and offering them only
#: invites the model to invent one.
_CV_FIELDS_NOT_PROMPTED = frozenset({"photo", "custom_connections"})

#: Entry fields the prompt does not mention, per entry model. These exist in
#: RenderCV and are legal, but asking for both `summary` and `highlights`
#: reliably produces a paragraph where bullets were wanted.
_ENTRY_FIELDS_NOT_PROMPTED = frozenset({"summary"})

#: The sections the prompt asks for, in the order they should appear in the
#: document, and the fields to leave out of each.
#:
#: RenderCV's entry models carry ``date`` *and* ``start_date``/``end_date``, and
#: it silently ignores the pair when ``date`` is set. Offering both invites a
#: model to fill in both and lose the range. So a section that describes a span
#: is asked only for the span, and a section that describes a moment only for
#: the moment.
_PROMPTED_SECTIONS: tuple[tuple[str, frozenset[str]], ...] = (
    ("experience", frozenset({"date"})),
    ("education", frozenset({"date"})),
    ("projects", frozenset({"start_date", "end_date", "location"})),
    ("skills", frozenset()),
    ("certifications", frozenset({"start_date", "end_date", "location"})),
)

#: Date fields are offered in ``YYYY-MM``, which is what the rules below ask
#: for. RenderCV's own first example is ``YYYY-MM-DD``; taking it verbatim would
#: make the schema block contradict the rules underneath it, which is the exact
#: failure D-22 is about.
_DATE_EXAMPLE_RE = re.compile(r"^\d{4}-\d{2}$")
_DATE_FIELDS = frozenset({"date", "start_date", "end_date"})


def _example(model: type[BaseModel], name: str) -> str:
    """One example value for a field, taken from RenderCV's own Field metadata."""
    info = model.model_fields[name]
    examples = [e for e in (info.examples or []) if isinstance(e, str)]
    if name in _DATE_FIELDS:
        for candidate in examples:
            if _DATE_EXAMPLE_RE.match(candidate):
                return candidate
    if examples:
        return examples[0]
    for candidate in info.examples or []:
        if isinstance(candidate, list) and candidate:
            return str(candidate[0])
    return "..."


def _field_lines(
    model: type[BaseModel], indent: str, omit: frozenset[str] = frozenset()
) -> list[str]:
    """One YAML line per field of ``model``, required ones marked."""
    required = set(required_fields(model))
    lines = []
    for name in model.model_fields:
        if name in _ENTRY_FIELDS_NOT_PROMPTED or name in omit:
            continue
        if name == "highlights":
            lines.append(f"{indent}highlights:")
            lines.append(f"{indent}  - Past-tense bullet naming the outcome")
            continue
        note = "" if name in required else "   # optional, omit if absent"
        lines.append(f"{indent}{name}: {_example(model, name)}{note}")
    return lines


def _cv_lines() -> list[str]:
    lines = []
    for name in Cv.model_fields:
        if name in _CV_FIELDS_NOT_PROMPTED or name == "sections":
            continue
        if name == "social_networks":
            lines.append("  social_networks:            # optional, omit if none")
            lines.append(
                "    - network: LinkedIn       # one of the names listed below"
            )
            lines.append("      username: handle-only   # the handle, never a URL")
            continue
        lines.append(f"  {name}: {_example(Cv, name)}   # optional, omit if absent")
    return lines


def schema_block() -> str:
    """The RenderCV document shape, as YAML, generated from the models."""
    lines = ["cv:", *_cv_lines(), "  sections:"]
    for section, omit in _PROMPTED_SECTIONS:
        model = SECTION_TO_ENTRY[section]
        lines.append(f"    {section}:")
        entry = _field_lines(model, "        ", omit)
        lines.append(f"      - {entry[0].strip()}")
        lines.extend(entry[1:])
    return "\n".join(lines)


def _networks_line() -> str:
    return ", ".join(sorted(SOCIAL_NETWORKS.values()))


def _import_system_prompt() -> str:
    return f"""\
You are a resume parser. Convert the resume text to EXACTLY this RenderCV YAML \
schema.

SCHEMA (copy field names verbatim — do not invent new keys):

{schema_block()}

SOCIAL NETWORKS — `network` must be exactly one of:
{_networks_line()}

RULES:
- Output ONLY the YAML above — no markdown fences, no prose.
- First line must be: cv:
- Do NOT output a `design:` block. The design is applied by the system and any
  `design:` you write is discarded.
- All section entries go under cv.sections — NEVER directly under cv.
- social_networks username must be the handle only, strip any URL.
- Dates must be YYYY-MM (e.g. "2023-01"). Use "present" for current roles.
- start_date must not be later than end_date.
- highlights must be a list of strings, one bullet per line.
- Omit any optional field that does not appear in the source.
- Omit phone entirely if no phone number appears in the source — never invent
  one. A phone number that is not dialable is dropped.
- Omit a whole section rather than emitting it empty.
"""


#: The system prompt for PDF import. Built once at import; the models it is
#: generated from do not change at runtime.
IMPORT_SYSTEM_PROMPT = _import_system_prompt()
