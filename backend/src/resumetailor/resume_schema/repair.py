"""The schema backstop: validate against RenderCV, prune what still fails.

The deterministic normalizers fix the mistakes we have seen. This is what
catches the ones we have not: the document is validated against RenderCV's own
model, and whatever RenderCV objects to is removed, up to five rounds. A resume
with one unparseable email degrades to a resume without an email rather than to
a failed render.

Two things about it changed in task 1.3.

**It fails loudly now** (PLAN.md D-17). The RenderCV imports below used to sit
inside ``try: ... except Exception: return`` in the middle of the function, so
a RenderCV reorganization would have silently converted the whole backstop into
a no-op — and the test guarding it would have skipped rather than failed. They
are module-level imports now, resolved when ``resume_schema`` is first
imported, which is while the routers are being imported, which is at startup.
A RenderCV that has moved these symbols now fails the boot.

**It validates against the right theme** (D-18). The probe used to hardcode
``{"theme": "classic"}`` while the renderer ran ``engineeringresumes``. It
reads the theme out of the configured design file now.

The pruning order is deliberate and unchanged: deepest locations first, highest
list index first within equal depth, and a location is skipped when something
beneath it has already been removed this round. Pruning a parent before its
child would invalidate the child's index; pruning a low index before a high one
would shift the high one.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from rendercv.exception import RenderCVUserValidationError
from rendercv.schema.rendercv_model_builder import (
    build_rendercv_model_from_commented_map,
)

from resumetailor.rendering.config import RenderProfile, get_render_profile

logger = logging.getLogger(__name__)

__all__ = ["MAX_REPAIR_ROUNDS", "prune_path", "validate_and_repair"]

#: How many prune-then-revalidate rounds to run before giving up and letting
#: the CLI report whatever is left.
MAX_REPAIR_ROUNDS = 5

_MISSING = object()


def prune_path(data: dict[str, Any], loc: tuple[str, ...]) -> Any:
    """Remove the value at a RenderCV error location.

    ``loc`` looks like ``("cv", "sections", "experience", "0", "highlights",
    "1")`` — dict keys and list indices are both plain strings.

    Returns:
        The removed value, or the module-private ``_MISSING`` sentinel when the
        location does not resolve. Use :func:`was_pruned` to test the result;
        ``None`` is a value a document can legitimately hold.
    """
    node: Any = data
    for part in loc[:-1]:
        if isinstance(node, list):
            if not str(part).isdigit() or int(part) >= len(node):
                return _MISSING
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                return _MISSING
            node = node[part]
        else:
            return _MISSING
    last = loc[-1]
    if isinstance(node, list) and str(last).isdigit() and int(last) < len(node):
        return node.pop(int(last))
    if isinstance(node, dict) and last in node:
        return node.pop(last)
    return _MISSING


def was_pruned(result: Any) -> bool:
    """Whether :func:`prune_path` removed something."""
    return result is not _MISSING


def _loc_sort_key(loc: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(int(p) if str(p).isdigit() else p for p in loc)


def _error_locations(exc: RenderCVUserValidationError) -> list[tuple[str, ...]]:
    """Locations to prune, deepest first, highest index first within a depth.

    Errors RenderCV could not attribute to a field carry a ``None`` location —
    a YAML syntax error is the usual cause — and there is nothing to prune for
    those, so they are skipped.
    """
    locations = {
        tuple(error.schema_location)
        for error in exc.validation_errors
        if error.schema_location is not None
    }
    return sorted(
        locations,
        key=lambda loc: (len(loc), _loc_sort_key(loc)),
        reverse=True,
    )


def validate_and_repair(
    data: dict[str, Any], profile: RenderProfile | None = None
) -> list[tuple[tuple[str, ...], Any]]:
    """Validate ``data`` against RenderCV and prune what fails. Mutates ``data``.

    Returns:
        One ``(location, removed_value)`` pair per pruned field, in the order
        they were pruned. Empty when the document validated as it stood.
    """
    render_profile = profile if profile is not None else get_render_profile()
    theme = render_profile.theme()
    pruned: list[tuple[tuple[str, ...], Any]] = []

    for _ in range(MAX_REPAIR_ROUNDS):
        probe = copy.deepcopy(data)
        probe["design"] = {"theme": theme}
        try:
            build_rendercv_model_from_commented_map(probe)
        except RenderCVUserValidationError as exc:
            locations = _error_locations(exc)
            this_round: list[tuple[str, ...]] = []
            changed = False
            for loc in locations:
                if any(p[: len(loc)] == loc for p in this_round):
                    continue  # a descendant was already pruned this round
                removed = prune_path(data, loc)
                if was_pruned(removed):
                    logger.warning("pruned %s to satisfy rendercv schema", loc)
                    this_round.append(loc)
                    pruned.append((loc, removed))
                    changed = True
            if not changed:
                return pruned
        except (ValueError, RuntimeError):
            # RenderCV's own error surface: RenderCVUserError and pydantic's
            # ValidationError are ValueErrors, RenderCVInternalError is a
            # RuntimeError. The backstop is best-effort by design — the CLI
            # runs next and reports whatever it still objects to — so a
            # surprise here must not take down the request. What must *not* be
            # swallowed is a failure to import RenderCV at all, and that now
            # happens at module import above, not here. See D-17.
            logger.exception("rendercv schema validation backstop failed")
            return pruned
        else:
            return pruned

    return pruned
