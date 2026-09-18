"""The hardening that has nowhere else to live: limits, allowlists, containment.

This module is the `security` role's one owned file (AGENTS.md section 2). It
holds the policy — the numbers, the allowlists, the containment helpers — and
`core/middleware.py` holds the two ASGI middlewares that enforce the parts of
it that are enforced per request. Splitting it that way keeps every tunable in
one reviewable place instead of spread across five routers.

What is here, and which defect each piece closes:

* **Input length bounds** (PLAN.md D-47). Five request models took a bare
  ``str``. The constants below are their bounds; the models reference them.
* **A bounded upload read** (D-48). :func:`read_upload_capped` replaces
  ``await file.read()``, which materialised the whole body before the 10 MB
  check in the PDF extractor could run.
* **Request body caps** (D-47's other half). Starlette imposes no default body
  size limit at all, so :class:`SecurityPolicy` carries one and
  ``BodySizeLimitMiddleware`` enforces it before the body is buffered.
* **Rate limiting** on the four endpoints that spend money (D-28's cost half).
* **A scrubbed subprocess environment** (D-49). :func:`subprocess_env` is the
  allowlist handed to the ``rendercv`` child, which otherwise inherits
  ``OPENAI_API_KEY`` from the container environment.
* **Path containment** (D-25). :func:`resolve_within` is the guard on the two
  places a database-sourced filename is joined to ``PDFS_DIR``.

On authentication
-----------------
There is none, deliberately. See PLAN.md decision **D4** and
``docs/adr/0004-no-auth-loopback-only.md``: the deployment target is undecided,
so the interim control is the *host-side port publish*
(``"127.0.0.1:8000:8000"`` in ``docker-compose.yml``) rather than a guessed-at
auth model. Everything in this module is a limit on abuse, not a gate on
access. Do not read the presence of this file as evidence that the API is
protected.

On CORS
-------
**There is no CORS middleware, and adding one would be a serious mistake.** The
frontend is same-origin: ``main.py`` mounts the Next.js static export at ``/``
in the same FastAPI process that serves ``/api/*``, so the browser never makes
a cross-origin request and no ``Access-Control-Allow-Origin`` header is needed.
If a CORS error ever appears, it means the frontend has moved to a separate
origin, and the reflexive fix — ``CORSMiddleware`` with
``allow_origins=["*"]``, or worse, with ``allow_credentials=True`` — would turn
a completely unauthenticated API into one that any web page in the world can
drive on the user's behalf: read the owner's full master resume and PII,
overwrite it, rewrite the stored system prompt used for every future chat turn,
and spend the owner's LLM credits. The rate limiter below caps the bill, not
the disclosure. Read D4 first and solve authentication, then CORS; not the
other way round.
"""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from resumetailor.core.errors import RequestTooLargeError

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.datastructures import UploadFile

# ── Input length bounds (D-47) ───────────────────────────────────────────────
#
# Pydantic's `max_length` counts *characters*, not bytes, so a body of
# `max_length` astral-plane characters is up to four times these numbers on the
# wire. The body caps in `SecurityPolicy` below are the byte-level bound; these
# are the "is this a plausible resume input" bound, and they are what keeps an
# absurd string out of the database and off the provider bill.
#
# Every number is a generous multiple of the realistic case, because the cost
# of being wrong in one direction is a rejected legitimate paste and in the
# other is a slightly larger prompt.

#: One chat turn. A long question to the assistant is a few hundred characters.
MAX_CHAT_MESSAGE_CHARS: Final = 10_000

#: One job description. A verbose enterprise posting is 4-6 KB of text.
MAX_JOB_DESCRIPTION_CHARS: Final = 20_000

#: One resume document as RenderCV YAML. The sample master resume in
#: `planning/` is about 12 KB; a very long academic CV might reach 40 KB.
MAX_RESUME_YAML_CHARS: Final = 100_000

#: The stored system prompt. The seeded default is well under 4 KB.
MAX_SYSTEM_PROMPT_CHARS: Final = 20_000

#: The uploaded PDF, in bytes. Matches `pdf.extract.MAX_BYTES`, which is the
#: check this one exists to run *before* rather than after the allocation.
MAX_PDF_UPLOAD_BYTES: Final = 10 * 1024 * 1024


# ── Per-request policy ───────────────────────────────────────────────────────

#: The endpoints that call a provider, and therefore the endpoints where an
#: unauthenticated caller can spend the owner's money. Matched on path alone:
#: each of these routes accepts exactly one method.
RATE_LIMITED_PATHS: Final = frozenset(
    {
        "/api/chat/stream",
        "/api/resumes/stream",
        "/api/evaluate/stream",
        "/api/master-resume/import",
    }
)

#: Paths whose body is a file upload and so gets the larger of the two body
#: caps. Everything else on this API is small JSON.
UPLOAD_PATHS: Final = frozenset({"/api/master-resume/import"})


class SecurityPolicy(BaseSettings):
    """The tunable half of this module, read once from the environment.

    Deliberately *not* part of ``core.config.Settings``, for the same reason
    ``rendering.config.RenderProfile`` is not: ``Settings`` is process-wide
    configuration every module reads, and these five knobs are read by two
    middlewares and one route. The ``SECURITY_`` prefix keeps the env names
    from colliding with anything.

    Every field is overridable, e.g. ``SECURITY_RATE_LIMIT_PER_MINUTE=60`` to
    loosen the limiter, or ``SECURITY_RATE_LIMIT_ENABLED=false`` to turn it off
    (which the test harness does, so that a suite making nine calls to four
    rate-limited endpoints is not measuring the limiter by accident).
    """

    #: Whether the limiter runs at all. On by default: with no authentication
    #: (D4) this is the only backstop against a single client draining the
    #: owner's provider credits.
    rate_limit_enabled: bool = True

    #: Bucket capacity: how many requests a client may make back to back after
    #: an idle period. A human using the app clicks Generate, waits ~30s for
    #: the two-pass pipeline and the render, then clicks again; six in a row is
    #: already well past anything the UI can produce.
    rate_limit_burst: int = Field(default=6, ge=1)

    #: Sustained rate, in requests per minute, across all four LLM endpoints
    #: combined. One token every five seconds. A generation costs two provider
    #: calls and takes tens of seconds, so twelve per minute is an order of
    #: magnitude above real use and still bounds a runaway client to something
    #: survivable.
    rate_limit_per_minute: float = Field(default=12.0, gt=0)

    #: Hard ceiling on a JSON request body, before it is buffered. The largest
    #: legitimate body is an evaluate request: a 100 KB YAML resume plus a
    #: 20 KB job description, which after JSON escaping and UTF-8 encoding
    #: cannot approach this.
    max_json_body_bytes: int = Field(default=1 * 1024 * 1024, gt=0)

    #: Hard ceiling on a multipart upload body. `MAX_PDF_UPLOAD_BYTES` plus
    #: room for the multipart framing, so the rejection a user sees comes from
    #: the PDF cap with its specific message rather than from this one.
    max_upload_body_bytes: int = Field(default=11 * 1024 * 1024, gt=0)

    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_security_policy() -> SecurityPolicy:
    """The process-wide policy. Cached; the environment is read once."""
    return SecurityPolicy()


# ── Rate limiting ────────────────────────────────────────────────────────────

#: Above this many tracked clients, prune before adding another. The store is
#: itself a memory-growth vector otherwise: one dict entry per distinct source
#: address is cheap, but it is attacker-controlled and must be bounded.
_PRUNE_THRESHOLD: Final = 256

#: Hard cap on tracked clients. Beyond it, the least recently seen are evicted.
#: An evicted client starts again with a full bucket, which is the safe way to
#: be wrong: the alternative is refusing a legitimate client because the table
#: is full.
_MAX_TRACKED_CLIENTS: Final = 1024


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    """A token bucket per client key, in process memory.

    In process rather than in Redis on purpose: this is a single-instance,
    single-worker application (``--workers 1`` in the Dockerfile), so a shared
    store would add an operational dependency and buy nothing. If the process
    ever runs more than one worker, each worker gets its own bucket and the
    effective limit multiplies by the worker count — which is the point at
    which this should move behind a shared store, not before.

    State is mutated under a lock. The middleware calls this from the event
    loop thread only, so the lock is never contended in practice; it is here so
    that a future caller on a worker thread cannot corrupt the store.
    """

    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> float:
        """Spend one token for ``key``.

        Returns:
            ``0.0`` if the request is allowed, otherwise the number of seconds
            the caller should wait before a token exists — which is what goes
            in ``Retry-After``.
        """
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._prune(moment)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self._capacity, updated=moment)
                self._buckets[key] = bucket
            else:
                elapsed = max(0.0, moment - bucket.updated)
                bucket.tokens = min(
                    self._capacity, bucket.tokens + elapsed * self._refill
                )
                bucket.updated = moment

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return 0.0
            return (1.0 - bucket.tokens) / self._refill

    def _prune(self, now: float) -> None:
        """Drop buckets that carry no information, then the oldest if needed.

        A bucket that has refilled to capacity is indistinguishable from a
        client that has never been seen, so forgetting it changes nothing.
        """
        if len(self._buckets) < _PRUNE_THRESHOLD:
            return
        full_after = self._capacity / self._refill
        self._buckets = {
            key: bucket
            for key, bucket in self._buckets.items()
            if now - bucket.updated < full_after
        }
        overflow = len(self._buckets) - _MAX_TRACKED_CLIENTS
        if overflow > 0:
            oldest = sorted(self._buckets, key=lambda k: self._buckets[k].updated)
            for key in oldest[:overflow]:
                del self._buckets[key]


@lru_cache(maxsize=1)
def get_rate_limiter() -> TokenBucketLimiter:
    """The process-wide limiter, built from the policy. Cached."""
    policy = get_security_policy()
    return TokenBucketLimiter(
        capacity=float(policy.rate_limit_burst),
        refill_per_second=policy.rate_limit_per_minute / 60.0,
    )


def retry_after_seconds(wait: float) -> int:
    """``Retry-After`` takes whole seconds, and must never round down to zero."""
    return max(1, math.ceil(wait))


def client_key(client: tuple[str, int] | None) -> str:
    """The rate-limiter key for one connection.

    The peer address, and **not** ``X-Forwarded-For``. On an API with no
    authentication, a header any caller can set is a way to mint unlimited
    buckets, so it is ignored. Behind a reverse proxy that means every request
    shares one bucket, which errs toward refusing too much rather than
    metering nothing; revisit it together with D4, when there is an
    authenticated subject worth keying on.
    """
    if client is None:
        return "unknown"
    return client[0]


# ── Bounded reads ────────────────────────────────────────────────────────────


async def read_upload_capped(
    file: UploadFile,
    max_bytes: int | None = None,
    *,
    chunk_size: int = 64 * 1024,
) -> bytes:
    """Read an upload into memory, refusing to buffer more than ``max_bytes``.

    ``await file.read()`` with no argument materialises the entire body
    whatever its size, so the 10 MB guard in :mod:`resumetailor.pdf.extract`
    ran *after* the allocation it was supposed to prevent (D-48). This reads in
    bounded chunks and gives up as soon as the running total passes the cap, so
    the peak allocation for an oversized upload is one chunk past the limit
    rather than the whole body.

    ``Content-Length`` is not consulted here: it is client-supplied, optional,
    and already checked by ``BodySizeLimitMiddleware`` before any of this runs.
    This is the check that does not depend on the client telling the truth.

    Args:
        file: the upload to read.
        max_bytes: the cap. Defaults to :data:`MAX_PDF_UPLOAD_BYTES`, read at
            call time rather than bound as a default argument so that a test
            can lower it without pushing ten megabytes through the ASGI stack.
        chunk_size: how much to read per iteration, and therefore how far past
            the cap the peak allocation can go.

    Raises:
        RequestTooLargeError: if the upload exceeds ``max_bytes``.
    """
    cap = MAX_PDF_UPLOAD_BYTES if max_bytes is None else max_bytes
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(chunk_size):
        total += len(chunk)
        if total > cap:
            msg = f"upload exceeds the {cap} byte cap (aborted after {total} bytes)"
            raise RequestTooLargeError(msg)
        chunks.append(chunk)
    return b"".join(chunks)


# ── Path containment (D-25) ──────────────────────────────────────────────────


def resolve_within(base: str | Path, relative: str) -> Path | None:
    """Join ``relative`` onto ``base`` and confirm the result stays inside it.

    Returns ``None`` rather than raising, and callers turn that into a 404
    rather than a 403: a 403 would confirm to a caller that the path it asked
    for exists somewhere and that a check refused it. A 404 says nothing.

    Not exploitable at the two call sites today — the stored value is always
    the server-generated ``f"{resume_id}.pdf"`` — but the column is one feature
    away from being user-influenced, and the guard is free (D-25).
    """
    root = Path(base).resolve()
    candidate = (root / relative).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        return None
    return candidate


# ── Subprocess environment (D-49) ────────────────────────────────────────────

#: Environment variables the ``rendercv`` child is allowed to inherit, and the
#: reason each one is on the list. Everything else is dropped, which is the
#: point: ``docker-compose.yml`` loads ``.env``, so ``OPENAI_API_KEY`` is a real
#: variable in the container's environment however the LLM adapter behaves, and
#: a Typst crash dump or a verbose RenderCV traceback that echoed its
#: environment would put the key in a `RenderError` message.
#:
#: Notably absent: ``PYTHONPATH``. The image sets it to ``/app/backend/src`` for
#: our own src-layout package, and RenderCV has no business importing from
#: there.
_SUBPROCESS_ENV_PASSTHROUGH: Final = (
    # Required. `create_subprocess_exec` resolves the executable with
    # `execvpe` against the PATH in the env it is *given*, so dropping this
    # means `rendercv` is not found at all. It is also how the child finds the
    # Typst binary that ships in the same virtualenv.
    "PATH",
    # fontconfig builds its cache under $HOME/.cache (or $XDG_CACHE_HOME) and
    # is noisy on stderr without a writable one. Typst resolves fonts through
    # it, and RenderCV's stderr ends up in a RenderError message.
    "HOME",
    "XDG_CACHE_HOME",
    # Typst and RenderCV both write intermediate files. Without this they use
    # /tmp, which is correct in the container and wrong on a host where TMPDIR
    # points somewhere writable and /tmp does not.
    "TMPDIR",
    # Encoding. RenderCV is a Python program reading a UTF-8 YAML file whose
    # content is a person's name; with no locale at all CPython's default
    # encoding on Linux is ASCII and a non-ASCII name fails the render. PYTHONUTF8
    # below makes this deterministic, but a non-Python child (Typst) still
    # reads these.
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    # Dates in the rendered document.
    "TZ",
    # Windows: a process started without it cannot load system DLLs. Only
    # relevant to a developer running the renderer outside the container.
    "SYSTEMROOT",
)


def subprocess_env() -> dict[str, str]:
    """The minimal environment for the ``rendercv`` child process.

    Built as an allowlist rather than by deleting known-sensitive names, so a
    variable added to the deployment later is excluded by default instead of
    inherited by default.
    """
    env = {
        name: os.environ[name]
        for name in _SUBPROCESS_ENV_PASSTHROUGH
        if name in os.environ
    }
    # `os.defpath` is the platform's fallback search path. Reaching this means
    # the parent has no PATH at all, which should be impossible; a child with
    # no PATH cannot exec at all, so a wrong-but-present value produces a
    # legible "rendercv: not found" instead of an opaque failure.
    env.setdefault("PATH", os.defpath)
    # Independent of the locale variables above: UTF-8 for the child's own I/O
    # whatever the host locale says.
    env["PYTHONUTF8"] = "1"
    # Nothing in the user site directory belongs in a render.
    env["PYTHONNOUSERSITE"] = "1"
    return env


# ── Wiring ───────────────────────────────────────────────────────────────────


def install_security_middleware(app: FastAPI) -> None:
    """Install the body-size cap and the rate limiter, in that order.

    Starlette's ``add_middleware`` inserts at the *front* of the stack, so the
    last middleware added is the outermost. Adding the body cap first and the
    limiter second puts the limiter outside it, which is the order that
    matters: a request from a client that is already over its limit is refused
    without reading its body.

    ``main.py`` calls this **before** it adds ``RequestContextMiddleware``, so
    that one ends up outside both and a 429 or a 413 still carries a request id
    and an ``X-Request-Id`` header.
    """
    from resumetailor.core.middleware import (
        BodySizeLimitMiddleware,
        RateLimitMiddleware,
    )

    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)


def reset_security_caches() -> None:
    """Drop the cached policy and limiter.

    For tests, which change ``SECURITY_*`` in the environment and need the next
    request to see it — and need the bucket state from the previous test gone.
    Nothing in the application calls this.
    """
    get_security_policy.cache_clear()
    get_rate_limiter.cache_clear()
