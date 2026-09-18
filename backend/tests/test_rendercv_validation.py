"""Tests for rendercv schema-validation failure modes in normalize_to_rendercv.

Each test reproduces a real failure observed when feeding LLM-generated YAML
to `rendercv render` (rendercv 2.8 validates with pydantic + phonenumbers).
"""
import yaml
import pytest

from resumetailor.yaml_utils import normalize_to_rendercv


def _norm(raw: str) -> dict:
    return yaml.safe_load(normalize_to_rendercv(raw))


MINIMAL_SKILLS = "    skills:\n    - label: Skills\n      details: Python\n"


# ---------------------------------------------------------------- phone

def test_invalid_phone_dropped():
    """123 is not a real US area code — rendercv rejects it, so drop it."""
    raw = "cv:\n  name: Jane\n  phone: 123-456-7890\n  sections:\n" + MINIMAL_SKILLS
    assert "phone" not in _norm(raw)["cv"]


def test_placeholder_phone_dropped():
    """555-000-0000 passes the old format check but fails phonenumbers."""
    raw = 'cv:\n  name: Jane\n  phone: "+1-555-000-0000"\n  sections:\n' + MINIMAL_SKILLS
    assert "phone" not in _norm(raw)["cv"]


def test_valid_us_phone_normalized():
    raw = "cv:\n  name: Jane\n  phone: (212) 683-3200\n  sections:\n" + MINIMAL_SKILLS
    assert _norm(raw)["cv"]["phone"] == "+12126833200"


def test_international_phone_kept():
    """Valid non-US numbers used to be silently dropped by the 10/11-digit check."""
    raw = 'cv:\n  name: Jane\n  phone: "+91 98765 43210"\n  sections:\n' + MINIMAL_SKILLS
    assert _norm(raw)["cv"]["phone"] == "+919876543210"


# ---------------------------------------------------------------- sections

def test_null_section_dropped_without_crash():
    """`certifications:` with no value crashed _normalize_certifications."""
    raw = (
        "cv:\n  name: Jane\n  sections:\n    certifications:\n" + MINIMAL_SKILLS
    )
    result = _norm(raw)
    assert "certifications" not in result["cv"]["sections"]
    assert "skills" in result["cv"]["sections"]


def test_scalar_section_wrapped_in_list():
    """rendercv requires every section to be a list of entries."""
    raw = (
        "cv:\n  name: Jane\n  sections:\n"
        "    summary: Experienced backend engineer.\n" + MINIMAL_SKILLS
    )
    assert _norm(raw)["cv"]["sections"]["summary"] == ["Experienced backend engineer."]


# ---------------------------------------------------------------- entries

def test_none_highlight_filtered():
    raw = (
        "cv:\n  name: Jane\n  sections:\n"
        "    experience:\n"
        "    - company: Acme\n"
        "      position: Engineer\n"
        "      highlights:\n"
        "      - Built things\n"
        "      -\n"
    )
    entry = _norm(raw)["cv"]["sections"]["experience"][0]
    assert entry["highlights"] == ["Built things"]


def test_reversed_dates_swapped():
    raw = (
        "cv:\n  name: Jane\n  sections:\n"
        "    experience:\n"
        "    - company: Acme\n"
        "      position: Engineer\n"
        '      start_date: "2024-01"\n'
        '      end_date: "2023-06"\n'
    )
    entry = _norm(raw)["cv"]["sections"]["experience"][0]
    assert entry["start_date"] == "2023-06"
    assert entry["end_date"] == "2024-01"


def test_education_without_area_uses_degree_text():
    """rendercv requires `area` on EducationEntry; fall back to the degree text."""
    raw = (
        "cv:\n  name: Jane\n  sections:\n"
        "    education:\n"
        "    - institution: NYU\n"
        "      degree: MBA\n"
        '      start_date: "2020-09"\n'
        '      end_date: "2022-05"\n'
    )
    entry = _norm(raw)["cv"]["sections"]["education"][0]
    assert entry["area"] == "MBA"


# ---------------------------------------------------------------- socials

def test_twitter_mapped_to_x():
    raw = (
        "cv:\n  name: Jane\n"
        "  social_networks:\n"
        "  - network: Twitter\n"
        "    username: janedoe\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    nets = _norm(raw)["cv"]["social_networks"]
    assert nets == [{"network": "X", "username": "janedoe"}]


def test_unknown_network_dropped():
    raw = (
        "cv:\n  name: Jane\n"
        "  social_networks:\n"
        "  - network: Portfolio\n"
        "    username: https://jane.dev\n"
        "  - network: github\n"
        "    username: janedoe\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    nets = _norm(raw)["cv"]["social_networks"]
    assert nets == [{"network": "GitHub", "username": "janedoe"}]


def test_url_username_stripped_to_handle():
    raw = (
        "cv:\n  name: Jane\n"
        "  social_networks:\n"
        "  - network: LinkedIn\n"
        "    username: https://www.linkedin.com/in/jane-doe/\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    nets = _norm(raw)["cv"]["social_networks"]
    assert nets == [{"network": "LinkedIn", "username": "jane-doe"}]


# ---------------------------------------------------------------- cv keys

def test_unknown_cv_key_dropped_and_label_becomes_headline():
    raw = (
        "cv:\n  name: Jane\n"
        "  label: Senior Engineer\n"
        "  objective_statement: something\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    cv = _norm(raw)["cv"]
    assert cv.get("headline") == "Senior Engineer"
    assert "label" not in cv
    assert "objective_statement" not in cv


# ---------------------------------------------------------------- backstop

def test_backstop_prunes_fields_normalizer_does_not_know():
    """Anything the deterministic fixes miss must be pruned by schema validation."""
    raw = (
        "cv:\n  name: Jane\n"
        "  email: not-an-email\n"
        "  sections:\n" + MINIMAL_SKILLS
    )
    cv = _norm(raw)["cv"]
    assert "email" not in cv
    assert cv["name"] == "Jane"


def test_normalized_output_passes_rendercv_schema():
    """End-to-end: nasty-but-salvageable input must validate against rendercv."""
    pytest.importorskip("rendercv")
    from rendercv.schema.rendercv_model_builder import (
        build_rendercv_model_from_commented_map,
    )

    raw = """
cv:
  name: Jane Doe
  label: Senior Engineer
  email: jane@example.com
  phone: "555-000-0000"
  contact:
    linkedin: linkedin.com/in/jane-doe
  social_networks:
    - network: Twitter
      username: janedoe
  summary: Ten years of backend experience.
  sections:
    certifications:
    experience:
      - company: Acme
        position: Engineer
        start_date: "2024-01"
        end_date: "2023-06"
        highlights:
          - Built things
          -
    education:
      - institution: NYU
        degree: MBA
        duration: "Sept 2020 to May 2022"
        gpa: 3.9
"""
    data = yaml.safe_load(normalize_to_rendercv(raw))
    data["design"] = {"theme": "classic"}
    build_rendercv_model_from_commented_map(data)  # must not raise
