"""The canonical schema is one source of truth, and it reports what it drops.

Covers D-08 (diagnostics instead of silent deletion), D-17 (the backstop is
imported once and fails loud), D-18 (theme parity), D-22 (one source of truth)
and D-24 (`work_experience` is normalized).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from resumetailor.rendering.config import RenderProfile
from resumetailor.resume_schema import models, prompt
from resumetailor.resume_schema.normalize import normalize_to_rendercv
from resumetailor.resume_schema.validate import validate

MINIMAL_SKILLS = "    skills:\n    - label: Skills\n      details: Python\n"


# ------------------------------------------------------------------ D-22


def test_cv_keys_come_from_rendercv_not_from_a_hand_written_set():
    from rendercv.schema.models.cv.cv import Cv

    assert frozenset(Cv.model_fields) == models.CV_KEYS
    assert "sections" in models.CV_KEYS


def test_social_networks_come_from_rendercv_literal():
    from rendercv.schema.models.cv.social_network import available_social_networks

    assert set(models.SOCIAL_NETWORKS.values()) == set(available_social_networks)
    # The hand-written set this replaced listed exactly these seventeen; the
    # point is that it is no longer hand-written.
    assert models.canonical_network("google scholar") == "Google Scholar"
    assert models.canonical_network("Twitter") == "X"
    assert models.canonical_network("Portfolio") is None


def test_import_prompt_is_generated_and_no_longer_contradicts_the_normalizer():
    """The old prompt asked for `design: theme: classic`, which we then stripped."""
    text = prompt.IMPORT_SYSTEM_PROMPT
    assert "theme: classic" not in text
    assert "Do NOT output a `design:` block" in text
    # Every network RenderCV accepts is offered, not just LinkedIn and GitHub.
    for network in models.SOCIAL_NETWORKS.values():
        assert network in text


def test_schema_block_names_every_required_entry_field():
    block = prompt.schema_block()
    for section, _omit in prompt._PROMPTED_SECTIONS:
        model = models.SECTION_TO_ENTRY[section]
        for name in models.required_fields(model):
            assert f"{name}:" in block, (section, name)


def test_schema_block_dates_match_the_format_the_rules_demand():
    """The old prompt's examples and its own rules disagreed. D-22."""
    block = prompt.schema_block()
    for line in block.splitlines():
        key, _, rest = line.partition(":")
        if key.strip() in ("date", "start_date", "end_date"):
            value = rest.split("#")[0].strip()
            assert re.fullmatch(r"\d{4}-\d{2}", value), line


def test_a_span_section_is_not_also_offered_a_single_date():
    """RenderCV ignores start/end when `date` is set; do not offer both."""
    block = prompt.schema_block()
    experience = block.split("experience:")[1].split("education:")[0]
    assert "start_date:" in experience
    assert "\n        date:" not in experience


def test_generated_schema_block_is_parseable_yaml():
    """A schema the model is told to copy verbatim had better be valid YAML."""
    assert isinstance(yaml.safe_load(prompt.schema_block()), dict)


# ------------------------------------------------------------------ D-24


def test_work_experience_is_normalized_like_experience():
    raw = (
        "cv:\n  name: Jane\n"
        "  work_experience:\n"
        "  - company: Acme\n"
        "    job_title: Engineer\n"
        "    duration: Jan 2022 - present\n"
        "    responsibilities:\n"
        "    - Built things\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    entry = yaml.safe_load(normalize_to_rendercv(raw).yaml)["cv"]["sections"][
        "work_experience"
    ][0]
    assert entry["position"] == "Engineer"
    assert entry["highlights"] == ["Built things"]
    assert entry["start_date"] == "2022-01"
    assert entry["end_date"] == "present"
    assert "job_title" not in entry
    assert "duration" not in entry


# ------------------------------------------------------------------ D-08


def test_dropped_phone_is_reported_not_only_logged():
    raw = 'cv:\n  name: Jane\n  phone: "+1-555-000-0000"\n  sections:\n' + (
        MINIMAL_SKILLS
    )
    result = normalize_to_rendercv(raw)
    assert "phone" not in yaml.safe_load(result.yaml)["cv"]
    dropped = [d for d in result.dropped if d.path == ("cv", "phone")]
    assert len(dropped) == 1
    assert "555" in dropped[0].value
    assert dropped[0].reason


def test_dropped_email_from_the_backstop_is_reported():
    raw = "cv:\n  name: Jane\n  email: not-an-email\n  sections:\n" + MINIMAL_SKILLS
    result = normalize_to_rendercv(raw)
    assert "email" not in yaml.safe_load(result.yaml)["cv"]
    assert any(d.path == ("cv", "email") for d in result.dropped)


def test_dropped_social_network_and_unknown_key_are_reported():
    raw = (
        "cv:\n  name: Jane\n"
        "  objective_statement: something\n"
        "  social_networks:\n"
        "  - network: Portfolio\n"
        "    username: https://jane.dev\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    paths = {d.field_path for d in normalize_to_rendercv(raw).dropped}
    assert "cv.objective_statement" in paths
    assert "cv.social_networks" in paths


def test_a_clean_document_reports_nothing_dropped():
    raw = "cv:\n  name: Jane\n  email: jane@example.com\n  sections:\n" + MINIMAL_SKILLS
    assert normalize_to_rendercv(raw).dropped == []


def test_unparseable_yaml_is_returned_verbatim():
    """Unchanged behaviour: the render reports the real error, not this function."""
    raw = "cv: [unclosed\n"
    result = normalize_to_rendercv(raw)
    assert result.yaml == raw
    assert result.dropped == []


# ------------------------------------------------------------------ D-17, D-18


def test_backstop_imports_rendercv_at_module_load():
    """The symbols the backstop needs are bound at import, not inside a try."""
    from resumetailor.resume_schema import repair

    assert repair.build_rendercv_model_from_commented_map is not None
    assert repair.RenderCVUserValidationError is not None


def test_backstop_probes_with_the_configured_theme(monkeypatch, tmp_path):
    """D-18: change the design file's theme and the probe follows it."""
    from resumetailor.resume_schema import repair

    design = tmp_path / "design.yaml"
    design.write_text("design:\n  theme: sb2nov\n", encoding="utf-8")
    profile = RenderProfile(design_path=design)

    seen: list[str] = []
    real = repair.build_rendercv_model_from_commented_map

    def spy(commented_map, *args, **kwargs):
        seen.append(commented_map["design"]["theme"])
        return real(commented_map, *args, **kwargs)

    monkeypatch.setattr(repair, "build_rendercv_model_from_commented_map", spy)
    repair.validate_and_repair(
        {
            "cv": {
                "name": "Jane",
                "sections": {"skills": [{"label": "S", "details": "P"}]},
            }
        },
        profile,
    )
    assert seen == ["sb2nov"]


# --- validate() -----------------------------------------------------------


def test_validate_accepts_a_good_document():
    raw = "cv:\n  name: Jane\n  email: jane@example.com\n  sections:\n" + MINIMAL_SKILLS
    document, issues = validate(raw)
    assert issues == []
    assert document.is_valid
    assert document.cv["name"] == "Jane"


def test_validate_locates_a_bad_field():
    raw = "cv:\n  name: Jane\n  email: not-an-email\n  sections:\n" + MINIMAL_SKILLS
    document, issues = validate(raw)
    assert not document.is_valid
    assert any(issue.location == ("cv", "email") for issue in issues)
    assert all(issue.message for issue in issues)


def test_validate_reports_unparseable_yaml_without_raising():
    document, issues = validate("cv: [unclosed\n")
    assert not document.is_valid
    assert len(issues) == 1
    assert issues[0].path == "<document>"


def test_validate_rejects_a_non_mapping():
    _, issues = validate("- just\n- a list\n")
    assert len(issues) == 1


# ------------------------------------------------------------------ end to end


@pytest.mark.slow
@pytest.mark.integration
def test_rendercv_accepts_the_exact_command_line_the_runner_builds(tmp_path):
    """The three overlay flags are real flags and the three files really load.

    This is the test that catches a settings.yaml RenderCV refuses: the old one
    named `render_command.design`/`locale`, which RenderCV resolves relative to
    the *input* file and so could never exist.
    """
    from resumetailor.rendering.runner import RenderCVAdapter

    profile = RenderProfile()
    yaml_path = tmp_path / "resume.yaml"
    pdf_path = tmp_path / "resume.pdf"
    yaml_path.write_text(
        normalize_to_rendercv(
            "cv:\n  name: Jane Doe\n  email: jane@example.com\n  sections:\n"
            "    experience:\n"
            "    - company: Acme\n      position: Engineer\n"
            '      start_date: "2022-01"\n      end_date: present\n'
            "      highlights:\n      - Built things\n"
        ).yaml,
        encoding="utf-8",
    )
    command = list(RenderCVAdapter(profile)._command(yaml_path, pdf_path))
    # The runner relies on PATH, which `uv run` sets and a bare interpreter does
    # not. Resolve it here rather than skipping: rendercv[full] is a declared
    # dependency, so a missing binary is a real failure.
    beside_interpreter = Path(sys.executable).parent / "rendercv"
    resolved = shutil.which("rendercv") or (
        str(beside_interpreter) if beside_interpreter.exists() else None
    )
    assert resolved, "rendercv is not installed; it is a declared dependency"
    command[0] = resolved

    completed = subprocess.run(  # noqa: S603 — the command is built by the runner
        command, capture_output=True, text=True, timeout=180, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert pdf_path.read_bytes()[:4] == b"%PDF"
