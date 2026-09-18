"""Task 3.5: the lifespan's own wiring — startup reaper, periodic reaper task,
and the graceful-shutdown drain — exercised directly rather than through
`client`, since `client` (see `conftest.py`) already enters and exits the real
lifespan around every other test in the suite and this file is about that
entry and exit themselves.
"""

from __future__ import annotations

import asyncio

import pytest

from resumetailor.core.metrics import REAPER_RUNS_TOTAL, sse_stream_tracker
from resumetailor.main import app, lifespan


@pytest.mark.anyio
async def test_lifespan_runs_the_reaper_once_at_startup(db_path, pdfs_dir):
    # Reading a Counter's own value has no public accessor.
    before = REAPER_RUNS_TOTAL.labels(trigger="startup")._value.get()

    async with lifespan(app):
        pass

    after = REAPER_RUNS_TOTAL.labels(trigger="startup")._value.get()
    assert after == before + 1


@pytest.mark.anyio
async def test_lifespan_cancels_the_periodic_reaper_task_on_shutdown(db_path, pdfs_dir):
    tasks_before = {t.get_name() for t in asyncio.all_tasks()}

    async with lifespan(app):
        tasks_during = asyncio.all_tasks()
        reaper_tasks = [t for t in tasks_during if t.get_name() == "orphan-reaper"]
        assert len(reaper_tasks) == 1
        assert not reaper_tasks[0].done()

    tasks_after = {t.get_name() for t in asyncio.all_tasks()} - tasks_before
    assert "orphan-reaper" not in tasks_after


@pytest.mark.anyio
async def test_lifespan_waits_for_an_in_flight_sse_stream_to_drain(
    db_path, pdfs_dir, monkeypatch: pytest.MonkeyPatch
):
    """The shutdown half of task 3.5's graceful-shutdown work.

    A stream that finishes well within `GRACEFUL_SHUTDOWN_TIMEOUT_S` must not
    be cut off: the lifespan's `__aexit__` should not return until it does.
    """
    import resumetailor.main as main_module

    monkeypatch.setattr(main_module.get_settings(), "GRACEFUL_SHUTDOWN_TIMEOUT_S", 5.0)

    stream_finished = False

    async def slow_stream() -> None:
        nonlocal stream_finished
        async with sse_stream_tracker.track():
            await asyncio.sleep(0.05)
            stream_finished = True

    async with lifespan(app):
        task = asyncio.create_task(slow_stream())
        await asyncio.sleep(0)  # let it register with the tracker
        assert sse_stream_tracker.active >= 1

    await task
    assert stream_finished is True


@pytest.mark.anyio
async def test_lifespan_logs_a_warning_rather_than_hanging_on_a_stuck_stream(
    db_path, pdfs_dir, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    import resumetailor.main as main_module

    monkeypatch.setattr(main_module.get_settings(), "GRACEFUL_SHUTDOWN_TIMEOUT_S", 0.05)

    async def stuck_stream() -> None:
        async with sse_stream_tracker.track():
            await asyncio.sleep(10)

    with caplog.at_level("WARNING", logger="resumetailor.main"):
        async with lifespan(app):
            task = asyncio.create_task(stuck_stream())
            await asyncio.sleep(0)

    assert any("timed out waiting" in message for message in caplog.messages)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
