# 0008. Default LLM provider switched from OpenAI to OpenRouter

- **Status:** Accepted (amended 2026-09-22, see *Amendment* below)
- **Date:** 2026-09-22
- **Addresses:** B-02's neighbouring context (`PLAN.md` §6); resolves ADR 0001's "genuine second
  provider requires editing the adapter" limitation for OpenRouter specifically

## Context

The application called OpenAI directly: `Settings.OPENAI_API_KEY` was the only provider key, and
`llm_api_key` unconditionally returned it regardless of what `LLM_MODEL` named. ADR 0001 already
flagged the cost of this: "Pointing `LLM_MODEL` at an Anthropic or Gemini model routes correctly in
litellm and then fails auth. A genuine second provider requires editing the adapter, not just
adding one."

The user asked to switch the default provider to OpenRouter (`openrouter/free`), reached through
the same `LiteLLMAdapter` — LiteLLM already supports OpenRouter natively via a `openrouter/<model>`
prefix on the model string, so no new SDK or adapter rewrite is required, only a second key and a
way to pick between the two.

## Decision

**`Settings` now declares both `OPENAI_API_KEY` and `OPENROUTER_API_KEY`.** `llm_api_key` reads
whichever one matches `LLM_MODEL`'s provider prefix: `openrouter/...` reads
`OPENROUTER_API_KEY`, anything else falls back to `OPENAI_API_KEY` (preserving the old behaviour
for a deployment that still points `LLM_MODEL` at a bare OpenAI model name). `LLM_MODEL`'s default
changed from `gpt-4o-mini` to `openrouter/free`. `validate_startup_settings` and the adapter's
auth-error message now name whichever key is actually relevant, instead of always naming
`OPENAI_API_KEY`.

This is a config-only change — `LiteLLMAdapter` itself is untouched. It was already provider-agnostic
in its call shape (`model`, `api_key`, `messages` passed straight to `litellm.acompletion`); the
only place OpenAI was hardcoded was `Settings.llm_api_key`.

## Consequences

- A fresh `.env` needs `OPENROUTER_API_KEY`, not `OPENAI_API_KEY`, to run against a real provider.
  `.env.example`, `README.md`, `docs/DEPLOYMENT.md`, `docs/TROUBLESHOOTING.md`, `docs/API.md` and
  `CONTRIBUTING.md` were updated to match.
- A deployment that wants to stay on OpenAI still can: set `LLM_MODEL` to a bare model name (e.g.
  `gpt-4o-mini`) and `OPENAI_API_KEY`; nothing about that path changed.
- ADR 0001's "genuine second provider requires editing the adapter" is now true only for a *third*
  provider (Anthropic, Gemini, ...) reached directly rather than through OpenRouter — OpenRouter
  itself proxies most of those anyway, which is the more likely path if one is ever wanted.
- OpenRouter's own reasoning-preservation pattern (`reasoning_details` passed back verbatim across
  turns) is **not** implemented by this change. It would require widening `LLMPort`'s return
  shape, a `chat_messages` schema migration, and rebuilding history in
  `domain/assistant.py::run_assistant_turn` — deferred as a separate, larger decision if the model
  behind `openrouter/free` turns out to need it for good multi-turn quality.

## Amendment (2026-09-22): the chosen default slug did not exist

The default this ADR settled on, `openrouter/free`, is not a real OpenRouter model. The provider
answers `404 {"error":{"message":"No endpoints available for openrouter/free"}}`, so a fresh
install passed `validate_startup_settings` (which only checks that a key is non-empty), booted
green, and then failed *every* generation, evaluation, chat turn and PDF import. No test caught it:
the suite runs entirely against `LLM_MOCK`'s stub, which never resolves a model name.

The default is now `openrouter/openai/gpt-oss-120b`, verified end to end against the live provider
(strict `json_schema` accepted, full tailoring pipeline to a rendered PDF).

Two things learned while picking it, both worth knowing before changing this default again:

- **Reasoning models can starve their own output.** Reasoning tokens are drawn from the same
  `LLM_MAX_TOKENS` budget as the answer. At the old 8192 default, `openai/gpt-oss-20b` spent ~92%
  of its completion on reasoning and returned empty content (`finish_reason=stop`), and
  `inclusionai/ling-3.0-flash` was truncated mid-thought (`finish_reason=length`). Both surfaced as
  `LLM_EMPTY_RESPONSE`, which reads like a provider fault and is not one.
- **A cheaper per-token price is not a cheaper pass.** Measured over the real two-call pipeline,
  `ling-3.0-flash` ($0.021/$0.063 per M) used 21,646 completion tokens against gpt-oss-120b's 4,629
  ($0.03/$0.17 per M) — 1.6x *more* expensive per resume and 3.2x slower. Compare measured
  cost-per-pass, not list price.

`LLM_MODEL` is still the only knob; nothing about the decision above changes.
