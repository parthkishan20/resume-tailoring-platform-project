"""Repository behaviour. Ported from tests/test_database.py.

Every assertion the old module made is still made here; the reads now come back
as models rather than dicts, and the cases the old free functions could not
express -- the unique constraint, the bounded page, the SQL-side chat limit,
the ISO timestamp -- are added at the end of each section.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from resumetailor.db.repositories.chat import (
    add_chat_message,
    clear_chat,
    get_chat_messages,
)
from resumetailor.db.repositories.master_resume import (
    HISTORY_LIMIT,
    delete_master_resume,
    get_master_resume,
    upsert_master_resume,
)
from resumetailor.db.repositories.resumes import (
    MAX_PAGE_SIZE,
    create_resume,
    delete_resume,
    get_resume,
    list_resumes,
    update_resume,
)
from resumetailor.db.repositories.rules import get_rules, reset_rules, upsert_rules
from resumetailor.db.repositories.system_prompt import (
    get_system_prompt,
    reset_system_prompt,
    upsert_system_prompt,
)
from resumetailor.db.seed import DEFAULT_RULES, DEFAULT_SYSTEM_PROMPT
from tests.db import raw

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _table_names(db_path: str) -> set[str]:
    with raw(db_path) as conn:
        return {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not row[0].startswith("sqlite_")
        }


# --- Schema and seed ---------------------------------------------------------


def test_migrate_creates_all_tables(db_path):
    assert _table_names(db_path) == {
        "master_resume",
        "master_resume_history",
        "generated_resumes",
        "chat_messages",
        "generation_rules",
        "system_prompt",
        "schema_version",
    }


def test_seed_writes_default_rules(db_path):
    assert len(get_rules(db_path)) == len(DEFAULT_RULES)


def test_seed_writes_default_system_prompt(db_path):
    prompt = get_system_prompt(db_path)
    assert prompt is not None
    assert prompt.content == DEFAULT_SYSTEM_PROMPT


def test_seed_is_idempotent(db_path):
    from resumetailor.db.seed import seed_defaults

    seed_defaults(db_path)
    seed_defaults(db_path)
    with raw(db_path) as conn:
        prompts = conn.execute("SELECT COUNT(*) FROM system_prompt").fetchone()[0]
        rules = conn.execute("SELECT COUNT(*) FROM generation_rules").fetchone()[0]
    assert prompts == 1
    assert rules == len(DEFAULT_RULES)


def test_seed_does_not_overwrite_an_edited_prompt(db_path):
    from resumetailor.db.seed import seed_defaults

    upsert_system_prompt(db_path, "Mine, not yours")
    seed_defaults(db_path)
    assert get_system_prompt(db_path).content == "Mine, not yours"


# --- Master resume -----------------------------------------------------------


def test_get_master_resume_returns_none_when_empty(db_path):
    assert get_master_resume(db_path) is None


def test_upsert_master_resume_creates_and_returns(db_path):
    result = upsert_master_resume(db_path, "cv:\n  name: Test")
    assert result.yaml_content == "cv:\n  name: Test"
    assert result.user_id == "default"
    assert result.id > 0
    assert ISO_UTC.match(result.updated_at)


def test_upsert_master_resume_updates_existing(db_path):
    upsert_master_resume(db_path, "cv:\n  name: First")
    result = upsert_master_resume(db_path, "cv:\n  name: Second")
    assert result.yaml_content == "cv:\n  name: Second"
    with raw(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume").fetchone()[0]
    assert count == 1


def test_master_resume_user_id_is_unique(db_path):
    """The constraint D-06 asks for, asserted against the database itself."""
    upsert_master_resume(db_path, "cv:\n  name: First")
    with raw(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO master_resume (user_id, yaml_content) VALUES ('default', 'x')"
        )


def test_upsert_saves_to_history(db_path):
    upsert_master_resume(db_path, "cv:\n  name: First")
    upsert_master_resume(db_path, "cv:\n  name: Second")
    with raw(db_path) as conn:
        history = conn.execute(
            "SELECT yaml_content FROM master_resume_history ORDER BY id ASC"
        ).fetchall()
    assert len(history) == 1
    assert history[0][0] == "cv:\n  name: First"


def test_history_is_pruned(db_path):
    for i in range(HISTORY_LIMIT + 2):
        upsert_master_resume(db_path, f"cv:\n  name: Version{i}")
    with raw(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume_history").fetchone()[0]
    assert count == HISTORY_LIMIT


def test_delete_master_resume(db_path):
    upsert_master_resume(db_path, "cv:\n  name: Test")
    assert delete_master_resume(db_path) is True
    assert get_master_resume(db_path) is None


def test_delete_master_resume_cascades_history(db_path):
    """D-14: history rows used to survive their parent and become unreachable."""
    upsert_master_resume(db_path, "cv:\n  name: First")
    upsert_master_resume(db_path, "cv:\n  name: Second")
    delete_master_resume(db_path)
    with raw(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume_history").fetchone()[0]
    assert count == 0


def test_delete_master_resume_returns_false_when_not_exist(db_path):
    assert delete_master_resume(db_path) is False


# --- Generated resumes -------------------------------------------------------


def test_create_and_get_resume(db_path):
    created = create_resume(
        db_path, "SWE @ Acme", "We need Python devs", "cv:\n  name: T"
    )
    assert created.name == "SWE @ Acme"
    assert created.job_description == "We need Python devs"
    assert created.pdf_path is None
    assert ISO_UTC.match(created.created_at)
    fetched = get_resume(db_path, created.id)
    assert fetched is not None
    assert fetched.id == created.id


def test_get_resume_returns_none_for_missing(db_path):
    assert get_resume(db_path, 9999) is None


def test_list_resumes_pagination(db_path):
    for i in range(5):
        create_resume(db_path, f"Resume {i}", f"JD {i}", "cv:\n  name: X")
    page = list_resumes(db_path, page=1, limit=3)
    assert page.total == 5
    assert len(page.items) == 3
    assert page.page == 1


def test_list_resumes_second_page(db_path):
    for i in range(5):
        create_resume(db_path, f"Resume {i}", f"JD {i}", "cv:\n  name: X")
    page = list_resumes(db_path, page=2, limit=3)
    assert len(page.items) == 2
    assert page.page == 2


def test_list_resumes_sort_by_jd(db_path):
    create_resume(db_path, "B", "Zebra Corp", "cv:\n  name: B")
    create_resume(db_path, "A", "Apple Inc", "cv:\n  name: A")
    page = list_resumes(db_path, sort="jd", order="asc")
    assert page.items[0].name == "A"


def test_list_resumes_summary_omits_yaml(db_path):
    """The list projection has never carried yaml_content and still does not."""
    create_resume(db_path, "A", "JD", "cv:\n  name: A")
    item = list_resumes(db_path).items[0]
    assert "yaml_content" not in item.model_dump()


@pytest.mark.parametrize("limit", [-1, 0, 10_000])
def test_list_resumes_limit_is_bounded(db_path, limit):
    """D-10: `?limit=-1` used to return every row in the table."""
    for i in range(3):
        create_resume(db_path, f"Resume {i}", "JD", "cv:\n  name: X")
    page = list_resumes(db_path, limit=limit)
    assert 1 <= page.limit <= MAX_PAGE_SIZE
    assert len(page.items) <= MAX_PAGE_SIZE


def test_list_resumes_page_is_bounded(db_path):
    create_resume(db_path, "A", "JD", "cv:\n  name: A")
    page = list_resumes(db_path, page=-5)
    assert page.page == 1
    assert len(page.items) == 1


def test_update_resume_name(db_path):
    created = create_resume(db_path, "Old Name", "JD", "cv:\n  name: X")
    updated = update_resume(db_path, created.id, name="New Name")
    assert updated is not None
    assert updated.name == "New Name"
    assert ISO_UTC.match(updated.updated_at)


def test_update_resume_pdf_path(db_path):
    created = create_resume(db_path, "Test", "JD", "cv:\n  name: X")
    updated = update_resume(db_path, created.id, pdf_path="42.pdf")
    assert updated is not None
    assert updated.pdf_path == "42.pdf"


def test_update_resume_with_nothing_to_change_is_a_read(db_path):
    created = create_resume(db_path, "Test", "JD", "cv:\n  name: X")
    assert update_resume(db_path, created.id) == created


def test_update_resume_returns_none_for_missing(db_path):
    assert update_resume(db_path, 9999, name="x") is None


def test_delete_resume(db_path):
    created = create_resume(db_path, "Test", "JD", "cv:\n  name: X")
    assert delete_resume(db_path, created.id) is True
    assert get_resume(db_path, created.id) is None


def test_delete_resume_returns_false_for_missing(db_path):
    assert delete_resume(db_path, 9999) is False


# --- Chat --------------------------------------------------------------------


def test_add_and_get_chat_messages(db_path):
    add_chat_message(db_path, "user", "Hello")
    add_chat_message(db_path, "assistant", "Hi there!")
    messages = get_chat_messages(db_path)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert ISO_UTC.match(messages[0].created_at)


def test_get_chat_messages_limit_returns_the_newest_in_reading_order(db_path):
    """D-21: the limit belongs in the query, and must not reverse the order."""
    for i in range(10):
        add_chat_message(db_path, "user", f"m{i}")
    recent = get_chat_messages(db_path, limit=3)
    assert [m.content for m in recent] == ["m7", "m8", "m9"]


def test_get_chat_messages_limit_larger_than_history(db_path):
    add_chat_message(db_path, "user", "only one")
    assert len(get_chat_messages(db_path, limit=30)) == 1


def test_clear_chat(db_path):
    add_chat_message(db_path, "user", "Hello")
    clear_chat(db_path)
    assert get_chat_messages(db_path) == []


# --- Rules -------------------------------------------------------------------


def test_get_rules_returns_seeded_defaults(db_path):
    rules = get_rules(db_path)
    assert len(rules) == len(DEFAULT_RULES)
    assert ("experience", "max_entries") in {(r.section, r.rule_key) for r in rules}


def test_upsert_rules_updates_value(db_path):
    upsert_rules(
        db_path,
        [{"section": "experience", "rule_key": "max_entries", "rule_value": "3"}],
    )
    rules = get_rules(db_path)
    rule = next(
        r for r in rules if r.section == "experience" and r.rule_key == "max_entries"
    )
    assert rule.rule_value == "3"
    assert len(rules) == len(DEFAULT_RULES)


def test_reset_rules_restores_defaults(db_path):
    upsert_rules(
        db_path,
        [{"section": "experience", "rule_key": "max_entries", "rule_value": "99"}],
    )
    rules = reset_rules(db_path)
    rule = next(
        r for r in rules if r.section == "experience" and r.rule_key == "max_entries"
    )
    assert rule.rule_value == "2"


# --- System prompt -----------------------------------------------------------


def test_get_system_prompt_returns_seeded_default(db_path):
    prompt = get_system_prompt(db_path)
    assert prompt is not None
    assert prompt.content == DEFAULT_SYSTEM_PROMPT


def test_upsert_and_reset_system_prompt(db_path):
    upsert_system_prompt(db_path, "Custom prompt")
    assert get_system_prompt(db_path).content == "Custom prompt"
    assert ISO_UTC.match(get_system_prompt(db_path).updated_at)
    reset_system_prompt(db_path)
    assert get_system_prompt(db_path).content == DEFAULT_SYSTEM_PROMPT


def test_system_prompt_user_id_is_unique(db_path):
    with raw(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO system_prompt (user_id, content) VALUES ('default', 'x')"
        )


def test_upsert_system_prompt_never_adds_a_row(db_path):
    for i in range(5):
        upsert_system_prompt(db_path, f"prompt {i}")
    with raw(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM system_prompt").fetchone()[0]
    assert count == 1
