"""Generated resumes: the library of tailored documents."""

from __future__ import annotations

import sqlite3

from resumetailor.db import DEFAULT_USER_ID
from resumetailor.db.engine import session
from resumetailor.db.models import GeneratedResume, ResumePage, ResumeSummary

#: The largest page this repository will ever return, whatever it is asked
#: for. `limit` reached SQL unbounded, so `?limit=-1` returned the whole table
#: (D-10). Rejecting the value with a 422 at the route is task 2.2's; clamping
#: it here means no caller, present or future, can ask for an unbounded read.
MAX_PAGE_SIZE = 100

_SELECT_ONE = """
    SELECT id, user_id, name, job_description, yaml_content, pdf_path,
           created_at, updated_at
      FROM generated_resumes
"""
_BY_ID = _SELECT_ONE + " WHERE id = ?"
_BY_ID_AND_USER = _SELECT_ONE + " WHERE id = ? AND user_id = ?"

# The four statements `list_resumes` can run, one per (sort, order) pair.
# Chosen from this table, never built: nothing user-supplied is interpolated
# into a query anywhere in this module.
_LIST_SELECT = """
    SELECT id, user_id, name, job_description, pdf_path, created_at, updated_at
      FROM generated_resumes
     WHERE user_id = ?
"""
_LIST_QUERIES: dict[tuple[str, str], str] = {
    ("created_at", "DESC"): _LIST_SELECT + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
    ("created_at", "ASC"): _LIST_SELECT + " ORDER BY created_at ASC LIMIT ? OFFSET ?",
    ("job_description", "DESC"): _LIST_SELECT
    + " ORDER BY job_description DESC LIMIT ? OFFSET ?",
    ("job_description", "ASC"): _LIST_SELECT
    + " ORDER BY job_description ASC LIMIT ? OFFSET ?",
}


def _to_model(row: sqlite3.Row) -> GeneratedResume:
    return GeneratedResume(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        job_description=row["job_description"],
        yaml_content=row["yaml_content"],
        pdf_path=row["pdf_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_summary(row: sqlite3.Row) -> ResumeSummary:
    return ResumeSummary(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        job_description=row["job_description"],
        pdf_path=row["pdf_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_resumes(  # noqa: PLR0913 - one parameter per query option, four of them keyword-only
    db_path: str,
    user_id: str = DEFAULT_USER_ID,
    *,
    sort: str = "date",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> ResumePage:
    """One page of the library, newest first by default.

    ``page`` and ``limit`` are clamped, not trusted: ``page`` to at least 1 and
    ``limit`` to 1..:data:`MAX_PAGE_SIZE`. The returned page reports the values
    actually used, so a caller that asked for something impossible can see what
    it got.
    """
    sort_col = "created_at" if sort == "date" else "job_description"
    order_dir = "DESC" if order.lower() == "desc" else "ASC"
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    page = max(page, 1)
    offset = (page - 1) * limit

    with session(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM generated_resumes WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        rows = conn.execute(
            _LIST_QUERIES[sort_col, order_dir], (user_id, limit, offset)
        ).fetchall()
        return ResumePage(
            items=[_to_summary(row) for row in rows],
            total=total,
            page=page,
            limit=limit,
        )


def create_resume(
    db_path: str,
    name: str,
    job_description: str,
    yaml_content: str,
    user_id: str = DEFAULT_USER_ID,
) -> GeneratedResume:
    """Insert a generated resume. ``pdf_path`` is set later, once it renders."""
    with session(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO generated_resumes "
            "(user_id, name, job_description, yaml_content) VALUES (?, ?, ?, ?)",
            (user_id, name, job_description, yaml_content),
        )
        row = conn.execute(_BY_ID, (cursor.lastrowid,)).fetchone()
        return _to_model(row)


def get_resume(
    db_path: str, resume_id: int, user_id: str = DEFAULT_USER_ID
) -> GeneratedResume | None:
    with session(db_path) as conn:
        row = conn.execute(_BY_ID_AND_USER, (resume_id, user_id)).fetchone()
        return _to_model(row) if row else None


def update_resume(  # noqa: PLR0913 - one parameter per updatable column, all keyword-only
    db_path: str,
    resume_id: int,
    *,
    name: str | None = None,
    yaml_content: str | None = None,
    pdf_path: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> GeneratedResume | None:
    """Update the named fields. ``None`` means "leave alone", not "set to null"."""
    assignments: list[str] = []
    values: list[str | int] = []
    if name is not None:
        assignments.append("name = ?")
        values.append(name)
    if yaml_content is not None:
        assignments.append("yaml_content = ?")
        values.append(yaml_content)
    if pdf_path is not None:
        assignments.append("pdf_path = ?")
        values.append(pdf_path)
    if not assignments:
        return get_resume(db_path, resume_id, user_id)

    assignments.append("updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")
    values.extend([resume_id, user_id])
    # The assignments are literal fragments chosen above, never caller input;
    # every value is still bound.
    statement = (
        f"UPDATE generated_resumes SET {', '.join(assignments)} "  # noqa: S608
        "WHERE id = ? AND user_id = ?"
    )

    with session(db_path) as conn:
        conn.execute(statement, values)
        row = conn.execute(_BY_ID_AND_USER, (resume_id, user_id)).fetchone()
        return _to_model(row) if row else None


def delete_resume(db_path: str, resume_id: int, user_id: str = DEFAULT_USER_ID) -> bool:
    with session(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM generated_resumes WHERE id = ? AND user_id = ?",
            (resume_id, user_id),
        )
        return cursor.rowcount > 0
