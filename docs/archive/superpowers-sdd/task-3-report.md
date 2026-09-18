# Task 3 Report: Remove hardcoded design injection from normalize_to_rendercv()

## Steps taken

1. Read task-3-brief.md and yaml_utils.py to understand the current design-hoisting logic (lines 225–229).
2. Created `backend/tests/test_yaml_utils.py` with 3 tests covering:
   - No design injected when absent from input YAML
   - design nested inside cv: is stripped (not hoisted)
   - design at top level is stripped
3. Ran failing tests to confirm TDD baseline (all 3 FAILED as expected).
4. Replaced the hoist block in `normalize_to_rendercv()` with two `.pop()` calls that silently remove design from both `cv` and `data`.
5. Ran yaml_utils tests: all 3 PASSED.
6. Ran full test suite: 66 passed, 0 failed, 2 deprecation warnings (pre-existing, unrelated to this task).
7. Committed both files.

## Test commands run with actual output

### Step 2 — failing tests (before fix)
```
cd backend && uv run pytest tests/test_yaml_utils.py -v
============================= test session starts ==============================
collected 3 items
tests/test_yaml_utils.py::test_no_design_injected_when_absent FAILED     [ 33%]
tests/test_yaml_utils.py::test_design_stripped_from_cv_block FAILED      [ 66%]
tests/test_yaml_utils.py::test_top_level_design_stripped FAILED          [100%]
3 failed in 0.04s
```

### Step 4 — passing tests (after fix)
```
cd backend && uv run pytest tests/test_yaml_utils.py -v
============================= test session starts ==============================
collected 3 items
tests/test_yaml_utils.py::test_no_design_injected_when_absent PASSED     [ 33%]
tests/test_yaml_utils.py::test_design_stripped_from_cv_block PASSED      [ 66%]
tests/test_yaml_utils.py::test_top_level_design_stripped PASSED          [100%]
3 passed in 0.02s
```

### Step 5 — full suite regression check
```
cd backend && uv run pytest tests/ -q
66 passed, 2 warnings in 0.55s
```
(Warnings are pre-existing FastAPI on_event deprecations, not introduced by this task.)

## Commit hash(es)

- `1261920` — fix: strip design block from normalized YAML, design provided via --design flag

## Self-review findings

- The fix is minimal: 5 lines replaced with 2 lines. No logic added beyond what the brief specifies.
- The module docstring still mentions `design: theme: classic` in the schema summary — left intentionally as documentation of what rendercv expects (provided externally), not what the normalizer outputs.
- No new environment variables or Settings fields introduced.
- No pre-existing tests broken.
