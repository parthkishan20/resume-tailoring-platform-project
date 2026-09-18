# 0005. Assistant tool calling limited to a fixed four-tool action set

- **Status:** Accepted. Recorded from [`PLAN.md`](../../PLAN.md) §5 decision **D8**, decided
  2026-09-18. Cleared blocker B-04.
- **Date:** 2026-09-18
- **Implements:** defect D-33, a P0. Built in task 3.3.

## Context

"An LLM chat assistant can perform any workstation action on the user's behalf" is one of the
three stated core principles of the product, and it does not exist. The chat route is a plain
streaming completion: no tool calling, no action parsing, no database write beyond the two chat
rows. The `done` event hardcodes `"action": null`.

The `ChatAction` type in `frontend/src/lib/types.ts` declares four action types and is imported
nowhere. `ChatDrawer`'s `onAction` prop and the `master_resume_updated` branch in `ChatPanel` are
dead wiring. Both the README and the in-app copy tell the user "changes apply directly".

So the decision is not whether to build it but how wide to make it. The spec's phrasing, "any
workstation action", reads as an argument for exposing the API surface generically: give the
model the endpoint list and let it choose. Against that: the assistant would then be able to
delete the master resume, delete generated resumes and rewrite the system prompt, all from
natural language, in an application that has no undo, no authentication (see
[ADR 0004](./0004-no-auth-loopback-only.md)) and where the job description reaching the
generation prompt is already an unguarded injection surface.

## Decision

**Four tools. No more, and no general API exposure.**

The four match the action types already declared in `types.ts`, so the frontend contract does not
change shape:

| Tool | Effect |
|---|---|
| Edit the master resume | Writes `master_resume.yaml_content` through the same validated path a manual save uses |
| Generate a tailored resume | Runs the two-pass pipeline for a given job description |
| Evaluate | Scores a resume against a job description |
| Update generation rules | Writes `generation_rules` |

Explicitly excluded:

- **No delete tool of any kind.** Not for the master resume, not for generated resumes, not for
  chat history. Deletion stays a deliberate human action.
- **No system-prompt tool.** Letting a model rewrite the prompt that governs its own future turns
  is a self-modifying loop with no upside here.
- **No generic API access**, no "call this endpoint" escape hatch, and no tool that takes a raw
  path or SQL.

## Consequences

- **The product claim becomes true**, and the copy stops describing a capability that does not
  exist. Until task 3.3 ships, the README and the in-app copy are corrected to describe what
  exists rather than what was specified.
- **The blast radius is bounded and enumerable.** Every action the assistant can take is one of
  four, each with a known effect on known rows. That is what makes it testable: four tools means
  a finite set of cases, not a combinatorial surface.
- **Nothing the assistant can do is unrecoverable.** Editing the master resume writes a history
  row first, as manual saves do. Generation adds a row rather than replacing one. Evaluation
  persists nothing. Rules are resettable to defaults.
- **The user will eventually ask for something outside the four**, most likely renaming or
  deleting a generated resume. The honest answer is to say so rather than to widen the set
  quietly. Widening it is a new ADR.
- **Every tool call must go through the same validated write path as the UI**, not a shortcut.
  Otherwise the assistant becomes a way to bypass validation that the manual path enforces, which
  matters because `PUT /api/master-resume` does not validate today and task 2.5 is what fixes
  that (D-04).
- **Tool arguments are model-authored and therefore untrusted.** They are validated exactly as a
  request body is. The existing prompt-injection surface through the job description and through
  `PUT /api/rules` makes this concrete rather than theoretical: the model can be steered by
  content it is asked to process.

## References

- [`API.md`](../API.md), `POST /api/chat/stream`, for the current `action: null` contract
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) §8 for the SSE event vocabulary the actions ride on
- `reports/audit-product.md` for the full spec-versus-implementation gap
