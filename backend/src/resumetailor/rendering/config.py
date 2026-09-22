"""Where the RenderCV overlay files live, and what bounds a render.

RenderCV takes three overlay files on the command line: a design, a locale
catalog, and a settings file. Their paths used to be a single module constant
in ``adapters.py`` and only one of the three was ever passed. They are a
:class:`RenderProfile` now, read from the environment, so an operator can point
a deployment at a different design without editing files inside the package.

This is deliberately *not* part of ``core.config.Settings``. ``core/`` belongs
to another task in this wave and the render profile is read by exactly one
package; ``Settings`` stays the place for process-wide configuration. The env
names are prefixed ``RENDER_`` so the two cannot collide.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from resumetailor.core.config import RENDERCV_CONFIG_DIR

#: The theme assumed when ``design.yaml`` is unreadable or names no theme. It
#: is RenderCV's own default, so a render still succeeds.
DEFAULT_THEME = "classic"


class RenderProfile(BaseSettings):
    """The inputs and limits of one RenderCV invocation.

    Every field is overridable from the environment with a ``RENDER_`` prefix,
    e.g. ``RENDER_DESIGN_PATH=/etc/resumetailor/design.yaml`` or
    ``RENDER_TIMEOUT_S=30``.
    """

    design_path: Path = Field(default=RENDERCV_CONFIG_DIR / "design.yaml")
    locale_path: Path = Field(default=RENDERCV_CONFIG_DIR / "locale.yaml")
    settings_path: Path = Field(default=RENDERCV_CONFIG_DIR / "settings.yaml")

    #: Wall-clock ceiling on one ``rendercv render``. Typst compiles a one-page
    #: CV in well under a second; anything past this is a hang, not slowness.
    timeout_s: float = Field(default=60.0, gt=0)
    #: How many renders may run at once. Each one is a Typst process, so this
    #: is a bound on CPU, not on connections.
    max_concurrent: int = Field(default=2, ge=1)

    model_config = SettingsConfigDict(
        env_prefix="RENDER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # `env_prefix` alone does not keep the two namespaces apart: pydantic-
        # settings loads every key in `.env` and then forbids the ones that are
        # not fields here, so a local `.env` carrying `OPENROUTER_API_KEY` /
        # `LLM_MODEL` / `LLM_MOCK` made `RenderProfile()` raise `extra_forbidden`
        # and took every real render down with it. Docker never saw it because
        # `.dockerignore` keeps `.env` out of the image, so this only ever fired
        # on a local dev server with `LLM_MOCK=false`.
        extra="ignore",
    )

    def theme(self) -> str:
        """The theme name ``design_path`` actually selects.

        The schema backstop validates against this rather than against a
        hardcoded ``classic`` (PLAN.md D-18): a document that passes under one
        theme can fail under another, and the one that matters is the one the
        subprocess is about to use.
        """
        try:
            raw = self.design_path.read_text(encoding="utf-8")
        except OSError:
            return DEFAULT_THEME
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return DEFAULT_THEME
        design = data.get("design")
        if not isinstance(design, dict):
            return DEFAULT_THEME
        theme = design.get("theme")
        return theme if isinstance(theme, str) and theme else DEFAULT_THEME


@lru_cache(maxsize=1)
def get_render_profile() -> RenderProfile:
    """The process-wide render profile. Cached; the environment is read once."""
    return RenderProfile()
