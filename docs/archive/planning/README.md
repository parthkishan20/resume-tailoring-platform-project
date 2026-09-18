# Archived planning tree (2026-07)

**These documents are history, not specification. Do not build against them.**

Everything in this directory describes the original 2026-07 build of ResumeTailor: the product
spec it was built from, the interface designs handed to each agent, and the step-by-step plans
those agents executed. The build completed. The implementation has since diverged from these
documents in ways that are now catalogued rather than guessed at.

The current source of truth is [`PLAN.md`](../../../PLAN.md) at the repository root, and the
current description of the system as it actually works is
[`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md).

## Why these are kept

They are preserved, not deleted, for three reasons. They record intent that the code does not
explain on its own. They are the provenance of decisions that are still live. And several of the
documented drifts between them and the code are themselves findings: `reports/audit-product.md`
§3 catalogues each one with evidence.

## What is here

| Path | What it was |
|---|---|
| `PLAN.md` | The original product specification. Still the only document that states what the product was *meant* to be, which is why the product audit draws its §1 entirely from it |
| `backend_API.md` | Backend design notes, written against OpenRouter |
| `backendAPI_interface.md` | The ports, adapters and facade interface design. Built faithfully, so it has served its purpose |
| `backend_simulator.md` | The deterministic simulator design. Accurate to what was built |
| `example-Prompt.md` | The generation and critique prompts. These now live verbatim in `backend/app/prompts.py`, which is the real source |
| `example-yaml-preview.png` | A rendered preview of the sample master resume |
| `superpowers/plans/` | Per-agent step-by-step build plans for the three original waves |
| `superpowers/specs/` | The agent-team design and the RenderCV config integration design |

The companion set, the briefs and completion reports those agents produced, is preserved
separately under [`../superpowers-sdd/`](../superpowers-sdd/), which was archived earlier under
task 0.7.

## Known divergences, so you do not act on a stale claim

These are the ones most likely to mislead. The full list is `reports/audit-product.md` §3.

- **The LLM provider is inverted.** `backend_API.md` and `backendAPI_interface.md` specify
  OpenRouter, `OPENROUTER_API_KEY`, and an `openrouter/*` model. The shipped stack is
  OpenAI-compatible litellm with `OPENAI_API_KEY` and a `gpt-4o-mini` default. A new contributor
  following those documents is set up wrong end to end.
- **The RenderCV locale flag decision was reversed.** `superpowers/specs/*-rendercv-config-integration-design.md`
  is marked "Approved" and says to pass `--locale`. That flag does not exist; the implementation
  merges the locale file into the document instead. The spec was never updated.
- **RenderCV 2.x uses Typst, not LaTeX.** `PLAN.md` §9's TeX Live package list is wrong.
  `backend_API.md` contains the correction, which is the one durable insight in that file.
- **The visual design is superseded twice over.** `PLAN.md` §2's palette and font rules describe
  neither the shipped dark and gold UI nor the approved replacement. The binding design document
  is [`docs/design/DESIGN-SYSTEM.md`](../../design/DESIGN-SYSTEM.md).
- **The API surface drifted.** `PLAN.md` §7 omits `GET /api/master-resume/preview`, and §11's
  mock payloads no longer match the simulator's output. The current reference is
  [`docs/API.md`](../../API.md).
- **The chat assistant's headline capability was never built.** These documents describe an
  assistant that performs workstation actions. It does not, yet. The scope that will be built is
  [ADR 0005](../../adr/0005-assistant-fixed-tool-set.md).

Internal links inside these files still point at the pre-archive paths (`planning/...`,
`docs/superpowers/...`). They have been left as written, since rewriting the contents of an
archive would defeat the point of keeping it.

## What is deliberately not here

`planning/master-resume.yaml` stays where it is, outside this archive. It contains real personal
data and is gitignored (defect D-01). `planning/example-master-resume.yaml` also stays, as the
tracked sample document.
