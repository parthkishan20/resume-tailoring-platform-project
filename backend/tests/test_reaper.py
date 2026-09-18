"""Task 3.5: the orphan reaper (D-20), exercised without an HTTP layer.

`store_tailored_resume` (`domain/tailoring.py`, owned by `backend-domain`) is
not called here — this suite builds the two crash states it can leave behind
directly through the same repository functions it uses, and checks
`core.reaper.reap_orphans` reconciles both without needing a running
application. See the module docstring in `core/reaper.py` for why each shape
is handled the way it is.

Synchronous throughout: `reap_orphans` blocks on purpose (see its docstring),
so none of this needs an event loop or the `anyio` marker other test modules
carry for their HTTP round trips.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import resumetailor.core.reaper as reaper_module
from resumetailor.core.config import get_settings
from resumetailor.core.reaper import ReaperReport, reap_orphans
from resumetailor.db.repositories import create_resume, get_resume, update_resume
from resumetailor.db.repositories.resumes import MAX_PAGE_SIZE


@pytest.fixture(autouse=True)
def _no_delete_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-81's grace period exists to protect a file that might still be
    mid-write in production; every file this suite creates is already
    complete, so there is nothing for the grace period to protect here and
    every deletion-path test would otherwise need to sleep past it."""
    monkeypatch.setattr(get_settings(), "REAPER_DELETE_GRACE_S", 0.0)


def test_relinks_a_row_whose_pdf_was_written_but_not_recorded(
    db_path: str, pdfs_dir: str
):
    """Crash after `write_bytes`, before `update_resume`: recoverable, no loss."""
    row = create_resume(db_path, "Resume — Orphan JD", "Orphan JD", "cv:\n  name: A\n")
    (Path(pdfs_dir) / f"{row.id}.pdf").write_bytes(b"%PDF-1.4 fake")

    report = reap_orphans(db_path, pdfs_dir)

    assert report.rows_relinked == 1
    assert report.rows_missing_pdf == 0
    assert report.files_deleted == 0
    reloaded = get_resume(db_path, row.id)
    assert reloaded is not None
    assert reloaded.pdf_path == f"{row.id}.pdf"


def test_leaves_a_row_with_no_pdf_at_all_alone(db_path: str, pdfs_dir: str):
    """Crash after `create_resume`, before any write: content survives, PDF missing.

    The reaper does not delete this row: `yaml_content` is intact and
    `POST /api/resumes/{id}/render` already re-renders any row regardless of
    its `pdf_path`, so deleting it would discard real content to clean up a
    gap the existing render endpoint already recovers from.
    """
    row = create_resume(db_path, "Resume — No PDF", "No PDF JD", "cv:\n  name: B\n")

    report = reap_orphans(db_path, pdfs_dir)

    assert report.rows_relinked == 0
    assert report.rows_missing_pdf == 1
    assert report.files_deleted == 0
    reloaded = get_resume(db_path, row.id)
    assert reloaded is not None
    assert reloaded.pdf_path is None
    assert reloaded.yaml_content == "cv:\n  name: B\n"


def test_deletes_a_pdf_file_no_row_references(db_path: str, pdfs_dir: str):
    """A file left over with no row pointing at it is cleaned up."""
    Path(pdfs_dir, "9999.pdf").write_bytes(b"%PDF-1.4 orphan")

    report = reap_orphans(db_path, pdfs_dir)

    assert report.files_deleted == 1
    assert not Path(pdfs_dir, "9999.pdf").exists()


def test_leaves_a_consistent_row_and_file_untouched(db_path: str, pdfs_dir: str):
    row = create_resume(db_path, "Resume — Fine", "Fine JD", "cv:\n  name: C\n")
    pdf_path = Path(pdfs_dir) / f"{row.id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 real")
    update_resume(db_path, row.id, pdf_path=f"{row.id}.pdf")

    report = reap_orphans(db_path, pdfs_dir)

    assert report == ReaperReport(
        rows_relinked=0,
        rows_missing_pdf=0,
        rows_broken_pdf_reference=0,
        files_deleted=0,
    )
    assert pdf_path.exists()


def test_empty_database_and_missing_pdfs_dir_is_a_no_op(db_path: str, tmp_path: Path):
    """The common case, on every boot: nothing to reconcile, no directory yet."""
    report = reap_orphans(db_path, str(tmp_path / "never-created"))

    assert report == ReaperReport(
        rows_relinked=0,
        rows_missing_pdf=0,
        rows_broken_pdf_reference=0,
        files_deleted=0,
    )


def test_pages_past_one_page_of_resumes(db_path: str, pdfs_dir: str):
    """The reconciliation scans every row, not just the first page (D-10)."""
    for i in range(MAX_PAGE_SIZE + 5):
        create_resume(db_path, f"Resume {i}", f"JD {i}", "cv:\n  name: X\n")

    report = reap_orphans(db_path, pdfs_dir)

    assert report.rows_missing_pdf == MAX_PAGE_SIZE + 5


# ── D-81: the delete-pass TOCTOU race ────────────────────────────────────────


def test_a_file_younger_than_the_grace_period_is_never_deleted(
    db_path: str, pdfs_dir: str, monkeypatch: pytest.MonkeyPatch
):
    """A file this fresh might belong to a write still in progress -- the
    grace period keeps it out of the delete pass regardless of what the row
    scan found, independent of the fresh-recheck path below."""
    monkeypatch.setattr(get_settings(), "REAPER_DELETE_GRACE_S", 9999.0)
    Path(pdfs_dir, "9999.pdf").write_bytes(b"%PDF-1.4 too fresh to touch")

    report = reap_orphans(db_path, pdfs_dir)

    assert report.files_deleted == 0
    assert Path(pdfs_dir, "9999.pdf").exists()


def test_a_row_with_a_broken_pdf_reference_is_detected_not_trusted(
    db_path: str, pdfs_dir: str
):
    """A row's own `pdf_path` used to be trusted with no check that the file
    still exists -- a broken reference (from this reaper's own race, or any
    other cause) was invisible forever. Now it is counted, and the row is
    left alone rather than silently treated as healthy."""
    row = create_resume(db_path, "Resume — Broken", "Broken JD", "cv:\n  name: D\n")
    update_resume(db_path, row.id, pdf_path=f"{row.id}.pdf")
    # No such file is ever written to pdfs_dir.

    report = reap_orphans(db_path, pdfs_dir)

    assert report.rows_broken_pdf_reference == 1
    assert report.rows_relinked == 0
    assert report.rows_missing_pdf == 0
    reloaded = get_resume(db_path, row.id)
    assert reloaded is not None
    assert reloaded.pdf_path == f"{row.id}.pdf"  # untouched, just reported


def test_a_file_linked_after_the_row_scan_survives_the_fresh_recheck(
    db_path: str, pdfs_dir: str, monkeypatch: pytest.MonkeyPatch
):
    """The exact race D-81 names: a row scan that ran before a concurrent
    `store_tailored_resume` call finished would build a `referenced` set that
    does not include the file that call just linked. Simulated here by
    forcing the row scan to see nothing, so the file the delete pass finds
    is "unreferenced" by the stale snapshot alone -- and must be saved by
    the fresh, direct database check immediately before deletion, not by the
    snapshot."""
    row = create_resume(db_path, "Resume — Raced", "Raced JD", "cv:\n  name: E\n")
    pdf_path = Path(pdfs_dir) / f"{row.id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 linked just now")
    update_resume(db_path, row.id, pdf_path=f"{row.id}.pdf")

    monkeypatch.setattr(reaper_module, "_all_resume_summaries", lambda _db_path: [])

    report = reap_orphans(db_path, pdfs_dir)

    assert report.files_deleted == 0
    assert pdf_path.exists()
