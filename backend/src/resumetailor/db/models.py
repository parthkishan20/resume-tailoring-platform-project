"""Typed rows. One model per shape a repository returns.

Routes used to hand FastAPI a ``dict`` built from a ``sqlite3.Row``, several of
them from ``SELECT *``, which is how any column added to a table silently
became part of the public API (D-54). These models are the fixed point: the
repository names the columns it reads and builds the model, so the shape of a
response is decided here and not by the current contents of the table.

The field sets below reproduce exactly what the old ``database.py`` returned,
key for key -- including the fact that :class:`ResumeSummary` has no
``yaml_content`` because the list query never selected it. Wiring these to
``response_model`` on the routes is task 2.2; this module only has to exist and
be correct for that to be a small change.

Every timestamp is a ``str`` holding ISO-8601 UTC (``2026-09-18T07:41:03Z``),
which is what the schema writes after migration 0004. They are not ``datetime``
because that would change the serialised form the frontend already parses, and
changing the wire format is task 2.2's call, not this one's.
"""

from __future__ import annotations

from pydantic import BaseModel


class MasterResume(BaseModel):
    """The one canonical resume document, per user."""

    id: int
    user_id: str
    yaml_content: str
    updated_at: str


class MasterResumeVersion(BaseModel):
    """A superseded master resume. The last ten are kept; nothing reads them yet."""

    id: int
    user_id: str
    yaml_content: str
    saved_at: str


class GeneratedResume(BaseModel):
    """One tailored resume, with the YAML it was rendered from."""

    id: int
    user_id: str
    name: str
    job_description: str
    yaml_content: str
    pdf_path: str | None
    created_at: str
    updated_at: str


class ResumeSummary(BaseModel):
    """A list row. Deliberately without ``yaml_content``: a library listing does
    not need every document's full source, and the list query never selected it.
    """

    id: int
    user_id: str
    name: str
    job_description: str
    pdf_path: str | None
    created_at: str
    updated_at: str


class ResumePage(BaseModel):
    """One page of the resume library, plus what it took to ask for it."""

    items: list[ResumeSummary]
    total: int
    page: int
    limit: int


class ChatMessage(BaseModel):
    """One turn of the assistant transcript."""

    id: int
    user_id: str
    role: str
    content: str
    created_at: str


class GenerationRule(BaseModel):
    """One ``section.rule_key = rule_value`` limit applied during generation.

    No ``id`` or ``user_id``: the rules query has always projected just these
    three columns, and the rules are addressed by ``(section, rule_key)``.
    """

    section: str
    rule_key: str
    rule_value: str


class SystemPrompt(BaseModel):
    """The system prompt in front of every assistant turn."""

    id: int
    user_id: str
    content: str
    updated_at: str
