import sqlite3
import tempfile
import os
import pytest
from resumetailor.database import (
    init_db, DEFAULT_RULES, DEFAULT_SYSTEM_PROMPT,
    get_master_resume, upsert_master_resume, delete_master_resume,
    list_resumes, create_resume, get_resume, update_resume, delete_resume,
    get_chat_messages, add_chat_message, clear_chat,
    get_rules, upsert_rules, reset_rules,
    get_system_prompt, upsert_system_prompt, reset_system_prompt,
)


@pytest.fixture
def temp_db():
    """Fixture that provides a temporary database path."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_init_db_creates_all_tables(temp_db):
    init_db(temp_db)
    with sqlite3.connect(temp_db) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    expected = {
        "master_resume", "master_resume_history", "generated_resumes",
        "chat_messages", "generation_rules", "system_prompt",
    }
    # Exclude sqlite_sequence (internal SQLite table)
    tables = {t for t in tables if t != "sqlite_sequence"}
    assert expected == tables


def test_init_db_seeds_default_rules(temp_db):
    init_db(temp_db)
    with sqlite3.connect(temp_db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM generation_rules WHERE user_id = 'default'"
        ).fetchone()[0]
    assert count == len(DEFAULT_RULES)


def test_init_db_seeds_default_system_prompt(temp_db):
    init_db(temp_db)
    with sqlite3.connect(temp_db) as conn:
        row = conn.execute(
            "SELECT content FROM system_prompt WHERE user_id = 'default'"
        ).fetchone()
    assert row is not None
    assert row[0] == DEFAULT_SYSTEM_PROMPT


def test_init_db_is_idempotent(temp_db):
    init_db(temp_db)
    init_db(temp_db)  # second call must not raise or duplicate data
    with sqlite3.connect(temp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM system_prompt").fetchone()[0]
    assert count == 1


# --- Master Resume Tests ---

def test_get_master_resume_returns_none_when_empty(temp_db):
    init_db(temp_db)
    assert get_master_resume(temp_db) is None


def test_upsert_master_resume_creates_and_returns(temp_db):
    init_db(temp_db)
    result = upsert_master_resume(temp_db, "cv:\n  name: Test")
    assert result["yaml_content"] == "cv:\n  name: Test"
    assert result["user_id"] == "default"
    assert "id" in result
    assert "updated_at" in result


def test_upsert_master_resume_updates_existing(temp_db):
    init_db(temp_db)
    upsert_master_resume(temp_db, "cv:\n  name: First")
    result = upsert_master_resume(temp_db, "cv:\n  name: Second")
    assert result["yaml_content"] == "cv:\n  name: Second"
    # Only one row should exist
    with sqlite3.connect(temp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume").fetchone()[0]
    assert count == 1


def test_upsert_saves_to_history(temp_db):
    init_db(temp_db)
    upsert_master_resume(temp_db, "cv:\n  name: First")
    upsert_master_resume(temp_db, "cv:\n  name: Second")
    with sqlite3.connect(temp_db) as conn:
        history = conn.execute(
            "SELECT yaml_content FROM master_resume_history ORDER BY saved_at ASC"
        ).fetchall()
    assert len(history) == 1
    assert history[0][0] == "cv:\n  name: First"


def test_history_pruned_to_10(temp_db):
    init_db(temp_db)
    for i in range(12):
        upsert_master_resume(temp_db, f"cv:\n  name: Version{i}")
    with sqlite3.connect(temp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM master_resume_history").fetchone()[0]
    assert count == 10


def test_delete_master_resume(temp_db):
    init_db(temp_db)
    upsert_master_resume(temp_db, "cv:\n  name: Test")
    assert delete_master_resume(temp_db) is True
    assert get_master_resume(temp_db) is None


def test_delete_master_resume_returns_false_when_not_exist(temp_db):
    init_db(temp_db)
    assert delete_master_resume(temp_db) is False


# --- Generated Resumes Tests ---

def test_create_and_get_resume(temp_db):
    init_db(temp_db)
    r = create_resume(temp_db, "SWE @ Acme", "We need Python devs", "cv:\n  name: Test")
    assert r["name"] == "SWE @ Acme"
    assert r["job_description"] == "We need Python devs"
    assert r["pdf_path"] is None
    fetched = get_resume(temp_db, r["id"])
    assert fetched["id"] == r["id"]


def test_get_resume_returns_none_for_missing(temp_db):
    init_db(temp_db)
    assert get_resume(temp_db, 9999) is None


def test_list_resumes_pagination(temp_db):
    init_db(temp_db)
    for i in range(5):
        create_resume(temp_db, f"Resume {i}", f"JD {i}", "cv:\n  name: X")
    result = list_resumes(temp_db, page=1, limit=3)
    assert result["total"] == 5
    assert len(result["items"]) == 3
    assert result["page"] == 1


def test_list_resumes_sort_by_jd(temp_db):
    init_db(temp_db)
    create_resume(temp_db, "B", "Zebra Corp", "cv:\n  name: B")
    create_resume(temp_db, "A", "Apple Inc", "cv:\n  name: A")
    result = list_resumes(temp_db, sort="jd", order="asc")
    assert result["items"][0]["name"] == "A"


def test_update_resume_name(temp_db):
    init_db(temp_db)
    r = create_resume(temp_db, "Old Name", "JD", "cv:\n  name: X")
    updated = update_resume(temp_db, r["id"], name="New Name")
    assert updated["name"] == "New Name"


def test_update_resume_pdf_path(temp_db):
    init_db(temp_db)
    r = create_resume(temp_db, "Test", "JD", "cv:\n  name: X")
    updated = update_resume(temp_db, r["id"], pdf_path="42.pdf")
    assert updated["pdf_path"] == "42.pdf"


def test_delete_resume(temp_db):
    init_db(temp_db)
    r = create_resume(temp_db, "Test", "JD", "cv:\n  name: X")
    assert delete_resume(temp_db, r["id"]) is True
    assert get_resume(temp_db, r["id"]) is None


def test_delete_resume_returns_false_for_missing(temp_db):
    init_db(temp_db)
    assert delete_resume(temp_db, 9999) is False


# --- Chat Tests ---

def test_add_and_get_chat_messages(temp_db):
    init_db(temp_db)
    add_chat_message(temp_db, "user", "Hello")
    add_chat_message(temp_db, "assistant", "Hi there!")
    msgs = get_chat_messages(temp_db)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_clear_chat(temp_db):
    init_db(temp_db)
    add_chat_message(temp_db, "user", "Hello")
    clear_chat(temp_db)
    assert get_chat_messages(temp_db) == []


# --- Rules Tests ---

def test_get_rules_returns_seeded_defaults(temp_db):
    init_db(temp_db)
    rules = get_rules(temp_db)
    assert len(rules) == len(DEFAULT_RULES)
    keys = {(r["section"], r["rule_key"]) for r in rules}
    assert ("experience", "max_entries") in keys


def test_upsert_rules_updates_value(temp_db):
    init_db(temp_db)
    upsert_rules(temp_db, [{"section": "experience", "rule_key": "max_entries", "rule_value": "3"}])
    rules = get_rules(temp_db)
    exp_max = next(r for r in rules if r["section"] == "experience" and r["rule_key"] == "max_entries")
    assert exp_max["rule_value"] == "3"


def test_reset_rules_restores_defaults(temp_db):
    init_db(temp_db)
    upsert_rules(temp_db, [{"section": "experience", "rule_key": "max_entries", "rule_value": "99"}])
    reset_rules(temp_db)
    rules = get_rules(temp_db)
    exp_max = next(r for r in rules if r["section"] == "experience" and r["rule_key"] == "max_entries")
    assert exp_max["rule_value"] == "2"


# --- System Prompt Tests ---

def test_get_system_prompt_returns_seeded_default(temp_db):
    init_db(temp_db)
    sp = get_system_prompt(temp_db)
    assert sp is not None
    assert DEFAULT_SYSTEM_PROMPT in sp["content"]


def test_upsert_and_reset_system_prompt(temp_db):
    init_db(temp_db)
    upsert_system_prompt(temp_db, "Custom prompt")
    assert get_system_prompt(temp_db)["content"] == "Custom prompt"
    reset_system_prompt(temp_db)
    assert get_system_prompt(temp_db)["content"] == DEFAULT_SYSTEM_PROMPT
