"""Task 3.3: tool calling, exercised without an HTTP layer or a real provider.

D-33's core loop -- stream the model, run whatever tools it asks for, feed the
results back, repeat -- lives in `domain.assistant.run_assistant_turn`. This
mirrors `test_domain_tailoring.py`'s approach: a scripted fake behind the
`BackendAPI` shape, driven directly, so the tool taxonomy (ADR 0005 / PLAN.md
D8) can be pinned one tool at a time rather than inferred from an SSE stream.
"""

from __future__ import annotations

import json

import pytest

from resumetailor.backend_api import BackendAPI
from resumetailor.core.errors import LLMUnavailableError, RenderError
from resumetailor.db.repositories import (
    get_master_resume,
    get_resume,
    get_rules,
    upsert_master_resume,
)
from resumetailor.domain.assistant import (
    MAX_TOOL_ITERATIONS,
    AssistantAction,
    AssistantReply,
    run_assistant_turn,
)
from resumetailor.llm.port import StreamEvent, ToolCall

VALID_YAML = "cv:\n  name: Tester\n  email: tester@example.com\n"
INVALID_YAML = "cv:\n  name: [not, a, mapping]\n"
JD = "Senior Python role"
NOT_USED = "not used by the assistant"


class ScriptedAssistantAPI:
    """Fills `BackendAPI`'s shape: `stream()` for the turn, `complete()` and
    `render()` for whatever a tool's own domain call needs underneath it.
    """

    def __init__(
        self,
        *,
        stream_rounds: list[list[StreamEvent]],
        complete_responses: list[str] | None = None,
        render_bytes: bytes = b"%PDF-1.4 mock",
        render_error: Exception | None = None,
    ) -> None:
        self._rounds = stream_rounds
        self._round = 0
        self._complete_responses = list(complete_responses or [])
        self._render_bytes = render_bytes
        self._render_error = render_error
        self.stream_calls: list[tuple[list[dict], object]] = []
        self.complete_calls: list[list[dict]] = []

    async def stream(self, messages: list[dict], tools: object = None):
        self.stream_calls.append((messages, tools))
        index = min(self._round, len(self._rounds) - 1)
        events = self._rounds[index]
        self._round += 1

        async def _gen():
            for event in events:
                yield event

        return _gen()

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        self.complete_calls.append(messages)
        return self._complete_responses.pop(0)

    async def render(self, yaml_content: str) -> bytes:
        if self._render_error is not None:
            raise self._render_error
        return self._render_bytes

    async def extract(self, pdf_bytes: bytes) -> str:
        raise AssertionError(NOT_USED)


def build_api(**kwargs: object) -> BackendAPI:
    return ScriptedAssistantAPI(**kwargs)  # type: ignore[arg-type,return-value]


async def run(api: BackendAPI, db_path: str, pdfs_dir: str, message: str = "hi"):
    events = []
    async for event in run_assistant_turn(
        api,
        db_path=db_path,
        pdfs_dir=pdfs_dir,
        messages=[
            {"role": "system", "content": "You are ResumeTailor."},
            {"role": "user", "content": message},
        ],
    ):
        events.append(event)
    return events


def tool_call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=json.dumps(arguments))


# ── Plain text: no tool involved ────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_plain_reply_needs_only_one_round(db_path, pdfs_dir):
    api = build_api(stream_rounds=[["Hello", " there"]])

    events = await run(api, db_path, pdfs_dir)

    assert events == [
        "Hello",
        " there",
        AssistantReply(text="Hello there", action=None),
    ]
    assert len(api.stream_calls) == 1  # type: ignore[attr-defined]


# ── edit_master_resume ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_edit_master_resume_writes_through_and_reports_the_action(
    db_path, pdfs_dir
):
    api = build_api(
        stream_rounds=[
            [tool_call("edit_master_resume", {"yaml_content": VALID_YAML})],
            ["Updated."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(
        text="Updated.", action=AssistantAction(type="master_resume_updated")
    )
    stored = get_master_resume(db_path)
    assert stored is not None
    assert stored.yaml_content == VALID_YAML


@pytest.mark.anyio
async def test_edit_master_resume_refuses_a_document_that_will_not_render(
    db_path, pdfs_dir
):
    """D-33's explicit hazard: this tool must not inherit D-04's open gap."""
    upsert_master_resume(db_path, VALID_YAML)
    api = build_api(
        stream_rounds=[
            [tool_call("edit_master_resume", {"yaml_content": INVALID_YAML})],
            ["It looks like that would not render."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(
        text="It looks like that would not render.", action=None
    )
    # Refused, not stored: the master resume from before the call is untouched.
    assert get_master_resume(db_path).yaml_content == VALID_YAML

    # The model saw why, not a raw exception.
    tool_result = api.stream_calls[1][0][-1]  # type: ignore[attr-defined]
    assert tool_result["role"] == "tool"
    assert "not valid" in tool_result["content"]


# ── generate_tailored_resume ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_generate_tailored_resume_runs_the_pipeline_and_stores_the_result(
    db_path, pdfs_dir
):
    upsert_master_resume(db_path, VALID_YAML)
    draft = json.dumps({"yaml_content": VALID_YAML})
    api = build_api(
        stream_rounds=[
            [tool_call("generate_tailored_resume", {"job_description": JD})],
            ["Done, take a look."],
        ],
        complete_responses=[draft, VALID_YAML],
    )

    events = await run(api, db_path, pdfs_dir)

    reply = events[-1]
    assert isinstance(reply, AssistantReply)
    assert reply.action is not None
    assert reply.action.type == "resume_generated"
    assert reply.action.resume_id is not None
    stored = get_resume(db_path, reply.action.resume_id)
    assert stored is not None
    assert stored.job_description == JD


@pytest.mark.anyio
async def test_generate_tailored_resume_without_a_master_resume_fails_softly(
    db_path, pdfs_dir
):
    api = build_api(
        stream_rounds=[
            [tool_call("generate_tailored_resume", {"job_description": JD})],
            ["There's nothing to tailor yet."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(
        text="There's nothing to tailor yet.", action=None
    )


@pytest.mark.anyio
async def test_a_render_failure_becomes_the_client_message_not_the_raw_detail(
    db_path, pdfs_dir
):
    """D-53's pattern, reused: the tool result must never carry `str(exc)`."""
    upsert_master_resume(db_path, VALID_YAML)
    draft = json.dumps({"yaml_content": VALID_YAML})
    api = build_api(
        stream_rounds=[
            [tool_call("generate_tailored_resume", {"job_description": JD})],
            ["Sorry, that did not work."],
        ],
        complete_responses=[draft, VALID_YAML],
        render_error=RenderError("subprocess stderr: /app/internal/path leaked here"),
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(text="Sorry, that did not work.", action=None)
    tool_result = api.stream_calls[1][0][-1]  # type: ignore[attr-defined]
    assert tool_result["content"] == RenderError.client_message
    assert "/app/internal/path" not in tool_result["content"]


# ── evaluate_resume ──────────────────────────────────────────────────────────


def _evaluation_json(score: int = 80) -> str:
    return json.dumps(
        {
            "match_score": score,
            "critique": "Solid overall.",
            "matched_keywords": ["Python"],
            "missing_keywords": ["Kubernetes"],
        }
    )


@pytest.mark.anyio
async def test_evaluate_resume_defaults_to_the_master_resume(db_path, pdfs_dir):
    upsert_master_resume(db_path, VALID_YAML)
    api = build_api(
        stream_rounds=[
            [tool_call("evaluate_resume", {"job_description": JD})],
            ["It scored 80."],
        ],
        complete_responses=[_evaluation_json(80)],
    )

    events = await run(api, db_path, pdfs_dir)

    reply = events[-1]
    assert isinstance(reply, AssistantReply)
    assert reply.action == AssistantAction(type="evaluated", resume_id=None)


@pytest.mark.anyio
async def test_evaluate_resume_can_target_a_generated_resume(db_path, pdfs_dir):
    upsert_master_resume(db_path, VALID_YAML)
    from resumetailor.db.repositories import create_resume

    generated = create_resume(db_path, "Existing", JD, VALID_YAML)
    api = build_api(
        stream_rounds=[
            [
                tool_call(
                    "evaluate_resume",
                    {"job_description": JD, "resume_id": generated.id},
                )
            ],
            ["Scored."],
        ],
        complete_responses=[_evaluation_json(60)],
    )

    events = await run(api, db_path, pdfs_dir)

    reply = events[-1]
    assert isinstance(reply, AssistantReply)
    assert reply.action == AssistantAction(type="evaluated", resume_id=generated.id)


@pytest.mark.anyio
async def test_evaluate_resume_with_an_unknown_id_fails_softly(db_path, pdfs_dir):
    api = build_api(
        stream_rounds=[
            [tool_call("evaluate_resume", {"job_description": JD, "resume_id": 999})],
            ["I couldn't find that resume."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(
        text="I couldn't find that resume.", action=None
    )


# ── update_generation_rules ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_update_generation_rules_writes_through_and_leaves_others_alone(
    db_path, pdfs_dir
):
    before = {(r.section, r.rule_key): r.rule_value for r in get_rules(db_path)}
    assert before, (
        "the seeded defaults must be non-empty for this test to mean anything"
    )

    api = build_api(
        stream_rounds=[
            [
                tool_call(
                    "update_generation_rules",
                    {
                        "rules": [
                            {
                                "section": "experience",
                                "rule_key": "max_bullets",
                                "rule_value": "2",
                            }
                        ]
                    },
                )
            ],
            ["Updated your rules."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(
        text="Updated your rules.", action=AssistantAction(type="rules_updated")
    )
    after = {(r.section, r.rule_key): r.rule_value for r in get_rules(db_path)}
    assert after[("experience", "max_bullets")] == "2"
    untouched = {k: v for k, v in before.items() if k != ("experience", "max_bullets")}
    for key, value in untouched.items():
        assert after[key] == value


@pytest.mark.anyio
async def test_update_generation_rules_rejects_an_oversized_field(db_path, pdfs_dir):
    api = build_api(
        stream_rounds=[
            [
                tool_call(
                    "update_generation_rules",
                    {
                        "rules": [
                            {
                                "section": "x" * 500,
                                "rule_key": "k",
                                "rule_value": "v",
                            }
                        ]
                    },
                )
            ],
            ["That value was too long."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(text="That value was too long.", action=None)
    tool_result = api.stream_calls[1][0][-1]  # type: ignore[attr-defined]
    assert "invalid" in tool_result["content"]


# ── Malformed and unknown calls ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_malformed_json_arguments_do_not_crash_the_turn(db_path, pdfs_dir):
    api = build_api(
        stream_rounds=[
            [ToolCall(id="1", name="edit_master_resume", arguments="{not json")],
            ["Something went wrong with that."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(
        text="Something went wrong with that.", action=None
    )


@pytest.mark.anyio
async def test_an_unknown_tool_name_is_reported_not_executed(db_path, pdfs_dir):
    api = build_api(
        stream_rounds=[
            [tool_call("delete_everything", {})],
            ["I can't do that."],
        ]
    )

    events = await run(api, db_path, pdfs_dir)

    assert events[-1] == AssistantReply(text="I can't do that.", action=None)
    tool_result = api.stream_calls[1][0][-1]  # type: ignore[attr-defined]
    assert "not an action" in tool_result["content"]


# ── The round budget ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_the_turn_finalizes_at_the_round_budget_even_if_pressed_for_more(
    db_path, pdfs_dir
):
    """A model that keeps asking for tools cannot hold the stream open forever.

    Every round here answers with a tool call, including a round the loop asks
    with no `tools` at all -- which a real provider could never do, but the
    fake ignores the argument on purpose to prove the *loop* finalizes
    unconditionally on that round rather than by trusting the provider not to.
    """
    forever_calling = [
        [
            tool_call(
                "update_generation_rules",
                {"rules": [{"section": "s", "rule_key": "k", "rule_value": str(n)}]},
            )
        ]
        for n in range(MAX_TOOL_ITERATIONS + 1)
    ]
    api = build_api(stream_rounds=forever_calling)

    events = await run(api, db_path, pdfs_dir)

    assert len(api.stream_calls) == MAX_TOOL_ITERATIONS + 1  # type: ignore[attr-defined]
    assert isinstance(events[-1], AssistantReply)
    # The last round's own tool call is never executed: the round it arrived
    # on had no tools offered, so nothing acts on it. Only rounds 0..budget-1
    # ran, leaving "k" at the second-to-last round's value.
    written = {(r.section, r.rule_key): r.rule_value for r in get_rules(db_path)}
    assert written[("s", "k")] == str(MAX_TOOL_ITERATIONS - 1)


@pytest.mark.anyio
async def test_a_second_round_answers_in_text_once_tools_have_run(db_path, pdfs_dir):
    upsert_master_resume(db_path, VALID_YAML)
    api = build_api(
        stream_rounds=[
            [tool_call("edit_master_resume", {"yaml_content": VALID_YAML})],
            ["All set."],
        ]
    )

    await run(api, db_path, pdfs_dir)

    # Round 2's request carries the tool call and its result, ahead of the
    # original system and user turns.
    second_round_messages = api.stream_calls[1][0]  # type: ignore[attr-defined]
    roles = [m["role"] for m in second_round_messages]
    assert roles == ["system", "user", "assistant", "tool"]
