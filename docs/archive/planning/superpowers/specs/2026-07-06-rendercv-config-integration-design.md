# RenderCV Config Integration Design

**Date:** 2026-07-06  
**Status:** Approved

## Problem

`design.yaml`, `locale.yaml`, and `settings.yaml` (RenderCV config files) sit at the project root and are not wired into PDF generation. The Dockerfile only copies `backend/`, so they never make it into the Docker image. Additionally, `normalize_to_rendercv()` hard-codes `design: {theme: "classic"}` which conflicts with the `engineeringresumes` theme defined in `design.yaml`.

## Approach

**Explicit CLI flags** — move config files into `backend/rendercv_config/` so they ship with the Docker image, then pass them as `--design` and `--locale` flags to the `rendercv render` subprocess. Path derived from `__file__` at runtime (hardcoded, no env var).

## Changes

### 1. File placement
Move from project root → `backend/rendercv_config/`:
- `design.yaml`
- `locale.yaml`
- `settings.yaml` (kept for reference; its `render_command.dont_generate_*` flags are already covered by explicit CLI args)

The existing `COPY backend/ ./backend/` Dockerfile line picks these up automatically.

### 2. `backend/app/adapters.py` — `RenderCVAdapter.render()`
- Compute `_CONFIG_DIR = Path(__file__).parent.parent / "rendercv_config"` as a module-level constant
- Add `"--design", str(_CONFIG_DIR / "design.yaml")` and `"--locale", str(_CONFIG_DIR / "locale.yaml")` to the subprocess args

### 3. `backend/app/yaml_utils.py` — `normalize_to_rendercv()`
- Remove the `data["design"] = {"theme": "classic"}` fallback injection
- Strip any `design:` block that the LLM may have emitted inside `cv:` (already done) but do **not** inject a replacement — design is now always provided via the external file

## What does NOT change
- Docker volumes, env vars, database schema, frontend — untouched
- The `--dont-generate-markdown`, `--dont-generate-html`, `--dont-generate-png` flags stay as-is (they match `settings.yaml`'s `render_command` values)

## Success criteria
- `rendercv render` picks up `engineeringresumes` theme and XCharter typography
- No `design:` block appears in normalized resume YAML
- Docker build (`COPY backend/`) automatically includes the config files
