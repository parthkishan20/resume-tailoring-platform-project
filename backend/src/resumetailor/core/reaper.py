# backend/src/resumetailor/core/reaper.py
"""The orphan reaper (PLAN.md D-20).

``domain/tailoring.py::store_tailored_resume`` writes a row, then a PDF file,
then updates the row — three steps, no transaction across the database and the
filesystem. Its own docstring names the gap and says fixing it belongs with
task 3.5's reaper, "not here": that function is `backend-domain`'s, and this
module is deliberately not a change to it. Everything below reads the same
state from the outside, through the repository functions
`domain/tailoring.py` itself calls, and reconciles after the fact rather than
preventing the race.

Two failure shapes, reconciled differently:

* **Crash after the file write, before the row update.** The row still has
  `pdf_path IS NULL`, but `<PDFS_DIR>/<id>.pdf` exists and is exactly the file
  the write was about to point the row at. This is not damage — relinking it
  (``update_resume(..., pdf_path=...)``) is the same write the crashed request
  was one statement away from making, so the reaper makes it. No data lost.
* **Crash after the row insert, before the file write.** `pdf_path IS NULL`
  and no file exists either. The row still holds a valid `yaml_content` — the
  tailored resume text was never lost — so deleting it would throw away
  content a crash merely stopped short of rendering, and `POST
  /api/resumes/{id}/render` already re-renders any row regardless of its
  `pdf_path`. The reaper leaves these alone and only counts them
  (`REAPER_ROWS_MISSING_PDF`), so the count is visible without hiding the
  content it describes.

A third shape is cleanup rather than recovery: a PDF file that matches no
row's `pdf_path` at all (the first case, before it is relinked, is the only
legitimate reason a file can exist with no row pointing at it yet — everything
else left in `PDFS_DIR` after relinking is unreferenced and safe to delete).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path

from resumetailor.core.metrics import (
    REAPER_FILES_DELETED_TOTAL,
    REAPER_ROWS_MISSING_PDF,
    REAPER_ROWS_RELINKED_TOTAL,
    REAPER_RUNS_TOTAL,
)
from resumetailor.db.models import ResumeSummary
from resumetailor.db.repositories import list_resumes, update_resume
from resumetailor.db.repositories.resumes import MAX_PAGE_SIZE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReaperReport:
    """What one reaper pass found and did."""

    rows_relinked: int
    rows_missing_pdf: int
    files_deleted: int


def _all_resume_summaries(db_path: str) -> list[ResumeSummary]:
    """Every `generated_resumes` row, across every page.

    `list_resumes` is paginated for the library UI (D-10); the reaper needs
    every row, so it pages through `MAX_PAGE_SIZE` at a time rather than
    asking the repository for an unbounded read it deliberately refuses to
    offer.
    """
    summaries: list[ResumeSummary] = []
    page = 1
    while True:
        result = list_resumes(db_path, page=page, limit=MAX_PAGE_SIZE)
        summaries.extend(result.items)
        if len(summaries) >= result.total or not result.items:
            return summaries
        page += 1


def reap_orphans(db_path: str, pdfs_dir: str) -> ReaperReport:
    """Reconcile `generated_resumes` against `PDFS_DIR`. Synchronous, blocking.

    Safe to call with an empty database and a missing or empty `pdfs_dir`
    (the common case, on every boot): the row scan returns nothing and the
    directory scan is skipped if the directory does not exist yet.
    """
    directory = Path(pdfs_dir)
    rows = _all_resume_summaries(db_path)

    relinked = 0
    missing = 0
    referenced: set[str] = set()

    for row in rows:
        if row.pdf_path is not None:
            referenced.add(row.pdf_path)
            continue

        candidate_name = f"{row.id}.pdf"
        if (directory / candidate_name).exists():
            update_resume(db_path, row.id, pdf_path=candidate_name)
            referenced.add(candidate_name)
            relinked += 1
        else:
            missing += 1

    deleted = 0
    if directory.is_dir():
        for pdf_file in directory.glob("*.pdf"):
            if pdf_file.name not in referenced:
                pdf_file.unlink()
                deleted += 1

    report = ReaperReport(
        rows_relinked=relinked, rows_missing_pdf=missing, files_deleted=deleted
    )
    REAPER_ROWS_RELINKED_TOTAL.inc(report.rows_relinked)
    REAPER_FILES_DELETED_TOTAL.inc(report.files_deleted)
    REAPER_ROWS_MISSING_PDF.set(report.rows_missing_pdf)

    if report.rows_relinked or report.files_deleted or report.rows_missing_pdf:
        logger.info(
            "orphan reaper: reconciled generated_resumes against PDFS_DIR",
            extra={
                "rows_relinked": report.rows_relinked,
                "files_deleted": report.files_deleted,
                "rows_missing_pdf": report.rows_missing_pdf,
            },
        )
    return report


async def run_once(db_path: str, pdfs_dir: str, *, trigger: str) -> ReaperReport:
    """Run one pass off the event loop, and record which trigger asked for it."""
    REAPER_RUNS_TOTAL.labels(trigger=trigger).inc()
    return await asyncio.to_thread(reap_orphans, db_path, pdfs_dir)


async def run_periodically(db_path: str, pdfs_dir: str, interval_s: float) -> None:
    """Run the reaper every ``interval_s`` seconds until cancelled.

    Intended to run as a background `asyncio.Task`, started after the
    guaranteed startup pass and cancelled by the lifespan on shutdown (see
    `main.py`). A failed pass is logged and does not stop the next one: a
    reaper that gives up permanently on one bad pass defeats its own purpose.
    """
    while True:
        await asyncio.sleep(interval_s)
        try:
            await run_once(db_path, pdfs_dir, trigger="periodic")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("orphan reaper: periodic run failed")


def start_background_task(
    db_path: str, pdfs_dir: str, interval_s: float
) -> asyncio.Task[None]:
    """Create the periodic task. A thin wrapper so `main.py` names one call."""
    return asyncio.create_task(
        run_periodically(db_path, pdfs_dir, interval_s), name="orphan-reaper"
    )


async def stop_background_task(task: asyncio.Task[None]) -> None:
    """Cancel the periodic task and wait for it to actually stop."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
