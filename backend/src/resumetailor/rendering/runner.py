"""The ``rendercv render`` subprocess, with a leash on it.

Three things changed when this moved out of ``adapters.py``:

* **It can no longer hang the server** (PLAN.md D-07). The call is wrapped in
  ``asyncio.wait_for`` and a semaphore bounds how many Typst processes exist at
  once. A timeout *kills the child*; cancelling the future that awaits it would
  leave an orphan holding a CPU and a temp directory.
* **The locale is passed, not injected** (D-16). The previous code merged
  ``locale.yaml``'s contents into the top level of the user's document because
  of a comment claiming ``--locale`` wants a dict. There is no ``--locale``
  flag. ``rendercv render --help`` on 2.8 lists ``--locale-catalog`` / ``-lc``,
  which takes a path, and that is what is passed now.
* **``settings.yaml`` is wired in** (D-15). It was dead configuration: never
  read by anything, and carrying one particular person's name in a repo file.

One flag the data-pipeline audit recommended is deliberately absent:
``--dont-generate-typst``. RenderCV's own help says "Disabling Typst generation
implicitly disables PDF and PNG" — passing it produces no PDF at all. The stray
``.typ`` is written inside the per-render temp directory and dies with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path

from resumetailor.core.errors import RenderError
from resumetailor.rendering.config import RenderProfile, get_render_profile

logger = logging.getLogger(__name__)

#: How long to wait for a killed child to actually die before giving up on
#: reaping it. A Typst process that ignores SIGKILL for this long is a kernel
#: problem, not ours.
_REAP_TIMEOUT_S = 5.0


async def _kill(proc: asyncio.subprocess.Process) -> None:
    """Kill a subprocess and reap it, tolerating one that already exited."""
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(TimeoutError, ProcessLookupError):
        await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)


class RenderCVAdapter:
    """Renders a resume document to PDF by shelling out to RenderCV.

    The semaphore is per-instance, and one instance is built per process by
    ``backend_api.create_real_backend``, so it bounds the whole application.
    """

    def __init__(self, profile: RenderProfile | None = None) -> None:
        self._profile = profile if profile is not None else get_render_profile()
        self._slots = asyncio.Semaphore(self._profile.max_concurrent)

    def _command(self, yaml_path: Path, pdf_path: Path) -> tuple[str, ...]:
        profile = self._profile
        return (
            "rendercv",
            "render",
            str(yaml_path),
            "--design",
            str(profile.design_path),
            "--locale-catalog",
            str(profile.locale_path),
            "--settings",
            str(profile.settings_path),
            "--pdf-path",
            str(pdf_path),
            "--dont-generate-markdown",
            "--dont-generate-html",
            "--dont-generate-png",
        )

    async def render(self, yaml_content: str) -> bytes:
        """Render ``yaml_content`` to PDF bytes.

        Raises:
            RenderError: if RenderCV exits non-zero, or does not finish within
                the profile's timeout.
        """
        async with self._slots:
            return await self._render(yaml_content)

    async def _render(self, yaml_content: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            yaml_path = tmpdir_path / "resume.yaml"
            pdf_path = tmpdir_path / "resume.pdf"
            yaml_path.write_text(yaml_content, encoding="utf-8")

            command = self._command(yaml_path, pdf_path)
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timeout = self._profile.timeout_s
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                await _kill(proc)
                logger.warning("rendercv timed out after %ss; killed", timeout)
                msg = f"rendercv timed out after {timeout:g}s and was terminated"
                raise RenderError(msg) from None

            if proc.returncode != 0:
                output = (
                    stdout.decode("utf-8", errors="replace")
                    + stderr.decode("utf-8", errors="replace")
                ).strip()
                msg = f"rendercv failed (exit {proc.returncode}): {output}"
                raise RenderError(msg)

            return pdf_path.read_bytes()
