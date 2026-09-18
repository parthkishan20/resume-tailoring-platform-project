### Task 2: Pass --design and --locale flags in RenderCVAdapter

**Files:**
- Modify: `backend/app/adapters.py` (add module-level `_CONFIG_DIR` constant; add two CLI flags)
- Modify: `backend/tests/test_llm.py` (add one new test)

**Interfaces:**
- Consumes: `backend/rendercv_config/design.yaml`, `backend/rendercv_config/locale.yaml` from Task 1 (at `_CONFIG_DIR / "design.yaml"` etc.)
- Produces: `_CONFIG_DIR` module-level constant exported from `app.adapters` (consumed by the test)

- [ ] **Step 1: Write the failing test**

Add this test at the bottom of `backend/tests/test_llm.py`, after the existing `test_rendercv_adapter_maps_nonzero_exit_to_render_error`:

```python
@pytest.mark.anyio
async def test_rendercv_adapter_passes_design_and_locale_flags():
    from app.adapters import RenderCVAdapter, _CONFIG_DIR
    adapter = RenderCVAdapter()
    proc_mock = MagicMock()
    proc_mock.returncode = 1  # fail early — we only care about the call args
    proc_mock.communicate = AsyncMock(return_value=(b"", b"err"))
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = proc_mock
        with pytest.raises(RenderError):
            await adapter.render("cv:\n  name: Test\n")
    call_args = mock_exec.call_args[0]  # positional args tuple
    cmd_str = " ".join(str(a) for a in call_args)
    assert "--design" in cmd_str
    assert "--locale" in cmd_str
    assert str(_CONFIG_DIR / "design.yaml") in cmd_str
    assert str(_CONFIG_DIR / "locale.yaml") in cmd_str
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/test_llm.py::test_rendercv_adapter_passes_design_and_locale_flags -v
```

Expected: `FAILED` — `ImportError: cannot import name '_CONFIG_DIR'` or `AssertionError`.

- [ ] **Step 3: Implement the changes in adapters.py**

In `backend/app/adapters.py`, add a module-level constant after the imports and update `RenderCVAdapter.render()`.

The top of the file (imports + constant):

```python
from __future__ import annotations
import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator

from .ports import LLMAuthError, LLMUnavailableError, PDFExtractError, RenderError

_CONFIG_DIR = Path(__file__).parent.parent / "rendercv_config"
```

The updated `RenderCVAdapter.render()` method (replace the existing method entirely):

```python
class RenderCVAdapter:
    async def render(self, yaml_content: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            yaml_path = tmpdir_path / "resume.yaml"
            pdf_path = tmpdir_path / "resume.pdf"
            yaml_path.write_text(yaml_content, encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                "rendercv", "render", str(yaml_path),
                "--design", str(_CONFIG_DIR / "design.yaml"),
                "--locale", str(_CONFIG_DIR / "locale.yaml"),
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && uv run pytest tests/test_llm.py::test_rendercv_adapter_passes_design_and_locale_flags -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd backend && uv run pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters.py backend/tests/test_llm.py
git commit -m "feat: pass --design and --locale flags to rendercv render"
```

---
