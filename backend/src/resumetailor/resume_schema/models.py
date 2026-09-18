"""The resume contract, derived from RenderCV rather than copied from it.

Before this module the contract existed in five hand-written places — the
normalizer's key sets, its docstring, the import prompt in the master-resume
route, the generation prompt, and the audit prompt — and they had already
drifted apart from each other and from RenderCV (PLAN.md D-22). The documented
case: the import prompt told the model to emit ``design: theme: classic``,
which the normalizer then stripped.

Everything below is *derived*. ``CV_KEYS`` is ``set(Cv.model_fields)``;
``SOCIAL_NETWORKS`` comes from RenderCV's own ``SocialNetworkName`` literal;
the entry field lists come from the entry models. Add a field to RenderCV and
it appears here on the next upgrade instead of silently becoming "unknown".

**This module imports RenderCV at import time, on purpose** (D-17). The
previous backstop imported RenderCV internals inside ``except Exception:
return``, so a RenderCV reorganization would have turned schema validation into
a permanent, silent no-op that no test could see — ``pytest.importorskip``
would merely have skipped. A failure to import now fails the process at
startup, where it is a legible boot error. ``resumetailor.main`` imports the
routers, the routers import ``resume_schema``, so the import happens before the
application serves anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from rendercv.schema.models.cv.cv import Cv
from rendercv.schema.models.cv.entries.education import EducationEntry
from rendercv.schema.models.cv.entries.experience import ExperienceEntry
from rendercv.schema.models.cv.entries.normal import NormalEntry
from rendercv.schema.models.cv.entries.one_line import OneLineEntry
from rendercv.schema.models.cv.entries.publication import PublicationEntry
from rendercv.schema.models.cv.social_network import (
    SocialNetwork,
    available_social_networks,
)

if TYPE_CHECKING:
    from rendercv.schema.models.rendercv_model import RenderCVModel

__all__ = [
    "CV_KEYS",
    "ENTRY_FIELDS",
    "NETWORK_ALIASES",
    "SECTION_KEYS",
    "SECTION_TO_ENTRY",
    "SOCIAL_NETWORKS",
    "Cv",
    "Document",
    "SocialNetwork",
    "canonical_network",
    "required_fields",
]

#: Every key RenderCV's ``Cv`` model accepts. Anything else fails validation
#: with "This field is unknown for this object", so the normalizer drops it.
CV_KEYS: frozenset[str] = frozenset(Cv.model_fields)

#: Normalised network name (lowercased, spaces removed) to the exact spelling
#: RenderCV requires.
SOCIAL_NETWORKS: dict[str, str] = {
    name.lower().replace(" ", ""): name for name in available_social_networks
}

#: Names people and models use that RenderCV does not. These are ours, not
#: RenderCV's, and are the only hand-maintained mapping left in this module.
NETWORK_ALIASES: dict[str, str] = {
    "twitter": "X",
    "googlescholar": "Google Scholar",
}

#: Section keys hoisted from ``cv.*`` into ``cv.sections.*``. RenderCV lets a
#: section be titled anything, so this list is about what LLMs actually emit at
#: the wrong level, not about what RenderCV permits.
SECTION_KEYS: tuple[str, ...] = (
    "experience",
    "education",
    "projects",
    "skills",
    "certifications",
    "summary",
    "publications",
    "awards",
    "languages",
    "interests",
    "extra_curricular_activities",
    "work_experience",
)

#: Which RenderCV entry model each known section should end up as. RenderCV
#: infers the entry type from the fields present rather than from the section
#: name, so this is what the per-section normalizers are steering towards.
#: ``work_experience`` maps to the same model as ``experience`` — that is
#: D-24: the key was hoisted into ``cv.sections`` but nothing normalized it.
SECTION_TO_ENTRY: dict[str, type[BaseModel]] = {
    "experience": ExperienceEntry,
    "work_experience": ExperienceEntry,
    "education": EducationEntry,
    "projects": NormalEntry,
    "certifications": NormalEntry,
    "skills": OneLineEntry,
    "publications": PublicationEntry,
}

#: Field names of each entry model, required fields first. Used to generate the
#: prompt text so the model is told what RenderCV actually wants.
ENTRY_FIELDS: dict[str, tuple[str, ...]] = {
    model.__name__: tuple(model.model_fields)
    for model in (
        ExperienceEntry,
        EducationEntry,
        NormalEntry,
        OneLineEntry,
        PublicationEntry,
    )
}


def required_fields(model: type[BaseModel]) -> tuple[str, ...]:
    """The fields of ``model`` that have no default."""
    return tuple(
        name for name, info in model.model_fields.items() if info.is_required()
    )


def canonical_network(raw: str) -> str | None:
    """RenderCV's spelling of a social network, or ``None`` if it has none.

    Matching ignores case and spacing, so ``"google scholar"``,
    ``"GoogleScholar"`` and ``"Google Scholar"`` all resolve.
    """
    key = raw.lower().replace(" ", "")
    return NETWORK_ALIASES.get(key) or SOCIAL_NETWORKS.get(key)


@dataclass(frozen=True)
class Document:
    """A resume document that has been put through RenderCV's own schema.

    ``design``, ``locale`` and ``settings`` are RenderCV's other top-level keys
    and this application owns all three — they come from the render profile's
    overlay files, never from user content — so a valid document here carries
    only ``cv``.

    Attributes:
        yaml: The document as YAML, exactly as it was validated.
        data: The same document parsed, for a caller that wants to read a field.
        model: RenderCV's validated model, or ``None`` when validation failed.
    """

    yaml: str
    data: dict[str, Any]
    model: RenderCVModel | None = None

    @property
    def is_valid(self) -> bool:
        return self.model is not None

    @property
    def cv(self) -> dict[str, Any]:
        cv = self.data.get("cv")
        return cv if isinstance(cv, dict) else {}
