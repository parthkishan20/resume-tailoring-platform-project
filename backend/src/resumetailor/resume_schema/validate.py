"""Validate a resume document without rendering it.

``normalize_to_rendercv`` repairs; this only reports. Any write path that wants
to refuse bad YAML rather than store it and discover the problem at render time
calls :func:`validate` — that is task 2.5's ``PUT /api/master-resume`` and
``PATCH /api/resumes/{id}`` (PLAN.md D-04). Nothing calls it yet, so no
endpoint's behaviour changes in this task.

The check runs against the same theme the renderer uses, so "valid here" means
"renders there".
"""

from __future__ import annotations

import copy
from typing import Any

import yaml
from rendercv.exception import RenderCVUserValidationError
from rendercv.schema.rendercv_model_builder import (
    build_rendercv_model_from_commented_map,
)

from resumetailor.rendering.config import RenderProfile, get_render_profile
from resumetailor.rendering.errors import RenderIssue, issues_from_validation_error
from resumetailor.resume_schema.models import Document

__all__ = ["validate"]


def validate(
    yaml_content: str, profile: RenderProfile | None = None
) -> tuple[Document, list[RenderIssue]]:
    """Check ``yaml_content`` against RenderCV's schema.

    Returns:
        The document, and the issues RenderCV found. An empty issue list means
        the document renders; ``document.is_valid`` says the same thing.
    """
    render_profile = profile if profile is not None else get_render_profile()

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return Document(yaml_content, {}), [
            RenderIssue(message=f"This is not valid YAML. {exc}")
        ]

    if not isinstance(data, dict):
        return Document(yaml_content, {}), [
            RenderIssue(
                message="A resume document must be a YAML mapping with a `cv` key."
            )
        ]

    probe: dict[str, Any] = copy.deepcopy(data)
    probe["design"] = {"theme": render_profile.theme()}
    try:
        model = build_rendercv_model_from_commented_map(probe)
    except RenderCVUserValidationError as exc:
        return Document(yaml_content, data), issues_from_validation_error(exc)

    return Document(yaml_content, data, model), []
