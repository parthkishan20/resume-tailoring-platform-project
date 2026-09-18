"""Task 3.5: `/api/metrics`, and the in-flight SSE tracker it exposes."""

from __future__ import annotations

import asyncio

import pytest

from resumetailor.core.metrics import SSEStreamTracker


@pytest.mark.anyio
async def test_metrics_endpoint_serves_prometheus_text(client):
    response = await client.get("/api/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    # At least one of this task's own series is present, proving the endpoint
    # serves the same registry `core/metrics.py` registers to, not an empty one.
    assert "resumetailor_http_requests_total" in response.text


@pytest.mark.anyio
async def test_metrics_endpoint_is_not_itself_uncounted(client):
    """Calling /api/metrics is an HTTP request like any other and is counted."""
    await client.get("/api/metrics")
    response = await client.get("/api/metrics")
    assert 'path="/api/metrics"' in response.text


@pytest.mark.anyio
async def test_a_completed_request_is_recorded_under_its_route_template(client):
    """The label is the route template, not the raw path (cardinality)."""
    await client.get("/api/health")
    response = await client.get("/api/metrics")
    assert 'path="/api/health"' in response.text


@pytest.mark.anyio
async def test_sse_stream_tracker_tracks_one_stream_at_a_time():
    tracker = SSEStreamTracker()
    assert tracker.active == 0

    async with tracker.track():
        assert tracker.active == 1
        drained_immediately = await tracker.wait_drained(0.01)
        assert drained_immediately is False

    assert tracker.active == 0
    assert await tracker.wait_drained(0.01) is True


@pytest.mark.anyio
async def test_sse_stream_tracker_decrements_even_when_the_body_raises():
    tracker = SSEStreamTracker()

    async def failing_stream() -> None:
        async with tracker.track():
            msg = "boom"
            raise ValueError(msg)

    with pytest.raises(ValueError, match="boom"):
        await failing_stream()

    assert tracker.active == 0


@pytest.mark.anyio
async def test_sse_stream_tracker_decrements_on_cancellation():
    """A disconnected SSE client cancels the streaming task; the count still drops."""
    tracker = SSEStreamTracker()
    started = asyncio.Event()

    async def hold_open() -> None:
        async with tracker.track():
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(hold_open())
    await started.wait()
    assert tracker.active == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert tracker.active == 0
