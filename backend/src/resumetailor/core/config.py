"""Settings and the on-disk layout the process depends on.

Everything the application reads from the environment is declared once, here,
and reached through :func:`get_settings`. Two rules hold:

* A secret is a ``SecretStr``. It does not appear in a log line, a traceback,
  or a ``repr`` by accident.
* Configuration that is required to do real work is checked at **startup**, by
  :func:`validate_startup_settings`, not at the first request that needs it.
  Before this module existed, a missing ``OPENAI_API_KEY`` defaulted to the
  literal ``"mock-key"``; the process booted, reported itself healthy, and then
  failed on the user's first generation with a provider auth error. See
  PLAN.md D-15.

The path constants below are resolved from this file's location rather than
from the working directory, so they hold for both `uv run` from `backend/` and
the container, where the tree is rooted at `/app/backend`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from resumetailor.core.errors import ConfigurationError

# ── Filesystem layout ────────────────────────────────────────────────────────
#
# <BACKEND_ROOT>/
#   migrations/             numbered SQL migrations (resumetailor.db.migrate)
#   rendercv_config/         design.yaml, locale.yaml, settings.yaml
#   static/                  the Next.js export, mounted at / by main.py
#   src/resumetailor/        this package
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PACKAGE_ROOT.parents[1]

RENDERCV_CONFIG_DIR = BACKEND_ROOT / "rendercv_config"
STATIC_DIR = BACKEND_ROOT / "static"


class Settings(BaseSettings):
    """Process configuration, read from the environment and from ``.env``."""

    # Empty rather than "mock-key": an unset key must be detectable. Both keys
    # are declared so a deployment can point `LLM_MODEL` at either provider
    # without losing the other's key; `llm_api_key` below picks the one that
    # matches `LLM_MODEL`.
    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENROUTER_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "openrouter/free"
    LLM_MOCK: bool = False

    # What bounds one provider call (PLAN.md D-46). The adapter reads these
    # through `llm.config.LLMProfile`, which documents each one; the bounds
    # are declared here so a bad value fails the boot rather than the call.
    LLM_TIMEOUT_S: float = Field(default=60.0, gt=0)
    LLM_MAX_ATTEMPTS: int = Field(default=3, ge=1)
    LLM_RETRY_BACKOFF_S: float = Field(default=0.5, gt=0)
    LLM_MAX_TOKENS: int = Field(default=8192, gt=0)
    LLM_STREAM_STALL_TIMEOUT_S: float = Field(default=30.0, gt=0)

    # What OpenRouter's free tier (the `openrouter/free` default) allows, for
    # the usage counter shown next to the assistant. Not enforced here — the
    # provider is the one that actually rejects a call over the limit — these
    # only label what `GET /api/llm/usage`'s counts are being compared
    # against, so a deployment on a different plan or provider can correct
    # them without a code change.
    LLM_RATE_LIMIT_PER_MINUTE: int = Field(default=20, gt=0)
    LLM_RATE_LIMIT_PER_DAY: int = Field(default=50, gt=0)

    DB_PATH: str = "/app/db/resumedb.db"
    PDFS_DIR: str = "/app/pdfs"

    LOG_LEVEL: str = "INFO"
    # "json" for anything that ships logs somewhere; "text" when a human is
    # reading the terminal.
    LOG_FORMAT: Literal["json", "text"] = "json"

    # Whether `/docs`, `/redoc` and `/openapi.json` are served (PLAN.md D-58).
    # True today because there is no auth model yet (D4/B-03 are open) and a
    # single-user deployment gains nothing from hiding its own contract from
    # itself; the lever exists so that decision does not require a code change
    # once D4 lands. See docs/adr/0006-docs-gated-by-setting.md.
    API_DOCS_ENABLED: bool = True

    # How long the lifespan waits, after receiving shutdown, for in-flight SSE
    # streams (generation, chat, evaluation) to finish on their own before it
    # returns and uvicorn tears the connections down. Generous relative to
    # `LLM_TIMEOUT_S` because a stream is two provider calls plus a render.
    GRACEFUL_SHUTDOWN_TIMEOUT_S: float = Field(default=60.0, gt=0)

    # How often the orphan reaper re-scans `generated_resumes` against
    # `PDFS_DIR` after its one guaranteed run at startup (PLAN.md D-20). Orphans
    # accumulate only from a crash mid-write, not from normal operation, so
    # hourly is frequent enough to bound disk growth without a rate that
    # crowds `PDFS_DIR`'s directory listing in the log.
    REAPER_INTERVAL_S: float = Field(default=3600.0, gt=0)

    # D-81: the reaper's row scan and its directory-delete pass are two
    # separate reads, seconds apart, of state a concurrent `store_tailored_
    # resume` call can move between them -- a file that did not exist at row-
    # scan time can exist by delete-pass time, without ever entering the
    # `referenced` set built from the earlier snapshot. A grace period keeps
    # any `*.pdf` file younger than this many seconds out of the delete pass
    # entirely, regardless of what the snapshot says, which is longer than a
    # real render (`rendering/config.py`'s `RENDER_TIMEOUT_S`, default 30s)
    # ever takes.
    REAPER_DELETE_GRACE_S: float = Field(default=300.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Same reason as `SecurityPolicy` and `RenderProfile`: this class has no
        # prefix of its own, so every `SECURITY_*` / `RENDER_*` key in the
        # shared `.env` would otherwise land here as an extra and fail the boot.
        extra="ignore",
    )

    @property
    def llm_api_key(self) -> str:
        """The provider key for `LLM_MODEL`, unwrapped.

        LiteLLM's routing convention is the provider prefix on the model
        string itself (``openrouter/...`` vs a bare OpenAI model name like
        ``gpt-4o-mini``), so that prefix is what selects which secret to read.
        The only place either secret is read.
        """
        key = (
            self.OPENROUTER_API_KEY
            if self.LLM_MODEL.startswith("openrouter/")
            else self.OPENAI_API_KEY
        )
        return key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def validate_startup_settings(settings: Settings) -> None:
    """Fail the boot rather than the first request.

    Raises:
        ConfigurationError: if the process is configured to call a real
            provider but has no key to call it with.
    """
    if not settings.LLM_MOCK and not settings.llm_api_key:
        var = (
            "OPENROUTER_API_KEY"
            if settings.LLM_MODEL.startswith("openrouter/")
            else "OPENAI_API_KEY"
        )
        msg = (
            f"{var} is not set for LLM_MODEL={settings.LLM_MODEL!r}. Set it "
            "in the environment or in backend/.env, or set LLM_MOCK=true to "
            "run against the deterministic stub."
        )
        raise ConfigurationError(msg)
