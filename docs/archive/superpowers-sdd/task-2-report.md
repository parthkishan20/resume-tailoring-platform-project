# Task 2 Report: Pass --design and --locale flags in RenderCVAdapter

## Steps Taken

### Step 1: Read task brief and existing files
- Read `.superpowers/sdd/task-2-brief.md`
- Read `backend/app/adapters.py` — confirmed no `_CONFIG_DIR` constant, `render()` had no `--design`/`--locale` flags
- Read `backend/tests/test_llm.py` — confirmed existing test structure

### Step 2: Write the failing test
Added `test_rendercv_adapter_passes_design_and_locale_flags` to `backend/tests/test_llm.py` after the existing `test_rendercv_adapter_maps_nonzero_exit_to_render_error` test.

### Step 3: Verify test fails
```
cd backend && uv run pytest tests/test_llm.py::test_rendercv_adapter_passes_design_and_locale_flags -v
```
Output:
```
FAILED tests/test_llm.py::test_rendercv_adapter_passes_design_and_locale_flags[asyncio]
ImportError: cannot import name '_CONFIG_DIR' from 'app.adapters'
1 failed in 0.04s
```
Confirmed expected failure.

### Step 4: Implement changes in adapters.py
Two changes to `backend/app/adapters.py`:
1. Added module-level constant after imports: `_CONFIG_DIR = Path(__file__).parent.parent / "rendercv_config"`
2. Added `--design` and `--locale` flags to the `asyncio.create_subprocess_exec` call in `RenderCVAdapter.render()`

### Step 5: Verify new test passes
```
cd backend && uv run pytest tests/test_llm.py::test_rendercv_adapter_passes_design_and_locale_flags -v
```
Output:
```
PASSED
1 passed in 0.01s
```

### Step 6: Run full test suite
```
cd backend && uv run pytest tests/ -q
```
Output:
```
63 passed, 2 warnings in 0.93s
```
No regressions. 2 deprecation warnings pre-existed (FastAPI `on_event` → lifespan).

### Step 7: Commit
```
git add backend/app/adapters.py backend/tests/test_llm.py
git commit -m "feat: pass --design and --locale flags to rendercv render"
```
Commit hash: `cca8c13`

## Self-Review Findings

- `_CONFIG_DIR` is correctly a module-level constant (not inside the class), making it importable as `from app.adapters import _CONFIG_DIR`
- Path derivation `Path(__file__).parent.parent / "rendercv_config"` resolves correctly: `backend/app/adapters.py` → `.parent` = `backend/app/` → `.parent` = `backend/` → `/ "rendercv_config"` = `backend/rendercv_config/`
- Existing flags `--dont-generate-markdown`, `--dont-generate-html`, `--dont-generate-png` are preserved
- No new environment variables or Settings fields introduced
- TDD sequence followed: failing test first, then implementation
