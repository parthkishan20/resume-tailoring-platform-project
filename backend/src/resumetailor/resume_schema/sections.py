"""Per-section repairs, before RenderCV ever sees the document.

Each function here fixes one family of mistake that language models reliably
make about one section: calling a position a ``job_title``, writing a degree as
prose, putting a certification's issuer where RenderCV expects an institution.
They are deterministic and cheap; the schema backstop in ``repair.py`` is what
catches everything they do not know about.

Dispatch goes through :data:`SECTION_NORMALIZERS`, which includes
``work_experience`` (PLAN.md D-24): the key was being hoisted into
``cv.sections`` by the section-key logic while no normalizer ran on it, so it
reached RenderCV with ``job_title``/``responsibilities``/``duration`` intact.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_MONTH_MAP = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

_DEGREE_PREFIX_MAP = [
    (re.compile(r"^(master|m\.?\s*s\.?|msc|m\.?\s*eng\.?)", re.I), "MS"),
    (
        re.compile(r"^(bachelor|b\.?\s*s\.?|bsc|b\.?\s*eng\.?|b\.?\s*tech\.?)", re.I),
        "BS",
    ),
    (re.compile(r"^(ph\.?\s*d\.?|doctor)", re.I), "PhD"),
    (re.compile(r"^(associate)", re.I), "AS"),
    (re.compile(r"^mba$", re.I), "MBA"),
]

# Greedy URL match so parentheses inside the URL do not stop at the first ")".
_MARKDOWN_LINK_RE = re.compile(r"^\[([^\]]+)\]\((https?://.+)\)$")

_DATE_KEY_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")

_PRESENT_RE = re.compile(r"^(present|current|now)$", re.I)

# En dash, em dash, hyphen or the word "to", each optionally spaced.
_DURATION_SPLIT_RE = re.compile(r"\s*[\u2013\u2014-]\s*|\s+to\s+")
_DURATION_PARTS = 2


def parse_date(raw: str) -> str:
    """Coerce a human date to RenderCV's ``YYYY-MM``, or leave it alone."""
    s = raw.strip()
    if re.match(r"^\d{4}-\d{2}$", s):
        return s
    if _PRESENT_RE.match(s):
        return "present"
    # "Jan 2023" / "January 2023" / "Sept 2024"
    m = re.match(r"^([A-Za-z]+)\.?\s+(\d{4})$", s)
    if m:
        month = _MONTH_MAP.get(m.group(1).lower()[:3], "01")
        return f"{m.group(2)}-{month}"
    if re.match(r"^\d{4}$", s):
        return s
    return s


def date_sort_key(value: Any) -> tuple[int, int, int] | None:
    m = _DATE_KEY_RE.match(str(value).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def fix_date_order(entry: dict[str, Any]) -> None:
    """Swap start/end when reversed — RenderCV rejects start_date > end_date."""
    start = date_sort_key(entry.get("start_date"))
    end = date_sort_key(entry.get("end_date"))
    if start and end and start > end:
        entry["start_date"], entry["end_date"] = entry["end_date"], entry["start_date"]


def clean_highlights(entry: dict[str, Any]) -> None:
    """Drop null and blank highlights — RenderCV requires each to be a string."""
    highlights = entry.get("highlights")
    if isinstance(highlights, list):
        cleaned = [str(h) for h in highlights if h is not None and str(h).strip()]
        if cleaned:
            entry["highlights"] = cleaned
        else:
            entry.pop("highlights")


def split_degree(raw: str) -> tuple[str, str]:
    """Split ``"Master in Computer Science"`` into ``("MS", "Computer Science")``."""
    # Find the area after " in " or " of [Science|Arts|...] in "
    m = re.search(r"\s+(?:of\s+\w+\s+)?in\s+(.+)$", raw, re.I)
    area = m.group(1).strip() if m else ""
    deg_part = raw[: m.start()].strip() if m else raw.strip()
    for pattern, short in _DEGREE_PREFIX_MAP:
        if pattern.match(deg_part):
            return short, area
    return deg_part, area


def _split_duration(entry: dict[str, Any]) -> None:
    raw = entry.pop("duration", None)
    if not raw:
        return
    parts = _DURATION_SPLIT_RE.split(str(raw).strip(), maxsplit=1)
    if len(parts) == _DURATION_PARTS:
        entry.setdefault("start_date", parse_date(parts[0]))
        end = parts[1].strip()
        if _PRESENT_RE.match(end):
            entry.setdefault("end_date", "present")
        else:
            entry.setdefault("end_date", parse_date(end))
    else:
        entry.setdefault("date", str(raw).strip())


def normalize_experience(entries: list[Any]) -> list[dict[str, Any]]:
    """``job_title`` → ``position``, ``responsibilities`` → ``highlights``."""
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if "job_title" in e and "position" not in e:
            e["position"] = e.pop("job_title")
        if "responsibilities" in e and "highlights" not in e:
            e["highlights"] = e.pop("responsibilities")
        _split_duration(e)
        out.append(e)
    return out


def normalize_education(entries: list[Any]) -> list[dict[str, Any]]:
    """Split a prose degree into ``degree`` + ``area``; fold GPA into highlights."""
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        _split_duration(e)
        # "Master in Computer Science" → degree + area (area is required)
        if "degree" in e and "area" not in e:
            short, area = split_degree(str(e["degree"]))
            e["degree"] = short
            if area:
                e["area"] = area
        # RenderCV requires `area` on EducationEntry — fall back to degree text
        if not e.get("area") and e.get("degree"):
            e["area"] = str(e.pop("degree"))
        highlights: list[str] = e.setdefault("highlights", [])
        for gpa_key in ("gpa", "cgpa"):
            if gpa_key in e:
                val = e.pop(gpa_key)
                label = f"GPA: {val}"
                if label not in highlights:
                    highlights.append(label)
        if not highlights:
            e.pop("highlights", None)
        out.append(e)
    return out


def normalize_projects(entries: list[Any]) -> list[dict[str, Any]]:
    """``title`` → ``name``, prose ``description`` → ``highlights``."""
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if "title" in e and "name" not in e:
            e["name"] = e.pop("title")
        if "description" in e and "highlights" not in e:
            desc = e.pop("description")
            if isinstance(desc, str):
                lines = [ln.strip() for ln in desc.strip().splitlines() if ln.strip()]
                e["highlights"] = lines or [desc.strip()]
            elif isinstance(desc, list):
                e["highlights"] = [str(x) for x in desc]
        _split_duration(e)
        # Discard placeholder link values like the literal string "link"
        link = e.pop("link", None)
        if link and str(link).strip().lower() not in ("", "link", "n/a", "none"):
            e.setdefault("url", str(link))
        out.append(e)
    return out


def normalize_certifications(entries: list[Any]) -> list[dict[str, Any]]:
    """Convert certification entries to a RenderCV ``NormalEntry``.

    RenderCV infers ``EducationEntry`` the moment it sees ``institution``,
    which then requires ``area``. Mapping certification data onto ``name`` plus
    ``highlights`` avoids that inference entirely.
    """
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = e.get("name") or e.get("title") or e.get("certificate") or ""
        issuer = e.get("institution") or e.get("issuer") or e.get("organization") or ""
        # Fall back to experience-style keys, but warn: their presence means the
        # model routed an experience-shaped entry into certifications.
        if not name and e.get("position"):
            name = e["position"]
            logger.warning(
                "certification entry used experience-style 'position' key: %r", e
            )
        if not issuer and e.get("company"):
            issuer = e["company"]
            logger.warning(
                "certification entry used experience-style 'company' key: %r", e
            )
        date_raw = str(e.get("date") or e.get("year") or "").strip()
        norm: dict[str, Any] = {"name": name}
        highlights: list[str] = []
        if issuer:
            highlights.append(f"Issued by {issuer}")
        # A markdown-link date renders as a highlight: RenderCV renders markdown
        # in highlights but not in the date field.
        if date_raw and _MARKDOWN_LINK_RE.match(date_raw):
            highlights.append(date_raw)
        elif date_raw:
            norm["date"] = date_raw
        if highlights:
            norm["highlights"] = highlights
        out.append(norm)
    return out


def normalize_skills(entries: list[Any]) -> list[Any]:
    """Coerce whatever shape the skills arrived in into ``{label, details}``."""
    if not entries:
        return entries
    first = entries[0]
    # Already correct: [{label, details}, ...]
    if isinstance(first, dict) and "label" in first:
        return entries
    # Flat list of strings: collapse into a single group
    if isinstance(first, str):
        return [{"label": "Skills", "details": ", ".join(str(s) for s in entries)}]
    if isinstance(first, dict):
        out = []
        for s in entries:
            if "category" in s and "label" not in s:
                s["label"] = s.pop("category")
            if "items" in s and "details" not in s:
                items = s.pop("items")
                if isinstance(items, list):
                    s["details"] = ", ".join(str(i) for i in items)
            out.append(s)
        return out
    return entries


#: Section key to the normalizer that runs on it. ``work_experience`` shares
#: ``experience``'s normalizer rather than being renamed to it, so a document
#: that carries both keeps both sections and their titles.
SECTION_NORMALIZERS: dict[str, Callable[[list[Any]], list[Any]]] = {
    "experience": normalize_experience,
    "work_experience": normalize_experience,
    "education": normalize_education,
    "projects": normalize_projects,
    "skills": normalize_skills,
    "certifications": normalize_certifications,
}
