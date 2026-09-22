# API reference

Every HTTP endpoint the backend serves, as it actually behaves today. Built on the verified
table in [`reports/audit-backend.md`](./reports/audit-backend.md) §2 and re-checked against
`backend/src/resumetailor/api/routers/*.py`.

Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) §4 for how a request reaches a handler, and §8 for
how the streaming routes work.

---

## 0. Read this before you use anything below

Four properties of this API are unusual enough that treating them as normal will cost you time.

**1. There is no `response_model` anywhere.** Not on a single route. Every handler returns a raw
`dict` built from a `sqlite3.Row`, and several of them come from `SELECT *`. Three consequences:

- `/openapi.json` documents **every** response body as `{}`. The generated spec is useless as a
  contract.
- The frontend's types in `frontend/src/lib/types.ts` are hand-written and unenforced on both
  ends.
- Any column added to a table silently joins the public API.

Every "Response" shape in this document is therefore the **observed runtime shape**, not a
declared contract. It can drift without anything failing.

**2. Streaming failures return HTTP 200.** All three SSE routes wrap their entire body in a
`try/except` *inside* the generator. The response status is committed before the first frame, so
a total LLM outage is an HTTP 200 carrying `event: error`. The global exception handlers never
fire for these routes. Check the event name, never the status code.

**3. `DELETE` is inconsistent.** Three routes return `204` with no body. Two return `200` with a
full body, because they are semantically "reset" rather than "delete":

| Route | Status | Body |
|---|---|---|
| `DELETE /api/master-resume` | 204 | empty |
| `DELETE /api/resumes/{id}` | 204 | empty |
| `DELETE /api/chat` | 204 | empty |
| `DELETE /api/rules` | **200** | the full rules array, reset to defaults |
| `DELETE /api/system-prompt` | **200** | the system-prompt row, reset to default |

The API client handles both (`frontend/src/lib/api.ts` returns early on 204 and on any empty
body), but anything else calling this API must too. This inconsistency was previously a live
bug: `res.json()` on an empty body rejects with `Unexpected end of JSON input`, which made all
three 204 flows fail on success (D-31, fixed in task 0.1).

**4. Two error shapes coexist.** See §4.

**There is no authentication on any endpoint.** See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §10
and [ADR 0004](./adr/0004-no-auth-loopback-only.md).

---

## 1. Endpoint table

| Method | Path | Request | Response (observed) | Status codes | Streaming |
|---|---|---|---|---|---|
| GET | `/api/health` | none | `{"status":"ok"}` | 200 | no |
| GET | `/api/master-resume` | none | `{id, user_id, yaml_content, updated_at}` | 200, 404 | no |
| PUT | `/api/master-resume` | `{yaml_content: str}` | same row | 200, 422 | no |
| DELETE | `/api/master-resume` | none | empty | 204, 404 | no |
| GET | `/api/master-resume/preview` | none | `application/pdf` bytes | 200, 404, 422 | no |
| POST | `/api/master-resume/import` | `multipart/form-data`, field `file` | master-resume row | 200, 400, 422, 500 | no |
| GET | `/api/resumes` | query `sort`, `order`, `page`, `limit` | `{items: [...], total, page, limit}` | 200, 422 | no |
| POST | `/api/resumes/stream` | `{job_description: str}` | `text/event-stream` | **200 always** | SSE |
| GET | `/api/resumes/{id}` | path int | full row, `SELECT *` | 200, 404, 422 | no |
| PATCH | `/api/resumes/{id}` | `{name?, yaml_content?}` | full row, `SELECT *` | 200, 404, 422 | no |
| GET | `/api/resumes/{id}/pdf` | path int | PDF, `Content-Disposition: inline` | 200, 404 | no |
| POST | `/api/resumes/{id}/render` | path int | full row, `SELECT *` | 200, 404, 500 | no |
| DELETE | `/api/resumes/{id}` | path int | empty | 204, 404 | no |
| GET | `/api/chat` | none | `[{id, user_id, role, content, created_at}]` | 200 | no |
| POST | `/api/chat/stream` | `{message: str}` | `text/event-stream` | **200 always** | SSE |
| DELETE | `/api/chat` | none | empty | 204 | no |
| GET | `/api/rules` | none | `[{section, rule_key, rule_value}]` | 200 | no |
| PUT | `/api/rules` | `{rules: [{section, rule_key, rule_value}]}` | rules array | 200, 422 | no |
| DELETE | `/api/rules` | none | **rules array, 200** | 200 | no |
| GET | `/api/system-prompt` | none | `{id, user_id, content, updated_at}` | 200, 404 | no |
| PUT | `/api/system-prompt` | `{content: str}` | full row, `SELECT *` | 200, 422 | no |
| DELETE | `/api/system-prompt` | none | **row, 200** | 200 | no |
| GET | `/docs`, `/redoc`, `/openapi.json` | none | FastAPI interactive docs | 200 | no |
| GET | `/{path:path}` | none | the frontend static export | 200, 404 | no |

`/docs`, `/redoc` and `/openapi.json` are served unconditionally, in every environment, with no
auth (D-58).

---

## 2. Endpoints in detail

### Health

#### `GET /api/health`

Returns the literal `{"status": "ok"}`. It **touches nothing**: not SQLite, not `PDFS_DIR`, not
the `rendercv` binary, not the LLM. A container with a corrupt database reports itself healthy
and keeps receiving traffic. Both the Dockerfile `HEALTHCHECK` and both compose healthchecks
point at it. See [`DEPLOYMENT.md`](./DEPLOYMENT.md) §5.

> **Target, not built yet.** A liveness and readiness split, where readiness does `SELECT 1`,
> checks `PDFS_DIR` is writable and confirms `rendercv` is on `PATH`. Task 3.5.

---

### Master resume

#### `GET /api/master-resume`

`200` with `{id, user_id, yaml_content, updated_at}`, or `404` with
`{"detail": "No master resume found"}` when no row exists.

The 404 is load-bearing on the client: `api.getMasterResume()` maps **only** a 404 to `null`, and
every other failure reaches the shell as an error state. Before task 0.2 a blanket catch made a
500 indistinguishable from a 404, which routed the user to onboarding whose "Start from Sample"
button immediately overwrites the real resume (D-32).

#### `PUT /api/master-resume`

Body `{yaml_content: str}`. Returns the stored row.

**The body is not validated in any way.** No `safe_load`, no normalization, no schema check, no
length bound. Arbitrary text becomes the canonical source document for every downstream render,
and the failure surfaces much later, at preview or generation time (D-04). Contrast
`POST /api/master-resume/import`, which does normalize.

Side effect: the *previous* body is written to `master_resume_history` and that table is pruned
to its newest 10 rows. Nothing reads that history; there is no endpoint for it.

#### `DELETE /api/master-resume`

`204` with an empty body, or `404` if there was nothing to delete. Leaves the resume's
`master_resume_history` rows orphaned (D-14).

#### `GET /api/master-resume/preview`

Renders the stored master resume to PDF and returns `application/pdf` bytes.

- `404` if there is no master resume.
- `422` if the render fails. Note this is **different from every other render path**: this
  handler catches `RenderError` and converts it to a 422, while `POST /api/resumes/{id}/render`
  lets it reach the global handler and become a 500 (D-58 territory; `reports/audit-backend.md`
  P2-2).

This route normalizes the YAML before rendering. `POST /api/resumes/{id}/render` does not, so
identical YAML can render through one path and fail through the other (D-57).

#### `POST /api/master-resume/import`

`multipart/form-data` with a `file` field. Extracts text with PyMuPDF, sends it to the LLM with a
schema-constrained prompt, normalizes the result, and upserts it as the master resume. Returns
the stored row.

- `400` if `file.content_type != "application/pdf"`. That header is client-supplied and trivially
  spoofed; the only real validation is PyMuPDF opening the stream.
- `422` via the `PDFExtractError` handler: over 10 MB, over 50 pages, or unopenable.
- `500`, **unhandled**, if the provider returns `None` content or non-JSON. There is no
  `try/except` around the `json.loads` in this handler (D-59).

The 10 MB guard lives inside the extractor, which means it runs **after**
`pdf_bytes = await file.read()` has already materialized the whole body in memory. A 2 GB POST
OOMs the container before the guard is reached (D-48).

---

### Generated resumes

#### `GET /api/resumes`

Query parameters, all unvalidated:

| Param | Default | Behaviour |
|---|---|---|
| `sort` | `date` | Any value other than `"date"` silently falls back to sorting by `job_description` |
| `order` | `desc` | Whitelisted against a closed set, so not injectable |
| `page` | `1` | `page=0` produces a negative `OFFSET` |
| `limit` | `20` | **`limit=-1` reaches SQLite as `LIMIT -1`, which SQLite reads as no limit, and dumps every row** (D-10) |

Returns `{items: [...], total, page, limit}`. The `items` rows use an explicit column list that
**omits `yaml_content`**, unlike `GET /api/resumes/{id}`, which returns `SELECT *`. Two different
"resume" shapes live under the same resource.

#### `POST /api/resumes/stream`

The two-pass generation pipeline. See §3 for the event sequence and
[`ARCHITECTURE.md`](./ARCHITECTURE.md) §5 for what each pass does.

Body `{job_description: str}`, a bare `str` with no `max_length`. Starlette imposes no default
body cap, so a 50 MB body is accepted, persisted and forwarded to the provider, twice (D-47).

The generated resume's display name is built as the word `Resume`, an em dash, and the first 40
characters of the job description: a truncated slice of caller-supplied text stored unsanitized.

#### `GET /api/resumes/{id}`

`SELECT *` row including `yaml_content` and the full `job_description`. `404` if absent.

#### `PATCH /api/resumes/{id}`

Body `{name?: str, yaml_content?: str}`. Returns the updated `SELECT *` row.

Two things to know:

- `yaml_content` is stored **without normalization or validation**. Invalid YAML is accepted here
  and only discovered later, at `POST /api/resumes/{id}/render`.
- `pdf_path` is left pointing at the PDF rendered from the **old** YAML, with no invalidation
  flag. `GET /api/resumes/{id}/pdf` then serves stale content (D-57).

The schema deliberately omits `pdf_path`. `update_resume` in `database.py` does accept a
`pdf_path` kwarg, so exposing it here would turn the unchecked `Path` join in the PDF read and
delete handlers into directory traversal (D-25). Do not add it without a containment guard.

#### `GET /api/resumes/{id}/pdf`

`FileResponse` with `Content-Disposition: inline`. `404` if the row is missing, if `pdf_path` is
null, or if the file is absent from `PDFS_DIR`.

#### `POST /api/resumes/{id}/render`

Re-renders the stored YAML and overwrites `PDFS_DIR/{id}.pdf`. Returns the updated row.

Does **not** normalize the YAML first, unlike `GET /api/master-resume/preview`. A `RenderError`
here reaches the global handler and becomes a `500` with `{"error": ..., "code": "RENDER_FAILED"}`,
where the preview path would have returned a 422 for the same input.

#### `DELETE /api/resumes/{id}`

`204` empty, or `404`. Deletes the row first and unlinks the PDF second, so a failed unlink
raises after the row is already gone (D-20).

---

### Chat

#### `GET /api/chat`

Returns **every message ever**, as a bare array. No pagination, no limit (D-21).

#### `POST /api/chat/stream`

Body `{message: str}`, unbounded. The only genuinely streaming endpoint.

Sequence: persist the user turn, load the **entire** history and slice the last 30 in Python,
read the system prompt from the `system_prompt` table (falling back to a divergent hardcoded
string if the row is missing), then stream deltas.

**The `done` event always carries `"action": null`.** There is no tool calling, no action
parsing and no database write beyond the two chat rows. The in-app copy claiming "changes apply
directly" describes something that does not exist (D-33). The scope for the version that will
exist is [ADR 0005](./adr/0005-assistant-fixed-tool-set.md).

The user turn is committed **before** the LLM call, so any failure leaves a user message
persisted with no assistant reply, permanently skewing the history replayed into every future
turn.

#### `DELETE /api/chat`

`204`, empty body. Always succeeds, even when there was nothing to clear.

---

### Rules

Generation rules are `(section, rule_key, rule_value)` triples. They are appended to **both**
system prompts of the generation pipeline by `rules_block()`, formatted as
`- {section}.{rule_key} = {rule_value}` under a header telling the model they override any
conflicting counts.

#### `GET /api/rules`

Bare array of `{section, rule_key, rule_value}`.

#### `PUT /api/rules`

Body `{rules: [{section, rule_key, rule_value}]}`. All three fields are bare `str` with no
validation, no whitelist and no length bound.

This is a **user-writable path into the system prompt**. Combined with the absence of
authentication, an anonymous caller injects arbitrary text into both the generation and the
critique prompt.

#### `DELETE /api/rules`

**`200` with the full rules array**, reset to the seeded defaults. Not a 204, because this is a
reset rather than a delete.

---

### System prompt

#### `GET /api/system-prompt`

`{id, user_id, content, updated_at}`, or `404`. Seeded on first boot from
`DEFAULT_SYSTEM_PROMPT`.

#### `PUT /api/system-prompt`

Body `{content: str}`, unbounded. Returns the `SELECT *` row.

This replaces the system prompt used for **every subsequent chat turn**. With no authentication
in front of it, it is a persistent stored prompt-injection primitive (D-28).

#### `DELETE /api/system-prompt`

**`200` with the row**, reset to `DEFAULT_SYSTEM_PROMPT`. Not a 204.

---

## 3. SSE contract

Three routes stream. The wire format is `event: <name>\ndata: <json>\n\n`. The client reads it
with a hand-rolled parser (`frontend/src/lib/sse.ts`) because the streams are `POST` bodies and
`EventSource` cannot issue those.

**Headers:** only `Cache-Control: no-cache` is set. There is no `X-Accel-Buffering: no`, no
`Connection: keep-alive` and no keepalive comment frames, so an idle reverse proxy may cut a
long two-pass generation.

### `POST /api/resumes/stream`

```
event: progress   data: {"message": "Analyzing job description..."}
event: progress   data: {"message": "Tailoring content..."}
event: progress   data: {"message": "Rendering PDF..."}
event: done       data: {"result": {<generated_resumes row>}}
```

The three `progress` messages are fixed strings emitted at fixed points, not real progress.
"Rendering PDF..." is emitted **before** the render starts, and nothing is emitted during it, so
a slow Typst compile looks like a hang.

Error codes on this route: `NO_MASTER_RESUME`, `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`,
`RENDER_FAILED`, `PDF_EXTRACT_FAILED`, `GENERATION_FAILED`.

### `POST /api/chat/stream`

```
event: token   data: {"delta": "..."}     (repeated)
event: done    data: {"result": {"text": "<full text>", "action": null}}
```

Error codes: `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`, `CHAT_FAILED`.

### `POST /api/evaluate/stream`

Body `{yaml_content: str, job_description: str}`, both unbounded.

```
event: progress   data: {"message": "Analyzing resume and job description..."}
event: done       data: {"result": {"match_score": 0, "critique": "...",
                                    "matched_keywords": [], "missing_keywords": []}}
```

Error codes: `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`, `EVALUATION_FAILED`.

This is the only LLM endpoint with **no persistence**. Results are streamed and discarded.

### The error frame

Every SSE error is the same shape, at HTTP 200:

```
event: error   data: {"error": "<message>", "code": "<CODE>"}
```

The `error` string is `str(exc)`. For `RENDER_FAILED` that is the full concatenated stdout and
stderr of the `rendercv` CLI, including absolute container paths, Rich box-drawing characters,
ANSI escapes and Python tracebacks, shipped verbatim to the browser (D-53).

---

## 4. Error shapes

There are **two**, and the client has to handle both.

**Shape A, from the domain error hierarchy in `backend/src/resumetailor/core/errors.py`:**

```json
{"error": "<message>", "code": "<MACHINE_CODE>"}
```

| Exception | Status | `code` |
|---|---|---|
| `LLMAuthError` | **500** | `LLM_AUTH_ERROR` |
| `LLMUnavailableError` | 503 | `LLM_UNAVAILABLE` |
| `RenderError` | 500 | `RENDER_FAILED` |
| `PDFExtractError` | 422 | `PDF_EXTRACT_FAILED` |

`LLMAuthError` mapping to **500** is worth noting: a server misconfiguration is presented as an
internal error, carrying the literal text "Invalid LLM API key (check OPENAI_API_KEY /
OPENROUTER_API_KEY)" to the client.

**Shape B, from every `HTTPException`:**

```json
{"detail": "<message>"}
```

That covers every 404 and every 400 in the API, plus FastAPI's own 422 validation errors (where
`detail` is an array of objects, not a string).

`frontend/src/lib/api.ts` reads `detail` first, then `error`, and preserves `code` and `status`
on an exported `ApiError` (task 0.1). Nothing in the UI yet *branches* on `code`, so the
interface cannot distinguish "configure your API key" from "the renderer crashed" (D-42).

Neither shape carries a request id **in the body**. Every response does carry one in the
`X-Request-ID` header, assigned (or reused from an inbound header of the same name) by
`RequestContextMiddleware`, and the domain error handler logs the failure with that id before it
serialises the response. So a user-reported error is correlatable server-side if the user can
supply the header value, which no part of the UI currently surfaces.

> **Target, not built yet.** One error envelope for both shapes, `response_model` on every
> route, an OpenAPI export gate, generated TypeScript types with zod validation at the boundary,
> bounded pagination, and a real status code on SSE failures that occur before the first frame.
> Task 2.2.

---

## 5. Request size and rate limits

There are none.

- No `max_length` on any of the five free-text request models (`ChatRequest.message`,
  `GenerateRequest.job_description`, `EvaluateRequest.yaml_content` and `.job_description`,
  `SystemPromptBody.content`, `MasterResumeBody.yaml_content`).
- No body-size middleware. Starlette imposes no default.
- No rate limiting on any endpoint, including the four that call the LLM.
- No timeout, retry, backoff or `max_tokens` on any LLM call.
- No `Content-Length` check before the upload read.

Every one of those is registered (D-46, D-47, D-48) and owned by task 2.4. Until then, the only
control is not exposing the port. See [`DEPLOYMENT.md`](./DEPLOYMENT.md) §6.
