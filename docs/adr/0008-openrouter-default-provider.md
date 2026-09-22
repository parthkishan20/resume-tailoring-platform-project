# 0008. Default LLM provider switched from OpenAI to OpenRouter

- **Status:** Accepted
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
