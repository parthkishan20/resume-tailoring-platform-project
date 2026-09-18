"""Regression coverage for the harness guards in `conftest.py` itself.

A guard that nobody tests is a claim, not a fact. These tests exercise the
D-66 harness-level guard: `dotenv.load_dotenv` is neutralized for the whole
process, at conftest import time, so no dependency's own dotenv side effect
can fill a real credential into `os.environ` during a test — or during
collection, before any fixture has run.
"""

from __future__ import annotations

import os

import dotenv
import pytest

from tests.conftest import D66_GUARD_MARKER, REAL_LOAD_DOTENV


def test_dotenv_load_dotenv_is_replaced_with_the_guard_for_the_whole_process():
    """The module attribute litellm (and anything else) actually calls."""
    assert getattr(dotenv.load_dotenv, D66_GUARD_MARKER, False) is True
    assert dotenv.load_dotenv is not REAL_LOAD_DOTENV


def test_guarded_load_dotenv_does_not_fill_an_absent_variable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Reproduces the exact D-66 mechanism and proves the guard closes it.

    D-66: a real-looking variable is absent from `os.environ`; some dependency
    calls `dotenv.load_dotenv(override=False)` at import time; `find_dotenv()`
    walks up from the working directory and finds a `.env` that defines the
    variable; the real value is filled into the process. Here the "real"
    value is a planted fixture rather than an actual secret, so the test is
    self-contained and does not depend on this repo's own `.env`.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_REAL_LOOKING_CREDENTIAL=leaked-value\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOME_REAL_LOOKING_CREDENTIAL", raising=False)

    # The exact call `litellm/__init__.py` makes.
    result = dotenv.load_dotenv(override=False)

    assert result is False
    assert "SOME_REAL_LOOKING_CREDENTIAL" not in os.environ


def test_the_unguarded_function_would_have_leaked_it(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Proves the regression test above is load-bearing, not vacuous.

    Calls the real `load_dotenv` this harness saved off before patching it,
    against the same planted `.env`, to show the leak is real absent the
    guard — the counterfactual the guard exists to prevent.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_REAL_LOOKING_CREDENTIAL=leaked-value\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOME_REAL_LOOKING_CREDENTIAL", raising=False)

    result = REAL_LOAD_DOTENV(override=False)

    assert result is True
    assert os.environ["SOME_REAL_LOOKING_CREDENTIAL"] == "leaked-value"
    # Clean up: this is the one test in the suite that deliberately calls the
    # real loader, so it must not leak the planted value into any other test.
    # `pristine_env` (autouse) also restores `os.environ` at teardown, but
    # deleting it here keeps the intent local to the test that caused it.
    monkeypatch.delenv("SOME_REAL_LOOKING_CREDENTIAL", raising=False)
