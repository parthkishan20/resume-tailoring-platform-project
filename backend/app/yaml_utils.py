"""Normalise LLM-generated YAML to valid rendercv schema.

rendercv schema summary:
  cv:
    name, email, phone, location, website, social_networks: [{network, username}]
    sections:
      experience:   [{company, position, location, start_date, end_date, highlights}]
      education:    [{institution, area, degree, start_date, end_date, date, highlights}]
      projects:     [{name, date, url, highlights}]
      skills:       [{label, details}]
      certifications: [{name, date, highlights}]
  (design is stripped from output — provided externally via --design CLI flag)
"""
from __future__ import annotations
import copy
import logging
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# cv-level keys accepted by rendercv's Cv model (anything else fails validation
# with "This field is unknown for this object").
_CV_ALLOWED_KEYS = {
    "name", "headline", "location", "email", "photo", "phone", "website",
    "social_networks", "custom_connections", "sections",
}

# Networks accepted by rendercv's SocialNetwork model, keyed for
# case/spacing-insensitive lookup.
_VALID_NETWORKS = {
    n.lower().replace(" ", ""): n
    for n in (
        "LinkedIn", "GitHub", "GitLab", "IMDB", "Instagram", "ORCID",
        "Mastodon", "StackOverflow", "ResearchGate", "YouTube",
        "Google Scholar", "Telegram", "WhatsApp", "Leetcode", "X",
        "Bluesky", "Reddit",
    )
}
_NETWORK_ALIASES = {"twitter": "X", "googlescholar": "Google Scholar"}


_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

_SECTION_KEYS = (
    "experience", "education", "projects", "skills", "certifications",
    "summary", "publications", "awards", "languages", "interests",
    "extra_curricular_activities", "work_experience",
)

_DEGREE_PREFIX_MAP = [
    (re.compile(r"^(master|m\.?\s*s\.?|msc|m\.?\s*eng\.?)", re.I), "MS"),
    (re.compile(r"^(bachelor|b\.?\s*s\.?|bsc|b\.?\s*eng\.?|b\.?\s*tech\.?)", re.I), "BS"),
    (re.compile(r"^(ph\.?\s*d\.?|doctor)", re.I), "PhD"),
    (re.compile(r"^(associate)", re.I), "AS"),
    (re.compile(r"^mba$", re.I), "MBA"),
]


def _parse_date(raw: str) -> str:
    s = raw.strip()
    if re.match(r"^\d{4}-\d{2}$", s):
        return s
    if re.match(r"^(present|current|now)$", s, re.I):
        return "present"
    # "Jan 2023" / "January 2023" / "Sept 2024"
    m = re.match(r"^([A-Za-z]+)\.?\s+(\d{4})$", s)
    if m:
        month = _MONTH_MAP.get(m.group(1).lower()[:3], "01")
        return f"{m.group(2)}-{month}"
    # bare year
    if re.match(r"^\d{4}$", s):
        return s
    return s


def _normalize_phone(raw: str) -> str | None:
    """Normalise to E.164 if the number is real; None if rendercv would reject it.

    rendercv validates phones semantically with the phonenumbers library, so
    format-only fixes are not enough — placeholders like 555-000-0000 must be
    dropped rather than fail the whole render.
    """
    import phonenumbers  # noqa: PLC0415 — only needed when a phone is present

    s = raw.strip()
    for region in (None, "US"):
        try:
            parsed = phonenumbers.parse(s, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
    logger.warning("dropping phone rendercv would reject: %r", raw)
    return None


def _normalize_url(raw: str) -> str:
    if raw and not re.match(r"^https?://", raw):
        return f"https://{raw}"
    return raw


_DATE_KEY_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def _date_sort_key(value: Any) -> tuple[int, int, int] | None:
    m = _DATE_KEY_RE.match(str(value).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def _fix_date_order(entry: dict[str, Any]) -> None:
    """Swap start/end when reversed — rendercv rejects start_date > end_date."""
    start = _date_sort_key(entry.get("start_date"))
    end = _date_sort_key(entry.get("end_date"))
    if start and end and start > end:
        entry["start_date"], entry["end_date"] = entry["end_date"], entry["start_date"]


def _clean_highlights(entry: dict[str, Any]) -> None:
    """Drop null/blank highlights — rendercv requires each to be a string."""
    highlights = entry.get("highlights")
    if isinstance(highlights, list):
        cleaned = [str(h) for h in highlights if h is not None and str(h).strip()]
        if cleaned:
            entry["highlights"] = cleaned
        else:
            entry.pop("highlights")


def _social_username(network: str, raw: str) -> str:
    """Strip URL decoration: 'https://linkedin.com/in/jane/' → 'jane'."""
    u = str(raw).strip().strip("/")
    if re.match(r"^(https?://|www\.)", u) or "/" in u:
        segments = [s for s in u.split("/") if s]
        u = segments[-1] if segments else ""
    return u


def _normalize_social_networks(cv: dict[str, Any]) -> None:
    raw_networks = cv.get("social_networks")
    if not isinstance(raw_networks, list):
        if raw_networks is not None:
            cv.pop("social_networks", None)
        return
    out = []
    for s in raw_networks:
        if not isinstance(s, dict):
            continue
        key = str(s.get("network", "")).lower().replace(" ", "")
        network = _NETWORK_ALIASES.get(key) or _VALID_NETWORKS.get(key)
        if not network:
            logger.warning("dropping social network rendercv rejects: %r", s)
            continue
        username = _social_username(network, s.get("username", ""))
        if not username:
            continue
        out.append({"network": network, "username": username})
    if out:
        cv["social_networks"] = out
    else:
        cv.pop("social_networks", None)


def _split_degree(raw: str) -> tuple[str, str]:
    """Split 'Master in Computer Science' → ('MS', 'Computer Science')."""
    # Find area after " in " or " of [Science|Arts|...] in "
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
    parts = re.split(r"\s*[–—]\s*|\s*-\s*|\s+to\s+", str(raw).strip(), maxsplit=1)
    if len(parts) == 2:
        entry.setdefault("start_date", _parse_date(parts[0]))
        end = parts[1].strip()
        if re.match(r"^(present|current|now)$", end, re.I):
            entry.setdefault("end_date", "present")
        else:
            entry.setdefault("end_date", _parse_date(end))
    else:
        entry.setdefault("date", str(raw).strip())


def _normalize_experience(entries: list[Any]) -> list[dict]:
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


def _normalize_education(entries: list[Any]) -> list[dict]:
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        _split_duration(e)
        # Split "Master in Computer Science" → degree + area (area is required by rendercv)
        if "degree" in e and "area" not in e:
            short, area = _split_degree(str(e["degree"]))
            e["degree"] = short
            if area:
                e["area"] = area
        # rendercv requires `area` on EducationEntry — fall back to degree text
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


def _normalize_projects(entries: list[Any]) -> list[dict]:
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if "title" in e and "name" not in e:
            e["name"] = e.pop("title")
        if "description" in e and "highlights" not in e:
            desc = e.pop("description")
            if isinstance(desc, str):
                lines = [l.strip() for l in desc.strip().splitlines() if l.strip()]
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


# Greedy URL match so parentheses inside the URL don't stop at the first ")".
_MARKDOWN_LINK_RE = re.compile(r"^\[([^\]]+)\]\((https?://.+)\)$")


def _normalize_certifications(entries: list[Any]) -> list[dict]:
    """Convert certification entries to rendercv NormalEntry (name + highlights).

    rendercv infers EducationEntry when it sees `institution`, which then requires
    `area`. Avoid that by mapping certification data to NormalEntry fields.
    """
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        # Resolve the name — also accept experience-style keys
        name = e.get("name") or e.get("title") or e.get("certificate") or ""
        issuer = (
            e.get("institution") or e.get("issuer") or e.get("organization") or ""
        )
        # Fall back to experience-style keys, but warn: their presence means the
        # LLM routed an experience-shaped entry into certifications.
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
        # If date is a markdown link, render it as a highlight (rendercv renders
        # markdown in highlights but not in the date field).
        if date_raw and _MARKDOWN_LINK_RE.match(date_raw):
            highlights.append(date_raw)
        elif date_raw:
            norm["date"] = date_raw
        if highlights:
            norm["highlights"] = highlights
        out.append(norm)
    return out


def _normalize_skills(entries: list[Any]) -> list[dict]:
    if not entries:
        return entries
    first = entries[0]
    # Already correct: [{label, details}, ...]
    if isinstance(first, dict) and "label" in first:
        return entries
    # Flat list of strings: convert to a single group
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


def _prune_path(data: dict[str, Any], loc: tuple[str, ...]) -> bool:
    """Remove the value at a rendercv error location like ('cv', 'sections',
    'experience', '0', 'highlights', '1'). Returns True if something was removed."""
    node: Any = data
    for part in loc[:-1]:
        if isinstance(node, list):
            if not str(part).isdigit() or int(part) >= len(node):
                return False
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                return False
            node = node[part]
        else:
            return False
    last = loc[-1]
    if isinstance(node, list) and str(last).isdigit() and int(last) < len(node):
        del node[int(last)]
        return True
    if isinstance(node, dict) and last in node:
        del node[last]
        return True
    return False


def _loc_sort_key(loc: tuple[str, ...]) -> tuple:
    return tuple(int(p) if str(p).isdigit() else p for p in loc)


def _validate_and_repair(data: dict[str, Any]) -> None:
    """Backstop: validate against rendercv's own schema and prune anything that
    still fails, so unforeseen LLM output degrades gracefully instead of
    failing the whole render. Mutates `data` in place."""
    try:
        from rendercv.exception import RenderCVUserValidationError  # noqa: PLC0415
        from rendercv.schema.rendercv_model_builder import (  # noqa: PLC0415
            build_rendercv_model_from_commented_map,
        )
    except Exception:  # rendercv not importable — let the CLI report errors
        return
    for _ in range(5):
        probe = copy.deepcopy(data)
        probe["design"] = {"theme": "classic"}
        try:
            build_rendercv_model_from_commented_map(probe)
            return
        except RenderCVUserValidationError as exc:
            # Deepest paths first so per-entry errors are pruned before their
            # parent section, and higher list indices before lower ones.
            locations = sorted(
                {tuple(e.schema_location) for e in exc.validation_errors},
                key=lambda loc: (len(loc), _loc_sort_key(loc)),
                reverse=True,
            )
            pruned: list[tuple[str, ...]] = []
            changed = False
            for loc in locations:
                if any(p[: len(loc)] == loc for p in pruned):
                    continue  # a descendant was already pruned this round
                if _prune_path(data, loc):
                    logger.warning("pruned %s to satisfy rendercv schema", loc)
                    pruned.append(loc)
                    changed = True
            if not changed:
                return
        except Exception:
            logger.exception("rendercv schema validation backstop failed")
            return


def normalize_to_rendercv(yaml_content: str) -> str:
    """Convert any LLM-generated resume YAML to a valid rendercv document."""
    try:
        data = yaml.safe_load(yaml_content)
    except Exception:
        return yaml_content
    if not isinstance(data, dict):
        return yaml_content

    cv = data.get("cv")
    if not isinstance(cv, dict):
        return yaml_content

    # 1. Strip any design block — design is provided via --design CLI flag
    cv.pop("design", None)
    data.pop("design", None)

    # 2. Flatten contact block into cv.*
    contact = cv.pop("contact", None)
    if isinstance(contact, dict):
        for field in ("email", "phone", "website"):
            if field in contact and field not in cv:
                cv[field] = contact[field]
        if "address" in contact and "location" not in cv:
            cv["location"] = contact["address"]
        if "location" in contact and "location" not in cv:
            cv["location"] = contact["location"]
        socials: list[dict] = cv.setdefault("social_networks", [])
        existing_nets = {s.get("network") for s in socials if isinstance(s, dict)}
        if "linkedin" in contact:
            username = re.sub(
                r"^(https?://)?(www\.)?linkedin\.com/(in/)?", "", str(contact["linkedin"])
            ).strip("/")
            if "LinkedIn" not in existing_nets:
                socials.append({"network": "LinkedIn", "username": username})
        if "github" in contact:
            username = re.sub(
                r"^(https?://)?(www\.)?github\.com/", "", str(contact["github"])
            ).strip("/")
            if "GitHub" not in existing_nets:
                socials.append({"network": "GitHub", "username": username})
        if not socials:
            cv.pop("social_networks", None)

    # Normalise phone to E.164 (rendercv validates real numbers, not just format)
    if "phone" in cv:
        fixed_phone = _normalize_phone(str(cv["phone"]))
        if fixed_phone:
            cv["phone"] = fixed_phone
        else:
            cv.pop("phone")

    # Normalise website to a full URL (rendercv requires a scheme)
    if "website" in cv:
        cv["website"] = _normalize_url(str(cv["website"]))

    # Canonicalise networks and strip URL decoration from usernames
    _normalize_social_networks(cv)

    # 3. Move known section keys under cv.sections
    sections: dict[str, Any] = cv.setdefault("sections", {})
    for key in _SECTION_KEYS:
        if key in cv:
            val = cv.pop(key)
            if key not in sections and val:
                sections[key] = val

    # LLMs emit label/title for a tagline — rendercv calls it headline
    for alias in ("label", "title"):
        if alias in cv and "headline" not in cv and isinstance(cv[alias], str):
            cv["headline"] = cv.pop(alias)
    # Drop anything rendercv's Cv model doesn't accept ("field is unknown")
    for key in list(cv):
        if key not in _CV_ALLOWED_KEYS:
            logger.warning("dropping unknown cv key rendercv rejects: %r", key)
            cv.pop(key)

    # Every section must be a list: drop nulls, wrap scalars
    for key in list(sections):
        val = sections[key]
        if val is None:
            del sections[key]
        elif isinstance(val, str):
            sections[key] = [val]
        elif not isinstance(val, list):
            del sections[key]

    # 4. Normalize section entries
    if "experience" in sections:
        sections["experience"] = _normalize_experience(sections["experience"])
    if "education" in sections:
        sections["education"] = _normalize_education(sections["education"])
    if "projects" in sections:
        sections["projects"] = _normalize_projects(sections["projects"])
    if "skills" in sections:
        sections["skills"] = _normalize_skills(sections["skills"])
    if "certifications" in sections:
        sections["certifications"] = _normalize_certifications(sections["certifications"])

    # Generic entry cleanup for every section
    for entries in sections.values():
        for entry in entries:
            if isinstance(entry, dict):
                _clean_highlights(entry)
                _fix_date_order(entry)

    if not sections:
        cv.pop("sections", None)

    # 5. Backstop: prune anything rendercv's schema still rejects
    _validate_and_repair(data)

    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
