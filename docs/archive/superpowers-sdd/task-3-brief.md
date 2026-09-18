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
