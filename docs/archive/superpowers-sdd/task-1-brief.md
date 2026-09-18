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
