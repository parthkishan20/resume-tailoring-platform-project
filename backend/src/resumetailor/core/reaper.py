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

D-81, a real TOCTOU race, found by wave 4's adversarial review and security
review independently: the row scan (`_all_resume_summaries`) and the
directory-delete pass are two reads of state a concurrent
`store_tailored_resume` call can move between, seconds apart. A file that did
not exist yet when the row scan ran can exist by the time the delete pass
runs, without ever entering the `referenced` set the row scan built — so the
delete pass could unlink a file a request had just finished writing, leaving
that row's already-set `pdf_path` pointing at nothing. Worse, nothing ever
re-checked a *set* `pdf_path` against the filesystem afterward, so a broken
reference from that race (or from any other cause) was invisible to every
later pass. Two independent changes close this, neither requiring a
cross-system transaction the database and the filesystem cannot actually
share:

1. **A grace period on deletion** (`Settings.REAPER_DELETE_GRACE_S`): a file
   younger than the grace period is never a deletion candidate, full stop,
   regardless of what the row-scan snapshot says — long enough that a
   concurrent write in progress when the row scan ran has finished and
   updated its row well before the file becomes old enough to consider.
2. **A fresh re-check, not a stale snapshot, immediately before an
   irreversible delete**: for each file that still looks unreferenced after
   the grace period, the reaper asks the database directly, right then,
   whether *that one row* now points at *that one file* — closing the exact
   window the grace period does not (a write that is still slower than the
   grace period, on an unusually loaded system) without re-scanning every
   row again.
3. **Re-verification of already-linked rows**: a row with a non-`NULL`
   `pdf_path` used to be trusted without checking the file still exists. Now
   every such row is checked, and a broken reference is counted
   (`REAPER_ROWS_BROKEN_PDF_REFERENCE`) rather than silently assumed healthy
   forever — the same file is still recoverable via `POST
   /api/resumes/{id}/render`, but the operator can now see it needs it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from resumetailor.core.config import get_settings
from resumetailor.core.metrics import (
    REAPER_FILES_DELETED_TOTAL,
    REAPER_ROWS_BROKEN_PDF_REFERENCE,
    REAPER_ROWS_MISSING_PDF,
    REAPER_ROWS_RELINKED_TOTAL,
    REAPER_RUNS_TOTAL,
)
from resumetailor.db.models import ResumeSummary
from resumetailor.db.repositories import get_resume, list_resumes, update_resume
from resumetailor.db.repositories.resumes import MAX_PAGE_SIZE

logger = logging.getLogger(__name__)

_FILENAME_RESUME_ID = re.compile(r"^(\d+)\.pdf$")


@dataclass(frozen=True, slots=True)
class ReaperReport:
    """What one reaper pass found and did."""

    rows_relinked: int
    rows_missing_pdf: int
    rows_broken_pdf_reference: int
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


def _resume_id_from_filename(name: str) -> int | None:
    """Parse `"<id>.pdf"` back to `<id>`, or `None` for anything else in the
    directory (there is not supposed to be anything else, but a reaper
    reading a filesystem should not assume that)."""
    match = _FILENAME_RESUME_ID.match(name)
    return int(match.group(1)) if match else None


def _currently_linked_to(db_path: str, filename: str) -> bool:
    """Ask the database, right now, whether some row still points at
    `filename` -- the fresh check `reap_orphans` runs immediately before an
    irreversible delete, closing the window between its own row-scan
    snapshot and this moment (D-81)."""
    resume_id = _resume_id_from_filename(filename)
    if resume_id is None:
        return False
    current = get_resume(db_path, resume_id)
    return current is not None and current.pdf_path == filename


@dataclass(frozen=True, slots=True)
class _RowReconciliation:
    rows_relinked: int
    rows_missing_pdf: int
    rows_broken_pdf_reference: int
    referenced_filenames: frozenset[str]


def _reconcile_rows(db_path: str, directory: Path) -> _RowReconciliation:
    """The row-scan half: relink what crashed one statement short, count what
    is missing, and (D-81) re-verify what claims to already be linked rather
    than trusting it."""
    relinked = 0
    missing = 0
    broken = 0
    referenced: set[str] = set()

    for row in _all_resume_summaries(db_path):
        if row.pdf_path is not None:
            # D-81: a row can carry a `pdf_path` that no longer resolves to a
            # real file (this exact reaper's own delete pass racing a
            # concurrent write is one way that happens), and nothing checked
            # afterward.
            if (directory / row.pdf_path).exists():
                referenced.add(row.pdf_path)
            else:
                broken += 1
                logger.warning(
                    "orphan reaper: row's pdf_path does not exist on disk",
                    extra={"resume_id": row.id, "pdf_path": row.pdf_path},
                )
            continue

        candidate_name = f"{row.id}.pdf"
        if (directory / candidate_name).exists():
            update_resume(db_path, row.id, pdf_path=candidate_name)
            referenced.add(candidate_name)
            relinked += 1
        else:
            missing += 1

    return _RowReconciliation(
        rows_relinked=relinked,
        rows_missing_pdf=missing,
        rows_broken_pdf_reference=broken,
        referenced_filenames=frozenset(referenced),
    )


def _should_delete(
    pdf_file: Path, *, db_path: str, referenced: frozenset[str], grace_s: float
) -> bool:
    """Whether `pdf_file` is safe to delete as an orphan (D-81): not
    referenced by the row-scan snapshot, old enough that a concurrent write
    in progress when that snapshot ran has certainly finished, and -- the
    final word, not the snapshot -- not linked by a fresh, direct read of
    current database state."""
    if pdf_file.name in referenced:
        return False
    try:
        age_s = time.time() - pdf_file.stat().st_mtime
    except FileNotFoundError:
        return False  # deleted by something else between glob() and stat()
    if age_s < grace_s:
        return False
    return not _currently_linked_to(db_path, pdf_file.name)


def _delete_unreferenced_files(
    db_path: str, directory: Path, referenced: frozenset[str], grace_s: float
) -> int:
    if not directory.is_dir():
        return 0
    deleted = 0
    for pdf_file in directory.glob("*.pdf"):
        if _should_delete(
            pdf_file, db_path=db_path, referenced=referenced, grace_s=grace_s
        ):
            pdf_file.unlink()
            deleted += 1
    return deleted


def reap_orphans(db_path: str, pdfs_dir: str) -> ReaperReport:
    """Reconcile `generated_resumes` against `PDFS_DIR`. Synchronous, blocking.

    Safe to call with an empty database and a missing or empty `pdfs_dir`
    (the common case, on every boot): the row scan returns nothing and the
    directory scan is skipped if the directory does not exist yet.
    """
    directory = Path(pdfs_dir)
    rows = _reconcile_rows(db_path, directory)
    deleted = _delete_unreferenced_files(
        db_path,
        directory,
        rows.referenced_filenames,
        get_settings().REAPER_DELETE_GRACE_S,
    )

    report = ReaperReport(
        rows_relinked=rows.rows_relinked,
        rows_missing_pdf=rows.rows_missing_pdf,
        rows_broken_pdf_reference=rows.rows_broken_pdf_reference,
        files_deleted=deleted,
    )
    REAPER_ROWS_RELINKED_TOTAL.inc(report.rows_relinked)
    REAPER_FILES_DELETED_TOTAL.inc(report.files_deleted)
    REAPER_ROWS_MISSING_PDF.set(report.rows_missing_pdf)
    REAPER_ROWS_BROKEN_PDF_REFERENCE.set(report.rows_broken_pdf_reference)

    if (
        report.rows_relinked
        or report.files_deleted
        or report.rows_missing_pdf
        or report.rows_broken_pdf_reference
    ):
        logger.info(
            "orphan reaper: reconciled generated_resumes against PDFS_DIR",
            extra={
                "rows_relinked": report.rows_relinked,
                "files_deleted": report.files_deleted,
                "rows_missing_pdf": report.rows_missing_pdf,
                "rows_broken_pdf_reference": report.rows_broken_pdf_reference,
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
