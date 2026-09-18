"""Tool calling: the assistant performing a real workstation action.

This is D-33, PLAN.md's single largest product gap, closed the way ADR 0005
(D8) scopes it: **four tools, no more, and no general API exposure.** Every
tool here writes through the same repository functions and the same domain
services (:mod:`resumetailor.domain.tailoring`,
:mod:`resumetailor.domain.evaluation`) the HTTP routes use, not a shortcut
around them, and every tool's arguments are validated exactly as a request
body would be -- they are model-authored text turned into JSON, which makes
them exactly as trustworthy as a POST body and no more.

:func:`run_assistant_turn` is what ``api/routers/chat.py`` calls. It is the
whole of the orchestration: stream the model, execute whatever tools it asks
for, feed the results back, and repeat until it answers in text or the round
budget runs out. The route stays a thin adapter -- it turns each yielded event
into an SSE frame and nothing more -- the same split task 2.5 drew between
``domain/tailoring.py`` and ``api/routers/resumes.py``.

**What is deliberately not here**, per ADR 0005: no delete tool of any kind,
no tool that can rewrite the system prompt, and no tool that takes a raw path,
a SQL fragment, or an arbitrary endpoint name. A model asking for anything
outside the four below gets back a sentence saying so, not a wider surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from pydantic import BaseModel, Field, ValidationError

from resumetailor.backend_api import BackendAPI
from resumetailor.core.errors import BackendError
from resumetailor.core.security import MAX_JOB_DESCRIPTION_CHARS, MAX_RESUME_YAML_CHARS
from resumetailor.db.repositories import (
    get_master_resume,
    get_resume,
    get_rules,
    upsert_master_resume,
    upsert_rules,
)
from resumetailor.domain.evaluation import evaluate
from resumetailor.domain.tailoring import TailoredResume, store_tailored_resume, tailor
from resumetailor.llm.port import ToolCall, ToolSpec
from resumetailor.rendering.errors import RenderIssue
from resumetailor.resume_schema.validate import validate

__all__ = [
    "TOOL_SPECS",
    "AssistantAction",
    "AssistantEvent",
    "AssistantReply",
    "run_assistant_turn",
]

logger = logging.getLogger(__name__)

#: Rounds of "model asks for a tool, we run it, we tell the model what
#: happened" one turn may go through before the last round is asked without
#: tools at all, which forces a text answer. Bounds the connection: a model
#: that keeps asking for tools cannot hold an SSE stream open indefinitely, and
#: the fixed four-tool set (ADR 0005) means a real request rarely needs more
#: than one round in the first place.
MAX_TOOL_ITERATIONS: Final = 4

#: D-78: the round budget above bounds how many times the model may ask for
#: tools, but nothing capped how many calls one round's single response could
#: contain -- `run_assistant_turn` executed every `ToolCall` a response
#: carried, so a generous or adversarial provider response (a crafted job
#: description or imported-PDF text asking for many actions at once) could
#: fan one rate-limited `/api/chat/stream` request out into many
#: `generate_tailored_resume` calls -- each itself further provider calls
#: plus a real render subprocess -- undermining task 2.4's cost/DoS control
#: (D-28's cost half) in exactly the way that limiter was never sized for.
#: Four matches the tool set's own size (ADR 0005): a genuine turn asking for
#: every tool at once is already at the ceiling a well-formed request needs.
MAX_TOOL_CALLS_PER_ROUND: Final = 4


@dataclass(frozen=True, slots=True)
class AssistantAction:
    """A workstation action the assistant actually completed this turn.

    Mirrors ``api/schemas/sse.py``'s ``ChatAction`` field for field, but lives
    here rather than importing it: a domain module does not reach into
    ``api/``, and the two are small enough that duplication is cheaper than
    the dependency would be. ``api/routers/chat.py`` is what turns one of
    these into the wire shape.
    """

    type: str
    resume_id: int | None = None


@dataclass(frozen=True, slots=True)
class AssistantReply:
    """The finished turn: everything the model said, and what it did.

    ``action`` names the *last* tool call that completed successfully this
    turn, or ``None`` if none did -- a tool call that failed validation or
    raised a domain error reports its failure back to the model as a tool
    result (so the model can explain it) rather than becoming this turn's
    action.
    """

    text: str
    action: AssistantAction | None


#: What :func:`run_assistant_turn` yields: a chunk of assistant text (to
#: forward as an ``event: token`` frame, exactly as before this task), then
#: exactly one :class:`AssistantReply` as the last event. Mirrors
#: ``domain.tailoring.TailoringEvent``'s shape on purpose.
AssistantEvent = str | AssistantReply


# ── Tool arguments ───────────────────────────────────────────────────────────
#
# Bounded the same way the request models in api/routers/*.py are (D-47):
# these arguments are model output, not a trusted internal call, so they get
# exactly the validation a POST body would.


class _EditMasterResumeArgs(BaseModel):
    yaml_content: str = Field(max_length=MAX_RESUME_YAML_CHARS)


class _GenerateTailoredResumeArgs(BaseModel):
    job_description: str = Field(max_length=MAX_JOB_DESCRIPTION_CHARS)


class _EvaluateResumeArgs(BaseModel):
    job_description: str = Field(max_length=MAX_JOB_DESCRIPTION_CHARS)
    #: Omitted or null: evaluate the master resume. Set: evaluate a
    #: previously generated one. There is no third source -- the assistant has
    #: no reach into an editor's unsaved buffer, which stays a frontend-only
    #: concept (D-45's other half, task 3.1's).
    resume_id: int | None = None


class _RuleArg(BaseModel):
    #: 200, not one of the four `MAX_*_CHARS` in `core/security.py`: a rule is
    #: a short label and a short value (see `RuleItem` in
    #: `api/routers/rules.py`, which is D-70 -- still unbounded there, in a
    #: file this task does not own). Bounding it here keeps a model-authored
    #: rule list from being a way around a limit the equivalent HTTP route
    #: still lacks.
    section: str = Field(max_length=200)
    rule_key: str = Field(max_length=200)
    rule_value: str = Field(max_length=200)


class _UpdateGenerationRulesArgs(BaseModel):
    rules: list[_RuleArg] = Field(min_length=1, max_length=50)


@dataclass(frozen=True, slots=True)
class _ToolOutcome:
    """What running one tool produced.

    ``content`` is fed back to the model as the tool result, verbatim -- on
    success it is a plain-language confirmation the model can relay or build
    on; on failure it is the same client-safe sentence an HTTP caller would
    get (D-53's ``client_message`` pattern), never ``str(exc)``. ``action`` is
    set only on success, and only for a tool whose effect is worth reporting to
    the frontend via the SSE ``done`` frame.
    """

    content: str
    action: AssistantAction | None


class _ToolHandler(Protocol):
    async def __call__(
        self, args: dict[str, Any], *, api: BackendAPI, db_path: str, pdfs_dir: str
    ) -> _ToolOutcome: ...


def _issue_detail(issues: Sequence[RenderIssue]) -> str:
    """The validation failures, as one line the model (and the user) can act on.

    Same shape as ``api/routers/resumes.py``'s ``_issue_detail``: safe to
    return, because it describes the submitted document field by field and
    says nothing about the inside of the process.
    """
    return "This resume is not valid: " + "; ".join(
        f"{issue.path}: {issue.message}" for issue in issues
    )


async def _edit_master_resume(
    args: dict[str, Any], *, api: BackendAPI, db_path: str, pdfs_dir: str
) -> _ToolOutcome:
    """Replace the master resume, refusing a document that will not render.

    D-33's explicit hazard: ``PUT /api/master-resume`` (the manual save path)
    does not validate today (D-04 is still open there, in a file this task
    does not own -- see PLAN.md). Going through "the same path" the UI uses
    would inherit that gap, which ADR 0005 calls out by name. This tool closes
    it independently, the same way ``PATCH /api/resumes/{id}`` does: refuse
    before writing, rather than store and let the user discover the problem at
    render time.
    """
    del api, pdfs_dir
    parsed = _EditMasterResumeArgs.model_validate(args)
    _, issues = await asyncio.to_thread(validate, parsed.yaml_content)
    if issues:
        return _ToolOutcome(content=_issue_detail(issues), action=None)
    await asyncio.to_thread(upsert_master_resume, db_path, parsed.yaml_content)
    return _ToolOutcome(
        content="The master resume was updated.",
        action=AssistantAction(type="master_resume_updated"),
    )


async def _generate_tailored_resume(
    args: dict[str, Any], *, api: BackendAPI, db_path: str, pdfs_dir: str
) -> _ToolOutcome:
    """Tailor the master resume to a job description and store the result.

    The pipeline is ``domain.tailoring.tailor``, unchanged: this tool runs it
    to completion and stores the one :class:`TailoredResume` it ends on, the
    same as ``POST /api/resumes/stream`` does. What it does not do is narrate
    the three stages as separate SSE frames -- the chat route has no frame
    shape for "progress inside a tool call" (extending ``STREAM_CONTRACTS`` for
    one nested case was judged not worth widening the contract this task
    touches only by necessity), so the caller sees one "the assistant is
    working" gap and then either the result or a tool-result explanation.
    """
    parsed = _GenerateTailoredResumeArgs.model_validate(args)
    master = await asyncio.to_thread(get_master_resume, db_path)
    if master is None:
        return _ToolOutcome(
            content="There is no master resume to tailor yet.", action=None
        )
    rules = await asyncio.to_thread(get_rules, db_path)

    result: TailoredResume | None = None
    async for event in tailor(
        api,
        master_yaml=master.yaml_content,
        job_description=parsed.job_description,
        rules=rules,
    ):
        if isinstance(event, TailoredResume):
            result = event
    if result is None:  # pragma: no cover - tailor() always ends on one TailoredResume
        msg = "the tailoring pipeline ended without a result"
        raise AssertionError(msg)

    row = await asyncio.to_thread(
        store_tailored_resume,
        db_path,
        pdfs_dir,
        job_description=parsed.job_description,
        result=result,
    )
    return _ToolOutcome(
        content=f'Generated a tailored resume named "{row.name}" (id {row.id}).',
        action=AssistantAction(type="resume_generated", resume_id=row.id),
    )


async def _evaluate_resume(
    args: dict[str, Any], *, api: BackendAPI, db_path: str, pdfs_dir: str
) -> _ToolOutcome:
    """Score the master resume, or a generated one, against a job description."""
    del pdfs_dir
    parsed = _EvaluateResumeArgs.model_validate(args)

    if parsed.resume_id is not None:
        generated = await asyncio.to_thread(get_resume, db_path, parsed.resume_id)
        if generated is None:
            return _ToolOutcome(
                content=f"There is no generated resume with id {parsed.resume_id}.",
                action=None,
            )
        yaml_content = generated.yaml_content
    else:
        master = await asyncio.to_thread(get_master_resume, db_path)
        if master is None:
            return _ToolOutcome(
                content="There is no master resume to evaluate yet.", action=None
            )
        yaml_content = master.yaml_content

    result = await evaluate(
        api, yaml_content=yaml_content, job_description=parsed.job_description
    )
    missing = ", ".join(result.missing_keywords) if result.missing_keywords else "none"
    return _ToolOutcome(
        content=(
            f"Match score {result.match_score}/100. {result.critique} "
            f"Missing keywords: {missing}."
        ),
        action=AssistantAction(type="evaluated", resume_id=parsed.resume_id),
    )


async def _update_generation_rules(
    args: dict[str, Any], *, api: BackendAPI, db_path: str, pdfs_dir: str
) -> _ToolOutcome:
    """Set the per-section generation rules. Leaves every other rule alone."""
    del api, pdfs_dir
    parsed = _UpdateGenerationRulesArgs.model_validate(args)
    await asyncio.to_thread(
        upsert_rules, db_path, [rule.model_dump() for rule in parsed.rules]
    )
    return _ToolOutcome(
        content="The generation rules were updated.",
        action=AssistantAction(type="rules_updated"),
    )


_TOOL_HANDLERS: dict[str, _ToolHandler] = {
    "edit_master_resume": _edit_master_resume,
    "generate_tailored_resume": _generate_tailored_resume,
    "evaluate_resume": _evaluate_resume,
    "update_generation_rules": _update_generation_rules,
}

#: The fixed action set (ADR 0005 / PLAN.md D8). Descriptions are the only
#: thing telling the model what each tool does and when to reach for it -- the
#: stored system prompt is user-editable content (a prompt-injection surface
#: per D-28) and deliberately carries none of this.
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="edit_master_resume",
        description=(
            "Replace the user's master resume with a new RenderCV YAML "
            "document. Provide the complete document, not a partial patch: "
            "whatever is passed becomes the whole master resume."
        ),
        parameters={
            "type": "object",
            "properties": {
                "yaml_content": {
                    "type": "string",
                    "description": "The full RenderCV YAML document.",
                }
            },
            "required": ["yaml_content"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="generate_tailored_resume",
        description=(
            "Tailor the user's master resume to a job description and store "
            "the result as a new generated resume with a rendered PDF."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_description": {
                    "type": "string",
                    "description": "The job description to tailor the resume to.",
                }
            },
            "required": ["job_description"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="evaluate_resume",
        description=(
            "Score a resume against a job description. Omit resume_id to "
            "evaluate the master resume, or pass the id of a previously "
            "generated resume to evaluate that one instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_description": {"type": "string"},
                "resume_id": {
                    "type": ["integer", "null"],
                    "description": (
                        "A generated resume's id, or omit/null for the master resume."
                    ),
                },
            },
            "required": ["job_description"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="update_generation_rules",
        description=(
            "Set the per-section rules applied when tailoring a resume, such "
            "as a maximum bullet count for a section. Replaces only the "
            "listed (section, rule_key) pairs; every other rule is left alone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "rules": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string"},
                            "rule_key": {"type": "string"},
                            "rule_value": {"type": "string"},
                        },
                        "required": ["section", "rule_key", "rule_value"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["rules"],
            "additionalProperties": False,
        },
    ),
)


async def _execute_tool(
    call: ToolCall, *, api: BackendAPI, db_path: str, pdfs_dir: str
) -> _ToolOutcome:
    """Run one tool call, never letting it raise past this function.

    A tool call is model output all the way down -- the name, the JSON, and
    the values inside it -- so every way it can be wrong is handled as data,
    not as an exception that unwinds the SSE stream: malformed JSON, an
    unknown tool name, arguments that fail validation, and a domain error the
    tool's own work raised (D-53: the client-safe ``client_message``, logged
    with ``exc.code`` and the full detail, never ``str(exc)``). Each becomes a
    tool-result sentence for the model instead, so the turn continues and the
    model can explain the failure in its own words rather than the connection
    simply dying.
    """
    try:
        parsed_args: dict[str, Any] = (
            json.loads(call.arguments) if call.arguments.strip() else {}
        )
    except json.JSONDecodeError:
        return _ToolOutcome(
            content=(
                "The action's arguments were not valid JSON, so nothing was changed."
            ),
            action=None,
        )

    handler = _TOOL_HANDLERS.get(call.name)
    if handler is None:
        return _ToolOutcome(
            content=f'"{call.name}" is not an action this assistant can perform.',
            action=None,
        )

    try:
        return await handler(parsed_args, api=api, db_path=db_path, pdfs_dir=pdfs_dir)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        return _ToolOutcome(
            content=f"The action's inputs were invalid ({field}: {first['msg']}).",
            action=None,
        )
    except BackendError as exc:
        logger.exception(
            "assistant tool failed: %s",
            exc.code,
            extra={"error_code": exc.code, "tool": call.name},
        )
        return _ToolOutcome(content=exc.client_message, action=None)


def _tool_call_message(text: str, calls: Sequence[ToolCall]) -> dict[str, Any]:
    """The assistant turn that asked for ``calls``, in the shape a provider expects."""
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ],
    }


async def run_assistant_turn(
    api: BackendAPI,
    *,
    db_path: str,
    pdfs_dir: str,
    messages: Sequence[dict[str, Any]],
) -> AsyncIterator[AssistantEvent]:
    """Run one assistant turn to completion: stream text, act on tool calls, repeat.

    Args:
        api: The port facade, handed straight to :meth:`BackendAPI.stream`.
        db_path: Where the tools that touch the database read and write.
        pdfs_dir: Where :func:`domain.tailoring.store_tailored_resume` writes
            a rendered PDF, for the ``generate_tailored_resume`` tool.
        messages: The conversation so far -- system prompt and history -- the
            same list ``api/routers/chat.py`` already built. Not mutated: a
            working copy carries the tool-call round trip.

    Yields:
        A ``str`` for every chunk of assistant text, across every round, in
        order. Exactly one :class:`AssistantReply` last, once the model has
        answered with no further tool calls -- ``action`` on it names the last
        workstation action a tool actually completed, or ``None`` if the turn
        touched nothing. The generator is exhausted after that event, the same
        contract :func:`domain.tailoring.tailor` uses for its own last event.

    The loop is bounded at :data:`MAX_TOOL_ITERATIONS` rounds of tool calls.
    The round after the budget is spent is asked with no ``tools`` at all,
    and its result is always treated as final -- a well-behaved provider
    cannot return a tool call it was not offered, but the round finalizing
    unconditionally (rather than by trusting that guarantee) is what makes
    the loop provably bounded rather than merely expected to be.
    """
    conversation = list(messages)
    text_parts: list[str] = []
    action: AssistantAction | None = None

    for round_index in range(MAX_TOOL_ITERATIONS + 1):
        tools = TOOL_SPECS if round_index < MAX_TOOL_ITERATIONS else None
        round_text: list[str] = []
        tool_calls: list[ToolCall] = []

        async for event in await api.stream(list(conversation), tools=tools):
            if isinstance(event, ToolCall):
                tool_calls.append(event)
            else:
                round_text.append(event)
                text_parts.append(event)
                yield event

        if tools is None or not tool_calls:
            yield AssistantReply(text="".join(text_parts), action=action)
            return

        conversation.append(_tool_call_message("".join(round_text), tool_calls))
        for call in tool_calls[:MAX_TOOL_CALLS_PER_ROUND]:
            outcome = await _execute_tool(
                call, api=api, db_path=db_path, pdfs_dir=pdfs_dir
            )
            if outcome.action is not None:
                action = outcome.action
            conversation.append(
                {"role": "tool", "tool_call_id": call.id, "content": outcome.content}
            )
        # Every tool_call_id from this round needs a matching tool message
        # before the next request, or the next `api.stream` call is a
        # malformed conversation as far as the provider's API is concerned --
        # so a call beyond the cap still gets a reply, just one that says why
        # it did not run, rather than being silently dropped.
        for call in tool_calls[MAX_TOOL_CALLS_PER_ROUND:]:
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": (
                        f"Not executed: at most {MAX_TOOL_CALLS_PER_ROUND} tool "
                        "calls run per turn, and this round already reached "
                        "that limit."
                    ),
                }
            )
