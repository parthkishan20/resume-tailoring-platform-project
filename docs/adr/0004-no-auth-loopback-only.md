# 0004. No authentication yet; loopback-only publishing as the interim

- **Status:** Accepted as an interim. The full authentication decision is **deferred**, per
  [`PLAN.md`](../../PLAN.md) §5 decision **D4**, and tracked as blocker **B-03**.
- **Date:** 2026-09-18
- **Addresses:** defect D-28, a P0

## Context

There is no authentication or authorization on any endpoint. No API key check, no session, no
token, no middleware of any kind. Every route is anonymous, and every row in every table is keyed
to the literal string `'default'`.

Anyone who can reach the published port can read the owner's full master resume including name,
email, phone, address and employment history; overwrite or delete it; read and clear the chat
history; **rewrite the system prompt used for every subsequent chat turn**, which is a persistent
stored prompt-injection primitive; inject arbitrary text into both generation system prompts
through the unvalidated `PUT /api/rules`; and spend the owner's LLM credits without limit, with
no rate limiting and no request size cap.

This is entirely appropriate for a localhost single-user tool and entirely inappropriate anywhere
else. `docker-compose.yml` publishes `"8000:8000"`, which binds **all** host interfaces. On a
shared network, a VPS or any cloud host, the application is fully open.

The obvious response is to add authentication. The problem with doing that now is that **the
deployment target is undecided**. Whether this ends up as a localhost tool, a single-user
container behind a reverse proxy on a personal VPS, or something multi-user determines whether
the right answer is a static API key, a reverse-proxy-terminated basic auth, an OIDC flow, or a
real user model. Building one of those and discovering it was the wrong one means building it
twice, and every one of them touches every route.

## Decision

**Do not build authentication yet. Remove the exposure instead, by publishing the container port
on the loopback interface only.**

- In `docker-compose.yml`, the mapping becomes `"127.0.0.1:8000:8000"` rather than `"8000:8000"`.
  The same change applies to both start scripts.
- **Uvicorn keeps binding `0.0.0.0` inside the container.** This is not an oversight and must not
  be "fixed". The Docker bridge cannot reach a process bound to the container's loopback, so
  changing the in-container bind breaks the app. The **host-side publish**, the left half of the
  `ports:` mapping, is what currently exposes the application. That is the only thing being
  changed.
- Full authentication is designed but not built until the deployment target is known.

Alongside this, task 2.4 removes the abuse amplifiers that make the exposure expensive rather
than merely embarrassing: rate limiting, input length and body limits, a streaming upload cap, a
scrubbed subprocess environment, a non-root container, and opaque client errors with the detail
logged server-side.

## Consequences

- **The absence of authentication becomes correct rather than dangerous.** A single-user tool
  reachable only from the machine it runs on does not need a login, and adding one would be
  friction with no security benefit.
- **It is a deployment-time control, not a code-level one**, so it is exactly one line and it can
  be got wrong by anyone who edits compose, writes a `docker run` by hand, or adds a reverse
  proxy. It is stated prominently in [`DEPLOYMENT.md`](../DEPLOYMENT.md) §6 for that reason.
- **It does not protect against anything running on the same host**, including other containers
  on the same Docker network and any process the user runs. That is accepted.
- **It blocks remote access outright.** Anyone who wants to use this from a phone or another
  machine has to solve authentication first, which is the intended outcome.
- **The tension is documented rather than resolved.** Any deployment target beyond this machine
  reopens the decision. B-03 stays open until someone answers "where does this actually run?"
- The data layer is already parameterized by `user_id`, so when identity does arrive there is a
  subject to scope on without a schema migration. The transport layer has no concept of identity
  at all, and the PDF filesystem layout has no `user_id` in the path, so those are the two places
  the work lands. See [`ARCHITECTURE.md`](../ARCHITECTURE.md) §10.

## Status of the implementation

**Not yet applied.** As of this ADR, `docker-compose.yml` still publishes `"8000:8000"`. The
change is task 2.4. Until it lands, do not run this stack on a shared network.
