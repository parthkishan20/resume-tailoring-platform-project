# backend/src/resumetailor/core/metrics.py
"""Prometheus metrics, and the in-flight SSE tracker that feeds two of them.

``prometheus_client`` rather than a hand-rolled counter dict: it is a single
pure-Python dependency with no transitive requirements and no server of its
own — `GET /api/metrics` in `api/routers/metrics.py` calls `generate_latest`
and returns the text, so nothing new listens on a port. Chosen over a second
logging stream because `core/logging.py`'s structured lines already answer
"what happened on this one request"; what was missing is "what does the
process look like right now," which a log has to be aggregated to answer and a
gauge or a counter answers directly.

Everything here is a module-level singleton registered once, at import, to
`prometheus_client`'s default registry — safe because the module is imported
exactly once per process (and once per test session; registering a metric
twice raises, which is exactly the guard that would catch a future refactor
that imports this module in a loop).

What is here:

* :data:`HTTP_REQUESTS_TOTAL` / :data:`HTTP_REQUEST_DURATION_SECONDS` — one
  request in, one line out, recorded by `core/middleware.py` so no router has
  to know metrics exist. Labelled by the *route template*
  (``/api/resumes/{resume_id}``), never the raw path, so a metrics label
  cannot grow one series per resume id.
* :data:`SSE_STREAMS_ACTIVE` and :class:`SSEStreamTracker` — the gauge is a
  side effect of the tracker, not tracked independently, because the same
  count is also what the lifespan waits on during shutdown (see `main.py`).
  One count, two readers.
* The ``REAPER_*`` metrics — updated by `core/reaper.py` after every run,
  startup and periodic alike, so "is the reaper running" and "is it finding
  anything" are both answerable without grepping logs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from prometheus_client import Counter, Gauge, Histogram

# ── HTTP ─────────────────────────────────────────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "resumetailor_http_requests_total",
    "HTTP requests, by method, route template and status code.",
    ("method", "path", "status"),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "resumetailor_http_request_duration_seconds",
    "HTTP request duration in seconds, by method and route template.",
    ("method", "path"),
)


def record_request(*, method: str, path: str, status: int, duration_s: float) -> None:
    """Record one finished request. Called once, from `RequestContextMiddleware`."""
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_s)


# ── SSE streams ──────────────────────────────────────────────────────────────

SSE_STREAMS_ACTIVE = Gauge(
    "resumetailor_sse_streams_active",
    "SSE streams (generate, chat, evaluate) currently open.",
)


#: How often `wait_drained` re-checks the count. Polling rather than an
#: `asyncio.Event` on purpose: an `Event`'s internal future binds itself to
#: whichever event loop first calls `.wait()` while it is unset, and this
#: tracker is a module-level singleton constructed once but awaited from a
#: fresh loop on every call in the test suite (a new loop per test, all
#: sharing the one `main.app` object) — the second test to drain a non-empty
#: tracker would raise "Event ... is bound to a different event loop". A
#: process only ever runs one event loop for its whole life, so this is a
#: test-harness-only failure mode, but the fix has to live here rather than in
#: the tests: polling has no loop affinity at all.
_POLL_INTERVAL_S = 0.05


class SSEStreamTracker:
    """How many SSE streams are open, and a way to wait for that to reach zero.

    Single-event-loop, single-worker process (see `core/security.py`'s
    `TokenBucketLimiter` docstring for the same assumption): increments and
    decrements happen on the event loop thread only, between `await` points,
    so no lock is needed.
    """

    def __init__(self) -> None:
        self._count = 0

    @property
    def active(self) -> int:
        return self._count

    @asynccontextmanager
    async def track(self) -> AsyncIterator[None]:
        """Wrap one stream's lifetime. Use as ``async with tracker.track():``."""
        self._count += 1
        SSE_STREAMS_ACTIVE.inc()
        try:
            yield
        finally:
            self._count -= 1
            SSE_STREAMS_ACTIVE.dec()

    async def wait_drained(self, timeout_s: float) -> bool:
        """Wait up to ``timeout_s`` seconds for every tracked stream to finish.

        Returns:
            ``True`` if the count reached zero in time, ``False`` on timeout —
            the caller decides whether that is worth a warning.
        """
        elapsed = 0.0
        while self._count > 0:
            if elapsed >= timeout_s:
                return False
            await asyncio.sleep(min(_POLL_INTERVAL_S, timeout_s - elapsed))
            elapsed += _POLL_INTERVAL_S
        return True


#: The process-wide tracker. `main.py`'s lifespan drains it on shutdown; the
#: three SSE routes report to it. One instance, because there is one process.
sse_stream_tracker = SSEStreamTracker()


# ── Orphan reaper (D-20) ─────────────────────────────────────────────────────

REAPER_RUNS_TOTAL = Counter(
    "resumetailor_reaper_runs_total",
    "Orphan reaper runs, by trigger.",
    ("trigger",),  # "startup" or "periodic"
)

REAPER_ROWS_RELINKED_TOTAL = Counter(
    "resumetailor_reaper_rows_relinked_total",
    "generated_resumes rows whose pdf_path was recovered because the PDF "
    "file the crash was writing already existed on disk.",
)

REAPER_FILES_DELETED_TOTAL = Counter(
    "resumetailor_reaper_files_deleted_total",
    "PDF files deleted from PDFS_DIR because no generated_resumes row referenced them.",
)

REAPER_ROWS_MISSING_PDF = Gauge(
    "resumetailor_reaper_rows_missing_pdf",
    "generated_resumes rows with pdf_path IS NULL and no matching file on "
    "disk, as of the last reaper run. Recoverable via POST "
    "/api/resumes/{id}/render; the reaper does not delete these.",
)

REAPER_ROWS_BROKEN_PDF_REFERENCE = Gauge(
    "resumetailor_reaper_rows_broken_pdf_reference",
    "generated_resumes rows whose pdf_path is set but the file it names does "
    "not exist on disk, as of the last reaper run (D-81) -- a row with a "
    "pdf_path used to be trusted without re-checking the file still exists, "
    "so a reference broken by a delete-pass race stayed invisible to every "
    "later pass. Recoverable the same way a missing-pdf row is, via POST "
    "/api/resumes/{id}/render.",
)
