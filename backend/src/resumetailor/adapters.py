# MOVED BY TASK 1.3. This module holds three unrelated adapters:
#   LiteLLMAdapter  -> llm/litellm_adapter.py
#   RenderCVAdapter -> rendering/runner.py (+ rendering/config.py, errors.py)
#   PyMuPDFAdapter  -> pdf/extract.py
# See PLAN.md section 3.3. Nothing here was changed by the src-layout move
# except the import paths and `_CONFIG_DIR`, which now comes from core.config
# because `__file__.parent.parent` no longer resolves to `backend/`.
from __future__ import annotations
import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator

import yaml

from resumetailor.core.config import RENDERCV_CONFIG_DIR
from resumetailor.ports import LLMAuthError, LLMUnavailableError, PDFExtractError, RenderError

_CONFIG_DIR = RENDERCV_CONFIG_DIR


def _llm_exceptions() -> tuple[type[Exception], tuple[type[Exception], ...]]:
    """Return (auth_error, unavailable_errors). Lazy: importing litellm is slow."""
    import litellm.exceptions as llm_exc  # noqa: PLC0415
    return llm_exc.AuthenticationError, (
        llm_exc.RateLimitError,
        llm_exc.ServiceUnavailableError,
        llm_exc.APIConnectionError,
    )


class LiteLLMAdapter:
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        os.environ["OPENAI_API_KEY"] = api_key

    async def complete(
        self, messages: list[dict], response_format: dict | None = None
    ) -> str:
        import litellm  # noqa: PLC0415 — lazy import, litellm is slow to load
        auth_error, unavailable = _llm_exceptions()
        kwargs: dict = {"model": self._model, "messages": messages}
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content
        except auth_error as exc:
            raise LLMAuthError("Invalid LLM API key (check OPENAI_API_KEY)") from exc
        except unavailable as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        import litellm  # noqa: PLC0415 — lazy import, litellm is slow to load
        auth_error, unavailable = _llm_exceptions()
        model = self._model

        async def _gen() -> AsyncIterator[str]:
            try:
                response = await litellm.acompletion(
                    model=model, messages=messages, stream=True
                )
            except auth_error as exc:
                raise LLMAuthError("Invalid LLM API key (check OPENAI_API_KEY)") from exc
            except unavailable as exc:
                raise LLMUnavailableError(str(exc)) from exc
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        return _gen()


class RenderCVAdapter:
    async def render(self, yaml_content: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            yaml_path = tmpdir_path / "resume.yaml"
            pdf_path = tmpdir_path / "resume.pdf"

            # Embed locale as a top-level key — rendercv --locale flag expects a
            # dict, not a file path, so we inject the content directly into the YAML.
            data = yaml.safe_load(yaml_content) or {}
            if "locale" not in data:
                locale_raw = (_CONFIG_DIR / "locale.yaml").read_text(encoding="utf-8")
                locale_data = yaml.safe_load(locale_raw) or {}
                data.update(locale_data)
                yaml_content = yaml.dump(
                    data, default_flow_style=False, allow_unicode=True, sort_keys=False
                )

            yaml_path.write_text(yaml_content, encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                "rendercv", "render", str(yaml_path),
                "--design", str(_CONFIG_DIR / "design.yaml"),
                "--pdf-path", str(pdf_path),
                "--dont-generate-markdown",
                "--dont-generate-html",
                "--dont-generate-png",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                output = (
                    stdout.decode("utf-8", errors="replace")
                    + stderr.decode("utf-8", errors="replace")
                ).strip()
                raise RenderError(
                    f"rendercv failed (exit {proc.returncode}): {output}"
                )
            return pdf_path.read_bytes()


class PyMuPDFAdapter:
    _MAX_BYTES = 10 * 1024 * 1024
    _MAX_PAGES = 50

    async def extract(self, pdf_bytes: bytes) -> str:
        if len(pdf_bytes) > self._MAX_BYTES:
            raise PDFExtractError(
                f"PDF exceeds 10 MB limit ({len(pdf_bytes) / 1_048_576:.1f} MB)"
            )
        try:
            import pymupdf  # noqa: PLC0415 — lazy import, pymupdf is slow to load
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PDFExtractError(f"Cannot open PDF: {exc}") from exc
        if doc.page_count > self._MAX_PAGES:
            doc.close()
            raise PDFExtractError(
                f"PDF has {doc.page_count} pages (max {self._MAX_PAGES})"
            )
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages)
