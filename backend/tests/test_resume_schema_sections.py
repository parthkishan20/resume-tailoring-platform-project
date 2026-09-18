import yaml
from resumetailor.resume_schema.normalize import normalize_to_rendercv
from resumetailor.resume_schema.sections import normalize_certifications


def test_no_design_injected_when_absent():
    """normalize must NOT add a design: block — design comes from --design CLI flag."""
    raw = "cv:\n  name: Jane Doe\n  sections:\n    skills:\n    - label: Skills\n      details: Python\n"
    result = yaml.safe_load(normalize_to_rendercv(raw).yaml)
    assert "design" not in result


def test_design_stripped_from_cv_block():
    """LLM sometimes nests design: inside cv: — it must be removed, not hoisted."""
    raw = (
        "cv:\n"
        "  name: Jane Doe\n"
        "  design:\n"
        "    theme: classic\n"
        "  sections:\n"
        "    skills:\n"
        "    - label: Skills\n"
        "      details: Python\n"
    )
    result = yaml.safe_load(normalize_to_rendercv(raw).yaml)
    assert "design" not in result
    assert "design" not in result.get("cv", {})


def test_top_level_design_stripped():
    """If design: already sits at top level (e.g. from master resume), it must be removed."""
    raw = (
        "cv:\n"
        "  name: Jane Doe\n"
        "  sections:\n"
        "    skills:\n"
        "    - label: Skills\n"
        "      details: Python\n"
        "design:\n"
        "  theme: engineeringresumes\n"
    )
    result = yaml.safe_load(normalize_to_rendercv(raw).yaml)
    assert "design" not in result


def test_certifications_basic_entry():
    """Standard entry: issuer becomes a highlight, plain date stays in date."""
    out = normalize_certifications(
        [{"name": "AWS Developer", "issuer": "Amazon", "date": "2023"}]
    )
    assert out == [
        {"name": "AWS Developer", "date": "2023", "highlights": ["Issued by Amazon"]}
    ]


def test_certifications_experience_style_keys():
    """LLM sometimes routes experience-shaped entries into certifications."""
    out = normalize_certifications([{"position": "Engineer", "company": "Acme"}])
    assert out == [{"name": "Engineer", "highlights": ["Issued by Acme"]}]


def test_certifications_markdown_link_date_moved_to_highlights():
    """Markdown-link dates render in highlights, not the date field."""
    out = normalize_certifications(
        [{"name": "Cert", "date": "[Credential](https://example.com/cert)"}]
    )
    assert out == [
        {"name": "Cert", "highlights": ["[Credential](https://example.com/cert)"]}
    ]
    assert "date" not in out[0]


def test_certifications_markdown_link_with_parens_in_url():
    """URLs containing ')' must still be recognised as markdown links."""
    link = "[Verify](https://example.com/cert_(2023))"
    out = normalize_certifications([{"name": "Cert", "date": link}])
    assert out == [{"name": "Cert", "highlights": [link]}]


def test_certifications_markdown_link_date_with_whitespace():
    """Surrounding whitespace must not defeat markdown-link detection."""
    out = normalize_certifications(
        [{"name": "Cert", "date": " [Verify](https://example.com) "}]
    )
    assert out == [{"name": "Cert", "highlights": ["[Verify](https://example.com)"]}]
