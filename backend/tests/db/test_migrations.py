"""Migrations, and the P0 they close.

D-02 in full: `init_db` ran `CREATE TABLE IF NOT EXISTS` on every boot, so
against a database that already had tables it did nothing. A schema change
deployed, changed nothing, and the next query raised `no such column`. Nothing
in the suite could have caught that, because nothing ever applied a change to a
database that already held data.

`test_data_survives_every_migration` is that missing test: build a database at
version 1, fill it the way a user would, apply every later migration, and read
it all back.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from resumetailor.db.migrate import (
    MIGRATIONS_DIR,
    MigrationError,
    current_version,
    discover,
    migrate,
)
from tests.db import raw

LATEST = max(version for version, _ in discover())


@pytest.fixture
def v1_dir(tmp_path):
    """A migrations directory holding only 0001, to build a pre-change database."""
    directory = tmp_path / "v1_migrations"
    directory.mkdir()
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", directory)
    return directory


@pytest.fixture
def v1_db(tmp_path, v1_dir) -> str:
    """A database at the schema this project shipped before migrations existed."""
    path = str(tmp_path / "v1.db")
    migrate(path, v1_dir)
    return path


def _rows(db_path: str, sql: str) -> list[tuple]:
    with raw(db_path) as conn:
        return conn.execute(sql).fetchall()


# --- The runner --------------------------------------------------------------


def test_current_version_of_an_unmigrated_file_is_zero(tmp_path):
    assert current_version(str(tmp_path / "nothing.db")) == 0


def test_migrate_applies_everything_to_an_empty_database(tmp_path):
    path = str(tmp_path / "fresh.db")
    assert migrate(path) == list(range(1, LATEST + 1))
    assert current_version(path) == LATEST


def test_migrate_is_idempotent(tmp_path):
    path = str(tmp_path / "fresh.db")
    migrate(path)
    assert migrate(path) == []
    assert current_version(path) == LATEST


def test_migrate_records_one_row_per_migration(tmp_path):
    path = str(tmp_path / "fresh.db")
    migrate(path)
    versions = [row[0] for row in _rows(path, "SELECT version FROM schema_version")]
    assert versions == list(range(1, LATEST + 1))


def test_migrate_resumes_from_a_partly_migrated_database(v1_db):
    assert current_version(v1_db) == 1
    assert migrate(v1_db) == list(range(2, LATEST + 1))


def test_discover_rejects_a_misnamed_file(tmp_path):
    (tmp_path / "add_a_column.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match=r"NNNN_name\.sql"):
        discover(tmp_path)


def test_discover_rejects_two_files_claiming_one_version(tmp_path):
    (tmp_path / "0001_initial.sql").write_text("SELECT 1;")
    (tmp_path / "0001_also_initial.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="claim version 1"):
        discover(tmp_path)


def test_a_failing_migration_rolls_back_and_is_not_recorded(tmp_path, v1_dir):
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", v1_dir)
    (v1_dir / "0002_broken.sql").write_text(
        "CREATE TABLE ok_so_far (id INTEGER);\nSELECT this_is_not_valid_sql;\n"
    )
    path = str(tmp_path / "broken.db")
    with pytest.raises(MigrationError, match=r"0002_broken\.sql"):
        migrate(path, v1_dir)
    assert current_version(path) == 1
    tables = {row[0] for row in _rows(path, "SELECT name FROM sqlite_master")}
    assert "ok_so_far" not in tables


# --- D-02: data survives a schema change -------------------------------------


def test_data_survives_every_migration(v1_db):
    """Populate a version-1 database, migrate it to the newest version, read it back.

    This is the test whose absence made D-02 a P0: every migration below
    rebuilds at least one table by copy-drop-rename, and nothing else in the
    suite would notice if a copy dropped a column or a row.
    """
    with raw(v1_db) as conn:
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content) VALUES ('default', 'cv: master')"
        )
        conn.executemany(
            "INSERT INTO master_resume_history (user_id, yaml_content) VALUES ('default', ?)",
            [(f"cv: v{i}",) for i in range(3)],
        )
        conn.executemany(
            "INSERT INTO generated_resumes (user_id, name, job_description, yaml_content, pdf_path) "
            "VALUES ('default', ?, ?, ?, ?)",
            [(f"Resume {i}", f"JD {i}", f"cv: gen{i}", f"{i}.pdf") for i in range(4)],
        )
        conn.executemany(
            "INSERT INTO chat_messages (user_id, role, content) VALUES ('default', ?, ?)",
            [("user", "hello"), ("assistant", "hi")],
        )
        conn.execute(
            "INSERT INTO generation_rules (user_id, section, rule_key, rule_value) "
            "VALUES ('default', 'experience', 'max_entries', '7')"
        )
        conn.execute(
            "INSERT INTO system_prompt (user_id, content) VALUES ('default', 'be brief')"
        )
        conn.commit()

    migrate(v1_db)

    assert current_version(v1_db) == LATEST
    assert _rows(v1_db, "SELECT yaml_content FROM master_resume") == [("cv: master",)]
    assert _rows(
        v1_db, "SELECT yaml_content FROM master_resume_history ORDER BY id"
    ) == [("cv: v0",), ("cv: v1",), ("cv: v2",)]
    assert _rows(
        v1_db,
        "SELECT name, job_description, yaml_content, pdf_path FROM generated_resumes ORDER BY id",
    ) == [(f"Resume {i}", f"JD {i}", f"cv: gen{i}", f"{i}.pdf") for i in range(4)]
    assert _rows(v1_db, "SELECT role, content FROM chat_messages ORDER BY id") == [
        ("user", "hello"),
        ("assistant", "hi"),
    ]
    assert _rows(
        v1_db, "SELECT section, rule_key, rule_value FROM generation_rules"
    ) == [("experience", "max_entries", "7")]
    assert _rows(v1_db, "SELECT content FROM system_prompt") == [("be brief",)]


def test_row_ids_survive_every_migration(v1_db):
    """The rebuilds copy ids explicitly; `pdf_path` is derived from one."""
    with raw(v1_db) as conn:
        conn.executemany(
            "INSERT INTO generated_resumes (user_id, name, job_description, yaml_content) "
            "VALUES ('default', ?, '', 'cv: x')",
            [(f"Resume {i}",) for i in range(3)],
        )
        conn.execute("DELETE FROM generated_resumes WHERE id = 2")
        conn.commit()
        before = conn.execute(
            "SELECT id, name FROM generated_resumes ORDER BY id"
        ).fetchall()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT id, name FROM generated_resumes ORDER BY id") == before


# --- 0002: dedupe then rebuild -----------------------------------------------


def test_duplicate_master_resumes_are_deduped_newest_wins(v1_db):
    with raw(v1_db) as conn:
        conn.executemany(
            "INSERT INTO master_resume (user_id, yaml_content, updated_at) VALUES ('default', ?, ?)",
            [
                ("cv: oldest", "2026-01-01 00:00:00"),
                ("cv: newest", "2026-03-01 00:00:00"),
                ("cv: middle", "2026-02-01 00:00:00"),
            ],
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT yaml_content FROM master_resume") == [("cv: newest",)]


def test_losing_master_resume_duplicates_are_kept_as_history(v1_db):
    """Dedupe must not be a quiet delete of something the user wrote."""
    with raw(v1_db) as conn:
        conn.executemany(
            "INSERT INTO master_resume (user_id, yaml_content, updated_at) VALUES ('default', ?, ?)",
            [
                ("cv: oldest", "2026-01-01 00:00:00"),
                ("cv: newest", "2026-03-01 00:00:00"),
            ],
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT yaml_content FROM master_resume_history") == [
        ("cv: oldest",)
    ]


def test_duplicate_system_prompts_are_deduped_newest_wins(v1_db):
    with raw(v1_db) as conn:
        conn.executemany(
            "INSERT INTO system_prompt (user_id, content, updated_at) VALUES ('default', ?, ?)",
            [("older", "2026-01-01 00:00:00"), ("newer", "2026-02-01 00:00:00")],
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT content FROM system_prompt") == [("newer",)]


def test_dedupe_is_a_no_op_without_duplicates(v1_db):
    with raw(v1_db) as conn:
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content) VALUES ('default', 'cv: only')"
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT yaml_content FROM master_resume") == [("cv: only",)]
    assert _rows(v1_db, "SELECT COUNT(*) FROM master_resume_history") == [(0,)]


# --- 0003: foreign keys and indexes ------------------------------------------


def test_orphan_history_rows_are_removed(v1_db):
    """Rows the old delete path left behind, which the new FK could not accept."""
    with raw(v1_db) as conn:
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content) VALUES ('default', 'cv: x')"
        )
        conn.execute(
            "INSERT INTO master_resume_history (user_id, yaml_content) VALUES ('default', 'kept')"
        )
        conn.execute(
            "INSERT INTO master_resume_history (user_id, yaml_content) VALUES ('ghost', 'orphan')"
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT yaml_content FROM master_resume_history") == [("kept",)]


def test_indexes_exist_after_migrating(tmp_path):
    path = str(tmp_path / "fresh.db")
    migrate(path)
    names = {
        row[0]
        for row in _rows(path, "SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert {
        "idx_master_resume_history_user",
        "idx_generated_resumes_user_created",
        "idx_generated_resumes_user_jd",
        "idx_chat_messages_user_id",
    } <= names


def test_list_query_uses_an_index(tmp_path):
    """D-14 said `list_resumes` full-scans and sorts. Ask SQLite whether it still does."""
    path = str(tmp_path / "fresh.db")
    migrate(path)
    with raw(path) as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM generated_resumes "
            "WHERE user_id = 'default' ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "idx_generated_resumes_user_created" in detail
    assert "SCAN" not in detail


# --- 0004: ISO-8601 timestamps -----------------------------------------------


def test_legacy_timestamps_are_converted_to_iso(v1_db):
    with raw(v1_db) as conn:
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content, updated_at) "
            "VALUES ('default', 'cv: x', '2026-09-18 07:41:03')"
        )
        conn.execute(
            "INSERT INTO generated_resumes (user_id, name, job_description, yaml_content, created_at, updated_at) "
            "VALUES ('default', 'R', '', 'cv: y', '2026-09-18 07:41:03', '2026-09-18 07:41:04')"
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT updated_at FROM master_resume") == [
        ("2026-09-18T07:41:03Z",)
    ]
    assert _rows(v1_db, "SELECT created_at, updated_at FROM generated_resumes") == [
        ("2026-09-18T07:41:03Z", "2026-09-18T07:41:04Z")
    ]


def test_column_defaults_write_iso_after_migrating(tmp_path):
    """The default, not just the converted data: a writer that names no timestamp
    must not be able to put the old naive form back."""
    path = str(tmp_path / "fresh.db")
    migrate(path)
    with raw(path) as conn:
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content) VALUES ('default', 'cv: x')"
        )
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES ('default', 'user', 'hi')"
        )
        conn.commit()
        stamps = [
            conn.execute("SELECT updated_at FROM master_resume").fetchone()[0],
            conn.execute("SELECT created_at FROM chat_messages").fetchone()[0],
        ]
    assert all(stamp.endswith("Z") and "T" in stamp for stamp in stamps)


def test_an_unparseable_timestamp_is_left_alone_rather_than_nulled(v1_db):
    with raw(v1_db) as conn:
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content, updated_at) "
            "VALUES ('default', 'cv: x', 'not a timestamp')"
        )
        conn.commit()

    migrate(v1_db)

    assert _rows(v1_db, "SELECT updated_at FROM master_resume") == [
        ("not a timestamp",)
    ]
