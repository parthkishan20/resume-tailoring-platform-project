"""Turn any resume YAML into a document RenderCV accepts, and say what it cost.

The normalizer is forgiving on purpose: a language model will nest ``design``
inside ``cv``, invent a ``contact`` block, write a phone number nobody can
dial, and call a social network "Portfolio". All of that is repaired or
removed rather than failing the render.

Removal is the part that used to be invisible. ``normalize_to_rendercv``
returned a bare ``str``, so a dropped email reached nothing but a log line the
user never sees, and the PDF came back silently missing their contact details
(PLAN.md D-08). It returns a :class:`NormalizeResult` now — the YAML, plus one
:class:`DroppedField` per thing removed. Surfacing those to the user is task
2.5's and the frontend's; making them exist at all is this one's.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from resumetailor.resume_schema.models import CV_KEYS, SECTION_KEYS, canonical_network
from resumetailor.resume_schema.repair import validate_and_repair
from resumetailor.resume_schema.sections import (
    SECTION_NORMALIZERS,
    clean_highlights,
    fix_date_order,
)

logger = logging.getLogger(__name__)

__all__ = ["DroppedField", "NormalizeResult", "normalize_to_rendercv"]

#: Longer values are truncated in a diagnostic. The point is to let the user
#: recognise what went missing, not to echo the document back at them.
_VALUE_PREVIEW_CHARS = 120


@dataclass(frozen=True)
class DroppedField:
    """Something removed from the document on the way to RenderCV.

    Attributes:
        path: Where it was, e.g. ``("cv", "phone")``.
        value: A short preview of what was removed.
        reason: Why, in language a user can act on.
    """

    path: tuple[str, ...]
    value: str
    reason: str

    @property
    def field_path(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class NormalizeResult:
    """The normalized document, and everything that did not survive it."""

    yaml: str
    dropped: list[DroppedField] = field(default_factory=list)


def _preview(value: Any) -> str:
    text = str(value)
    if len(text) > _VALUE_PREVIEW_CHARS:
        return text[: _VALUE_PREVIEW_CHARS - 1] + "…"
    return text


class _Drops:
    """Collects diagnostics while the document is being rewritten."""

    def __init__(self) -> None:
        self.items: list[DroppedField] = []

    def add(self, path: tuple[str, ...], value: Any, reason: str) -> None:
        self.items.append(DroppedField(path, _preview(value), reason))


def _normalize_phone(raw: str) -> str | None:
    """E.164 if the number is real, ``None`` if RenderCV would reject it.

    RenderCV validates phones semantically with ``phonenumbers``, so
    format-only fixes are not enough: a placeholder like ``555-000-0000`` is
    well-formed and still invalid, and leaving it in fails the whole render.
    """
    import phonenumbers  # lazy: only needed when a phone is present

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


def _social_username(raw: str) -> str:
    """Strip URL decoration: ``https://linkedin.com/in/jane/`` → ``jane``."""
    u = str(raw).strip().strip("/")
    if re.match(r"^(https?://|www\.)", u) or "/" in u:
        segments = [s for s in u.split("/") if s]
        u = segments[-1] if segments else ""
    return u


def _normalize_social_networks(cv: dict[str, Any], drops: _Drops) -> None:
    raw_networks = cv.get("social_networks")
    if not isinstance(raw_networks, list):
        if raw_networks is not None:
            cv.pop("social_networks", None)
            drops.add(
                ("cv", "social_networks"),
                raw_networks,
                "social networks must be a list of network/username pairs",
            )
        return
    out = []
    for s in raw_networks:
        if not isinstance(s, dict):
            continue
        network = canonical_network(str(s.get("network", "")))
        if not network:
            logger.warning("dropping social network rendercv rejects: %r", s)
            drops.add(
                ("cv", "social_networks"),
                s.get("network", ""),
                "not a social network RenderCV can link to",
            )
            continue
        username = _social_username(s.get("username", ""))
        if not username:
            drops.add(
                ("cv", "social_networks", network),
                s.get("username", ""),
                "no username could be read from this entry",
            )
            continue
        out.append({"network": network, "username": username})
    if out:
        cv["social_networks"] = out
    else:
        cv.pop("social_networks", None)


def _flatten_contact(cv: dict[str, Any]) -> None:
    """Fold an invented ``cv.contact`` block into the fields RenderCV knows."""
    contact = cv.pop("contact", None)
    if not isinstance(contact, dict):
        return
    for name in ("email", "phone", "website"):
        if name in contact and name not in cv:
            cv[name] = contact[name]
    if "address" in contact and "location" not in cv:
        cv["location"] = contact["address"]
    if "location" in contact and "location" not in cv:
        cv["location"] = contact["location"]
    socials: list[dict[str, Any]] = cv.setdefault("social_networks", [])
    existing = {s.get("network") for s in socials if isinstance(s, dict)}
    for key, network, url_prefix in (
        ("linkedin", "LinkedIn", r"^(https?://)?(www\.)?linkedin\.com/(in/)?"),
        ("github", "GitHub", r"^(https?://)?(www\.)?github\.com/"),
    ):
        if key in contact and network not in existing:
            username = re.sub(url_prefix, "", str(contact[key])).strip("/")
            socials.append({"network": network, "username": username})
    if not socials:
        cv.pop("social_networks", None)


def _hoist_sections(cv: dict[str, Any]) -> dict[str, Any]:
    """Move known section keys from ``cv.*`` down into ``cv.sections.*``."""
    sections: dict[str, Any] = cv.setdefault("sections", {})
    for key in SECTION_KEYS:
        if key in cv:
            val = cv.pop(key)
            if key not in sections and val:
                sections[key] = val
    return sections


def _coerce_sections(sections: dict[str, Any], drops: _Drops) -> None:
    """Every section must be a list: drop nulls, wrap scalars, drop the rest."""
    for key in list(sections):
        val = sections[key]
        if val is None:
            del sections[key]
        elif isinstance(val, str):
            sections[key] = [val]
        elif not isinstance(val, list):
            del sections[key]
            drops.add(
                ("cv", "sections", key),
                val,
                "a section must be a list of entries",
            )


def _drop_unknown_cv_keys(cv: dict[str, Any], drops: _Drops) -> None:
    # Models emit `label`/`title` for a tagline — RenderCV calls it `headline`.
    for alias in ("label", "title"):
        if alias in cv and "headline" not in cv and isinstance(cv[alias], str):
            cv["headline"] = cv.pop(alias)
    for key in list(cv):
        if key not in CV_KEYS:
            logger.warning("dropping unknown cv key rendercv rejects: %r", key)
            value = cv.pop(key)
            drops.add(("cv", key), value, "RenderCV has no such field on a CV")


def _normalize_contact(cv: dict[str, Any], drops: _Drops) -> None:
    """The three contact fields RenderCV validates semantically, not by shape."""
    if "phone" in cv:
        fixed_phone = _normalize_phone(str(cv["phone"]))
        if fixed_phone:
            cv["phone"] = fixed_phone
        else:
            drops.add(("cv", "phone"), cv.pop("phone"), "not a dialable phone number")
    if "website" in cv:
        cv["website"] = _normalize_url(str(cv["website"]))
    _normalize_social_networks(cv, drops)


def _normalize_sections(cv: dict[str, Any], drops: _Drops) -> None:
    """Hoist section keys into ``cv.sections``, then repair each section."""
    sections = _hoist_sections(cv)
    _drop_unknown_cv_keys(cv, drops)
    _coerce_sections(sections, drops)

    for key, normalizer in SECTION_NORMALIZERS.items():
        if key in sections:
            sections[key] = normalizer(sections[key])

    for entries in sections.values():
        for entry in entries:
            if isinstance(entry, dict):
                clean_highlights(entry)
                fix_date_order(entry)

    if not sections:
        cv.pop("sections", None)


def normalize_to_rendercv(yaml_content: str) -> NormalizeResult:
    """Convert any resume YAML into a valid RenderCV document.

    Input that cannot be understood at all — unparseable YAML, a top level that
    is not a mapping, a missing ``cv`` — is returned verbatim with no
    diagnostics. That is unchanged behaviour: the caller persists it and the
    render reports the real error, which is more useful than this function
    inventing one. Validating those paths up front is task 2.5's (D-04).
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return NormalizeResult(yaml_content)
    if not isinstance(data, dict):
        return NormalizeResult(yaml_content)

    cv = data.get("cv")
    if not isinstance(cv, dict):
        return NormalizeResult(yaml_content)

    drops = _Drops()

    # 1. Strip any design block — design comes from the render profile.
    cv.pop("design", None)
    data.pop("design", None)

    # 2. Flatten an invented contact block into cv.*
    _flatten_contact(cv)

    # 3. Contact fields RenderCV validates semantically.
    _normalize_contact(cv, drops)

    # 4. Sections: hoist, coerce to lists, then normalize per section.
    _normalize_sections(cv, drops)

    # 5. Backstop: prune anything RenderCV's schema still rejects.
    for location, value in validate_and_repair(data):
        drops.add(location, value, "RenderCV rejected this value")

    dumped = yaml.dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    return NormalizeResult(dumped, drops.items)
