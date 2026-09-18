# 0001. Ports and adapters for the LLM, the renderer and the PDF extractor

- **Status:** Accepted
- **Date:** 2026-09-18 (records a decision taken during the original 2026-07 build)
- **Source:** [`PLAN.md`](../../PLAN.md) §2, which lists this boundary among the things that are
  kept, and §3.2, which refines it

## Context

The application depends on three external things that are slow, non-deterministic, or both:

- an LLM provider, reached over the network, whose output varies run to run
- the `rendercv` CLI, run as a subprocess, which shells out to a Typst compiler
- PyMuPDF, which parses untrusted uploaded PDFs

Every meaningful user journey touches at least one of them. If they are called directly from
route handlers, then nothing can be tested without a live API key, a network connection and a
working Typst toolchain, and the end-to-end suite becomes unrunnable in CI.

A second pressure: the provider choice was expected to change, and did. The project moved from
OpenRouter to a direct OpenAI-compatible path during the original build.

## Decision

Define the three dependencies as **ports**, implement them as **adapters**, and resolve them
through a single composition root that can be swapped wholesale.

- `ports.py` declares `LLMPort`, `PDFRenderPort` and `PDFExtractPort` as `Protocol`s, plus a
  four-member error taxonomy under `BackendError`: `LLMAuthError`, `LLMUnavailableError`,
  `RenderError`, `PDFExtractError`. Those four exceptions are the only ones the application
  translates deliberately to HTTP. (Task 1.1 has since moved the taxonomy to `core/errors.py`,
  where each class carries its own status code, and `ports.py` re-exports the names. The
  decision recorded here is unchanged; only its location is.)
- `backend/src/resumetailor/adapters.py` implements them as `LiteLLMAdapter`, `RenderCVAdapter` and
  `PyMuPDFAdapter`.
- `backend/src/resumetailor/deps.py` is the whole DI container: one `lru_cache`d factory that branches on the
  `LLM_MOCK` setting and returns either `SimulatedBackendAPI` or the real composition. Routes
  obtain it through `Depends(get_backend)`, and tests override it through
  `app.dependency_overrides`.

Persistence is deliberately **not** behind a port. `database.py` is imported directly by every
route module.

## Consequences

**What this bought.**

- A deterministic test mode exists at all. `LLM_MOCK=true` swaps the entire backend object for a
  simulator, which is why the 89-test backend suite, the e2e stack and CI all run with no network
  and no API key. That is the single highest-value property of the design.
- The provider swap from OpenRouter to OpenAI was a change inside one adapter.
- `RenderError` and `PDFExtractError` give the routes something specific to catch, which is why
  the SSE error vocabulary can distinguish a render failure from an LLM failure.

**What it did not buy, and the costs that are now being paid.**

- **The provider abstraction is nominal.** `LiteLLMAdapter.__init__` unconditionally writes
  `os.environ["OPENAI_API_KEY"]`, and the exception map names litellm's own classes. Pointing
  `LLM_MODEL` at an Anthropic or Gemini model routes correctly in litellm and then fails auth. A
  genuine second provider requires editing the adapter, not just adding one.
- **Writing the key into `os.environ` from a constructor is global mutable state**, and the
  `rendercv` child process inherits it despite having no use for it (D-49).
- **`BackendAPI` fuses all three ports into one facade.** A route that only needs PDF rendering
  receives an object that can also call the LLM. There is no interface segregation, and adding a
  second renderer means editing the facade constructor and the composition root as well as
  writing the adapter.
- **The boundary stops at these three dependencies.** Persistence, YAML normalization and prompt
  text are all direct imports in the route modules, which is why business logic ended up inside
  handlers and why the orchestration in `generate_resume_stream` cannot be unit tested without an
  HTTP client. See [`ARCHITECTURE.md`](../ARCHITECTURE.md) §4.
- The `Protocol`s are `@runtime_checkable`, which only checks method presence and never
  signatures or async-ness, and nothing performs an `isinstance` check against them anyway. The
  decorator gives false assurance.
- `SimulatedBackendAPI` dispatches on **substring matches against system prompt text**
  (`"ResumeTailor"`, `"ResumeAuditor"`, `"evaluation"`). Rewording a prompt header silently
  reroutes the simulator with no test failure at the seam.

**What changes, and what does not.** `PLAN.md` §3.2 keeps the ports and the port-per-dependency
idea and removes the facade: services take only the ports they need, repositories become ports
too, and the singleton moves from `lru_cache` to `app.state` so it is resettable. The decision
recorded here is not being reversed; it is being extended to the parts of the system it never
covered.
