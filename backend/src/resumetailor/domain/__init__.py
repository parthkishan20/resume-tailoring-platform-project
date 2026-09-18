"""Business logic, free of HTTP and of storage details.

Two pipelines live here, moved out of ``api/routers/{resumes,evaluate}.py`` by
task 2.5 (PLAN.md section 3.3):

* :mod:`resumetailor.domain.tailoring` — the two-pass generate-then-audit
  pipeline, and the write that persists its output.
* :mod:`resumetailor.domain.evaluation` — scoring one resume against one job
  description.

Neither imports from ``api/``. A route parses the request, calls one of these,
and serializes what comes back; the progress narration and the SSE frame shapes
stay with the route, because they are the wire contract rather than the work.
"""
