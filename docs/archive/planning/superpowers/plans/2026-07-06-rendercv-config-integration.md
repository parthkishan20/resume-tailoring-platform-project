# RenderCV Config Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle design.yaml, locale.yaml, and settings.yaml with the backend image and wire them into every PDF render call so the `engineeringresumes` theme and XCharter typography take effect.

**Architecture:** Move the three RenderCV config files into `backend/rendercv_config/` (bundled automatically by the existing `COPY backend/ ./backend/` Dockerfile line). Update `RenderCVAdapter.render()` to pass `--design` and `--locale` as explicit CLI flags with paths derived from `__file__`. Strip any `design:` block from `normalize_to_rendercv()` output — design is now always provided externally.

**Tech Stack:** Python 3.12, RenderCV CLI, pytest + anyio

## Global Constraints

- No new environment variables or `Settings` fields
- Config path derived from `Path(__file__).parent.parent / "rendercv_config"` — hardcoded, not configurable at runtime
- Do not modify the Dockerfile — `COPY backend/ ./backend/` already handles bundling
- Keep existing `--dont-generate-markdown`, `--dont-generate-html`, `--dont-generate-png` flags unchanged

---

### Task 1: Move config files into backend/rendercv_config/

**Files:**
- Create: `backend/rendercv_config/design.yaml` (moved from project root `design.yaml`)
- Create: `backend/rendercv_config/locale.yaml` (moved from project root `locale.yaml`)
- Create: `backend/rendercv_config/settings.yaml` (moved from project root `settings.yaml`)

**Interfaces:**
- Consumes: nothing
- Produces: `backend/rendercv_config/design.yaml` and `backend/rendercv_config/locale.yaml` — consumed by Task 2's `_CONFIG_DIR` path constant

- [ ] **Step 1: Create directory and move files with git**

```bash
mkdir -p backend/rendercv_config
git mv design.yaml backend/rendercv_config/design.yaml
git mv locale.yaml backend/rendercv_config/locale.yaml
git mv settings.yaml backend/rendercv_config/settings.yaml
```

- [ ] **Step 2: Verify files landed correctly**

```bash
ls backend/rendercv_config/
```

Expected:
```
design.yaml  locale.yaml  settings.yaml
```

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
cd backend && uv run pytest tests/ -q
```

Expected: all tests pass (no import errors or missing-file errors).

- [ ] **Step 4: Commit**

```bash
git add backend/rendercv_config/
git commit -m "feat: move rendercv config files into backend/rendercv_config"
```

---

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

### Task 3: Remove hardcoded design injection from normalize_to_rendercv()

**Files:**
- Modify: `backend/app/yaml_utils.py` (remove `design` injection; strip any LLM-generated design block)
- Create: `backend/tests/test_yaml_utils.py` (new test file)

**Interfaces:**
- Consumes: nothing from prior tasks (standalone normalizer)
- Produces: `normalize_to_rendercv(yaml_str: str) -> str` — output YAML has no `design:` key at top level

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_yaml_utils.py`:

```python
import yaml
from app.yaml_utils import normalize_to_rendercv


def test_no_design_injected_when_absent():
    """normalize must NOT add a design: block — design comes from --design CLI flag."""
    raw = "cv:\n  name: Jane Doe\n  sections:\n    skills:\n    - label: Skills\n      details: Python\n"
    result = yaml.safe_load(normalize_to_rendercv(raw))
    assert "design" not in result


def test_design_stripped_from_cv_block():
    """LLM sometimes nests design: inside cv: — it must be removed, not hoisted."""
    raw = (
        "cv:\n"
        "  name: Jane Doe\n"
        "  design:\n"
        "    theme: classic\n"
        "  sections:\n"
        "    skills:\n"
        "    - label: Skills\n"
        "      details: Python\n"
    )
    result = yaml.safe_load(normalize_to_rendercv(raw))
    assert "design" not in result
    assert "design" not in result.get("cv", {})


def test_top_level_design_stripped():
    """If design: already sits at top level (e.g. from master resume), it must be removed."""
    raw = (
        "cv:\n"
        "  name: Jane Doe\n"
        "  sections:\n"
        "    skills:\n"
        "    - label: Skills\n"
        "      details: Python\n"
        "design:\n"
        "  theme: engineeringresumes\n"
    )
    result = yaml.safe_load(normalize_to_rendercv(raw))
    assert "design" not in result
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_yaml_utils.py -v
```

Expected: `FAILED` — `test_no_design_injected_when_absent` fails because the current code injects `{"theme": "classic"}`, `test_top_level_design_stripped` fails for the same reason.

- [ ] **Step 3: Update normalize_to_rendercv() in yaml_utils.py**

In `backend/app/yaml_utils.py`, find the `normalize_to_rendercv` function and replace the design-handling block (around line 225–229):

**Before:**
```python
    # 1. Hoist design: to top level
    if "design" in cv:
        data["design"] = cv.pop("design")
    if "design" not in data:
        data["design"] = {"theme": "classic"}
```

**After:**
```python
    # 1. Strip any design block — design is provided via --design CLI flag
    cv.pop("design", None)
    data.pop("design", None)
```

- [ ] **Step 4: Run the yaml_utils tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_yaml_utils.py -v
```

Expected: all 3 tests `PASSED`.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd backend && uv run pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/yaml_utils.py backend/tests/test_yaml_utils.py
git commit -m "fix: strip design block from normalized YAML, design provided via --design flag"
```
