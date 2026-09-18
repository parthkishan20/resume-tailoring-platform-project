# Data + Document-Rendering Layer Audit
`/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform` — FastAPI + raw sqlite3 + RenderCV 2.8

All line references verified against the working tree as of this audit. Tests run: 49 passed in 0.60s
(`test_rendercv_validation.py`, `test_yaml_utils.py`, `test_database.py`).

---

## Findings — ranked by severity

### P0

**1. No migration path at all. Schema changes silently do not apply to existing databases.**
`init_db` (`backend/app/database.py:34-52`) runs `conn.executescript(_schema_sql())` on every boot, and every
statement in `backend/db/schema.sql` is `CREATE TABLE IF NOT EXISTS`. On an existing volume
(`resumedb-data:/app/db`, `docker-compose.yml:9`) the script is a no-op. Add a column to `schema.sql` and
deploy: the table is untouched, the new code queries the column, and every request that touches that table
raises `sqlite3.OperationalError: no such column`. There is no version table, no Alembic, no `ALTER` path, and
`test_init_db_is_idempotent` (`backend/tests/test_database.py:59`) only proves re-running on an *unchanged*
schema is safe — it does not cover drift. Highest-risk item for production.

**2. No backups; the only durable copy of user data is a Docker named volume.**
`DB_PATH=/app/db/resumedb.db` (`backend/app/config.py:11`) on `resumedb-data`. `docker compose down -v`, a
volume prune, or host loss destroys the master resume and all generated resumes with no recovery.
`master_resume_history` (`schema.sql:8`) keeps only 10 versions, capped by `HISTORY_LIMIT` (`database.py:5`,
prune at `database.py:80-86`); `generated_resumes.yaml_content` has no history at all.

**3. `PUT /api/master-resume` stores arbitrary unvalidated text.**
`backend/app/routes/master_resume.py:96-99` passes `body.yaml_content` straight to `upsert_master_resume`. No
`safe_load`, no normalize, no schema check. The canonical source document for every downstream render can be
non-YAML garbage, and the failure only surfaces later at `/preview` or during generation. Contrast
`import_pdf` (`master_resume.py:156`), which does normalize.

### P1

**4. `normalize_to_rendercv` runs CPU-bound rendercv validation synchronously on the event loop.**
`_validate_and_repair` (`yaml_utils.py:368-406`) imports rendercv and builds up to 5 full pydantic models over
`copy.deepcopy`'d data. Called from async handlers with no `to_thread`: `master_resume.py:120`,
`resumes.py:69`, `resumes.py:94`, `resumes.py:110`. Measured on the real `planning/master-resume.yaml`:

```
cold (incl. rendercv import): 4.940s
warm avg:                     0.134s
```

The first render after boot freezes the *entire* single-worker server (`Dockerfile:41-43`, `--workers 1`) for
~5s — health checks included. Every generation blocks the loop ~0.4s across its three calls.
Fix: `await asyncio.to_thread(normalize_to_rendercv, ...)` at all four call sites, and warm the rendercv
import in `lifespan` (`main.py:20-27`).

**5. `master_resume` and `system_prompt` have no `UNIQUE(user_id)`; the upserts are read-then-write.**
`schema.sql:1-6` and `:43-48` declare no uniqueness. `upsert_master_resume` (`database.py:70-101`) does
`SELECT` → branch → `INSERT` or `UPDATE`; `upsert_system_prompt` (`database.py:303-323`) does the same. Two
concurrent `PUT`s on a fresh DB both see no row and both `INSERT`. Afterwards `get_master_resume`
(`database.py:60-63`) does `fetchone()` and silently returns whichever row SQLite yields first — the user's
edits appear to randomly revert. `generation_rules` got this right (`UNIQUE(user_id, section, rule_key)`,
`schema.sql:40`, with a real `ON CONFLICT` upsert at `database.py:272-273`); the other two did not.

**6. `rendercv` subprocess has no timeout.**
`backend/app/adapters.py:87-97`: `await proc.communicate()` with no `asyncio.wait_for`. A hung
`rendercv`/`typst` holds the SSE connection, the `TemporaryDirectory`, and the subprocess forever. No kill
path, no cap on concurrent renders — N concurrent generations spawn N typst processes.

**7. The validation backstop silently deletes user data with no signal to the user.**
`_validate_and_repair` prunes anything rendercv rejects (`yaml_utils.py:395-400`) and only `logger.warning`s.
`test_backstop_prunes_fields_normalizer_does_not_know` (`test_rendercv_validation.py:166-175`) codifies this:
`email: not-an-email` → `email` deleted. The user receives a PDF with no email address and is never told.
`normalize_to_rendercv` returns only a `str` — there is no channel for diagnostics. Same for dropped phones
(`yaml_utils.py:101`) and dropped social networks (`yaml_utils.py:162`).

**8. Timestamps are UTC-naive text, misread as local time by the frontend.**
All timestamps default to `datetime('now')` → `"2026-09-18 14:22:01"` TEXT (`schema.sql:5,12,22,23,31,47`;
also `database.py:88,191,312`). That is UTC, space-separated, no offset. `new Date("2026-09-18 14:22:01")` in
V8 parses it as *local* time, so `frontend/src/components/MasterResumePanel.tsx:67` and
`frontend/src/components/ResumeListPanel.tsx:101` display every timestamp shifted by the host offset (−4h in
EDT). Store ISO-8601 with `Z`, or emit `strftime('%Y-%m-%dT%H:%M:%SZ','now')`.

**9. `sort`/`order`/`page`/`limit` reach SQL unvalidated from the query string.**
`backend/app/routes/resumes.py:47-50` forwards raw query params to `list_resumes` (`database.py:115-137`).
`sort_col`/`order_dir` are whitelisted (`database.py:123-124`) so the f-string at `database.py:132-134` is not
injectable — but `limit` and `page` are unbounded. `limit=-1` → `LIMIT -1` → SQLite returns *every* row;
`page=0` → negative offset. Add `Query(ge=1, le=100)` bounds.

### P2

**10. `with sqlite3.connect(...)` never closes the connection.**
Every one of the 17 DB functions uses `with sqlite3.connect(db_path) as conn:`. `sqlite3.Connection.__exit__`
commits or rolls back — it does **not** close. Connections survive until refcount GC. Under load through
`asyncio.to_thread`'s bounded executor this leaks fds and leaves `-wal`/`-shm` handles open. Use
`contextlib.closing` or an explicit context manager.

**11. No WAL, no `busy_timeout` tuning, no `foreign_keys` pragma, no indexes, no foreign keys.**
`schema.sql` declares zero indexes and zero foreign keys. `master_resume_history.user_id` and
`generated_resumes.user_id` are free-floating TEXT with no FK and no `ON DELETE`. `delete_master_resume`
(`database.py:104-110`) deletes the resume but leaves its history rows orphaned forever. Every query filters
on `user_id` with no index; `list_resumes` does `ORDER BY created_at` with no index → full scan + sort. No
`PRAGMA journal_mode=WAL` means readers block writers, and the default 5s busy timeout surfaces as an
unhandled `OperationalError` → 500.

**12. `settings.yaml` is dead configuration.**
`backend/rendercv_config/settings.yaml` is never read by any code — `grep` finds it only under
`docs/superpowers/`. `adapters.py:12` defines `_CONFIG_DIR` and uses only `design.yaml` (`:89`) and
`locale.yaml` (`:79`). rendercv 2.8 *does* expose `--settings PATH` (verified via `rendercv render --help`),
so `pdf_title: Parthkumar_Patel_resume_{role}`, `bold_keywords`, and `current_date` are all inert. The
`pdf_title` value also hardcodes a specific person's name into repo config.

**13. The locale-embedding workaround rests on a misdiagnosis.**
`adapters.py:75-84` merges `locale.yaml` into the user's YAML, with the comment *"rendercv --locale flag
expects a dict, not a file path"*. The actual flag is `--locale-catalog / -lc` and it takes a `PATH`
(confirmed in `rendercv render --help`). `--locale` simply does not exist, which is presumably what was tried.
The workaround functions but is fragile: `data.update(locale_data)` mutates top-level user keys, and the guard
`if "locale" not in data` (`adapters.py:78`) means an LLM that emits a stray `locale:` key silently disables
the project locale — `normalize_to_rendercv` strips `design` (`yaml_utils.py:423-424`) but not `locale`.
`test_llm.py:120` even asserts `"--locale" not in cmd_str`, freezing the misdiagnosis into the test suite.

**14. The backstop is coupled to rendercv 2.8 private internals and fails open, silently.**
`yaml_utils.py:373-377` imports `rendercv.exception.RenderCVUserValidationError` and
`rendercv.schema.rendercv_model_builder.build_rendercv_model_from_commented_map` inside a bare
`try/except Exception: return`. If rendercv reorganizes those modules the backstop becomes a permanent no-op
with no log line and no test failure (`test_normalized_output_passes_rendercv_schema`,
`test_rendercv_validation.py:178`, uses `importorskip` and would just skip). `pyproject.toml:9` pins
`rendercv[full]>=2.8` with no upper bound.

**15. The backstop validates against a different theme than the renderer uses.**
`yaml_utils.py:382` sets `probe["design"] = {"theme": "classic"}`; the actual render passes
`--design .../design.yaml` with `theme: engineeringresumes` (`design.yaml:2`). Theme-specific design
validation diverges from what is validated.

**16. `phonenumbers` is an undeclared direct dependency.**
`yaml_utils.py:89` imports it unguarded inside `_normalize_phone`. It is not in
`backend/pyproject.toml:5-13`; it arrives transitively via rendercv (`uv.lock:971`, pulled in at
`uv.lock:1419`). If rendercv drops it, `ImportError` escapes `normalize_to_rendercv` uncaught and every render
500s.

**17. Orphaned rows and orphaned PDFs on partial failure.**
`resumes.py:119-131`: `create_resume` → write PDF → `update_resume`. A crash between steps 1 and 2 leaves a DB
row with `pdf_path=NULL`; a crash between 2 and 3 leaves a PDF on disk that no row references.
`delete_generated` (`resumes.py:195-203`) deletes the row first and unlinks second; an unlink failure orphans
the file permanently. No reaper exists.

**18. Chat reads the entire history on every turn.**
`chat.py:47` calls `get_chat_messages` (unbounded `SELECT`, `database.py:224-228`), then slices `[-30:]` in
Python (`chat.py:53`). `GET /api/chat` (`chat.py:35`) also returns every message ever. Push the limit into SQL.

**19. The master-resume schema contract exists in five drifting places with no single source of truth.**
- `_IMPORT_SYSTEM_PROMPT` prose schema — `master_resume.py:20-77`
- `GENERATION_SYSTEM_PROMPT` structural rules — `prompts.py:1-125`
- the docstring — `yaml_utils.py:1-13`
- hand-copied constants `_CV_ALLOWED_KEYS` / `_SECTION_KEYS` / `_VALID_NETWORKS` — `yaml_utils.py:26-54`
- the only machine-readable pointer, `# yaml-language-server: $schema=.../v2.8/schema.json`, is line 1 of
  `planning/master-resume.yaml`, which no code reads.

They already contradict each other: `_IMPORT_SYSTEM_PROMPT:65-66` instructs the LLM to emit
`design:\n  theme: classic`, which `normalize_to_rendercv` then strips (`yaml_utils.py:423-424`) and which
`test_yaml_utils.py:29-42` asserts must be stripped.

**20. `DEFAULT_RULES` section names don't match the YAML section keys.**
`database.py:11,19` use `extracurricular`; `_SECTION_KEYS` (`yaml_utils.py:53`) and the real master resume use
`extra_curricular_activities`. `rules_block` (`prompts.py:193-202`) emits `- extracurricular.max_entries = 1`
into the prompt, naming a section that does not exist in the YAML the LLM is editing. Also
`certifications.max_entries = 2` against 9 certifications in the master resume, and `skills.max_entries = 20`
against a single 42-item skills group.

**21. `work_experience` is hoisted but never normalized.**
`_SECTION_KEYS` includes `work_experience` (`yaml_utils.py:53`) so it is moved under `cv.sections`, but
`normalize_to_rendercv:497-506` only dispatches normalizers for the exact keys
`experience`/`education`/`projects`/`skills`/`certifications`. A `work_experience` section skips
`_normalize_experience` entirely (no `job_title`→`position`, no `_split_duration`) and reaches rendercv as an
untyped custom section.

**22. Latent path traversal on `pdf_path`.**
`resumes.py:173` and `:202` do `Path(_pdfs_dir()) / row["pdf_path"]`. `update_resume` accepts a `pdf_path`
parameter (`database.py:178`), and if it ever becomes reachable from a request body, `../../etc/passwd`
escapes the directory. Currently unreachable only because `ResumeUpdate` (`resumes.py:41-44`) omits the field.
Resolve-and-verify against `PDFS_DIR`, or derive the path from `resume_id` and drop the column from the API
surface.

**23. `planning/master-resume.yaml` is untracked, not gitignored, and contains real PII.**
`git check-ignore` returns non-zero. The file holds a real name, `ppatel36@stevens.edu`, `+15519967909`, a
home address, LinkedIn/GitHub handles, and nine personal certificate verification URLs including LinkedIn
tokens with `accountId`/`authUUID` query parameters. One `git add -A` publishes it. The `.gitignore` diff in
this working tree adds `.agents/`, `skills-lock.json`, `.claude/skills/` but not
`planning/master-resume.yaml`.

---

## Full schema

`backend/db/schema.sql` — 6 tables, no indexes, no foreign keys, no triggers, no `schema_version`.

| Table | Column | Type / constraint | Written by | Read by |
|---|---|---|---|---|
| **master_resume** | `id` | INTEGER PK AUTOINCREMENT | — | `get_master_resume` |
| | `user_id` | TEXT NOT NULL DEFAULT 'default'; **no UNIQUE** (P1 #5) | `upsert_master_resume` (`database.py:94`) | all master-resume fns |
| | `yaml_content` | TEXT NOT NULL — unvalidated YAML blob | `upsert_master_resume` (`database.py:88,94`) ← `PUT /api/master-resume` (unvalidated), `POST /import` (normalized) | `GET /api/master-resume`, `/preview` (`master_resume.py:120`), generation (`resumes.py:69`) |
| | `updated_at` | TEXT DEFAULT `datetime('now')`, UTC naive (P1 #8) | `database.py:88` | `MasterResumePanel.tsx:67` |
| **master_resume_history** | `id` | INTEGER PK AUTOINCREMENT | | ordering + prune key |
| | `user_id` | TEXT NOT NULL DEFAULT 'default'; no FK, orphaned on delete | `database.py:77` | prune query `database.py:81-86` only |
| | `yaml_content` | TEXT NOT NULL — the *previous* master body | `database.py:77` | **nothing** — no read path, no restore endpoint exists |
| | `saved_at` | TEXT DEFAULT `datetime('now')` | implicit | `test_database.py:100` only |
| **generated_resumes** | `id` | INTEGER PK AUTOINCREMENT — also the PDF filename | | `resumes.py:125,186` |
| | `user_id` | TEXT NOT NULL DEFAULT 'default' | `database.py:151` | all resume fns |
| | `name` | TEXT NOT NULL DEFAULT 'Untitled' — `f"Resume — {jd[:40]}"` (`resumes.py:118`) | `database.py:151`, `update_resume` | list / detail |
| | `job_description` | TEXT NOT NULL DEFAULT '' — unbounded | `database.py:151` | list, sort key (`database.py:123`) |
| | `yaml_content` | TEXT NOT NULL — post-audit normalized YAML; no history | `database.py:151`, `PATCH` (`resumes.py:157-165`) | `POST /render` (`resumes.py:185`) |
| | `pdf_path` | TEXT NULL — bare filename `{id}.pdf`; joined unvalidated (P2 #22) | `database.py:153,188` | `resumes.py:173,202` |
| | `created_at` / `updated_at` | TEXT DEFAULT `datetime('now')`, UTC naive | `database.py:191` | `ResumeListPanel.tsx:101` |
| **chat_messages** | `id` | INTEGER PK AUTOINCREMENT | | ordering key (`database.py:227`) |
| | `user_id` | TEXT NOT NULL DEFAULT 'default' | `chat.py:44,63` | `get_chat_messages` |
| | `role` | TEXT NOT NULL **CHECK (role IN ('user','assistant'))** — the only CHECK in the schema | `chat.py:44,63` | LLM message array `chat.py:52` |
| | `content` | TEXT NOT NULL — unbounded, never pruned | `chat.py:44,63` | `chat.py:53` |
| | `created_at` | TEXT DEFAULT `datetime('now')` | implicit | frontend |
| **generation_rules** | `id` | INTEGER PK AUTOINCREMENT | | |
| | `user_id`,`section`,`rule_key` | TEXT NOT NULL, **UNIQUE(user_id, section, rule_key)** (`schema.sql:40`) | `init_db` seed (`database.py:40-44`), `upsert_rules` real ON CONFLICT upsert (`database.py:272-273`), `reset_rules` | `get_rules` → `rules_block` (`prompts.py:193`) |
| | `rule_value` | TEXT NOT NULL — numbers stored as strings, never parsed, interpolated into the prompt verbatim | `PUT /api/rules` (`rules.py:31`) | `prompts.py:198` |
| **system_prompt** | `id` | INTEGER PK AUTOINCREMENT | | |
| | `user_id` | TEXT NOT NULL DEFAULT 'default'; **no UNIQUE** (P1 #5) | `database.py:317` | `get_system_prompt` |
| | `content` | TEXT NOT NULL, seeded from `DEFAULT_SYSTEM_PROMPT` (`database.py:22-27`) | `PUT /api/system-prompt` | `chat.py:49` — only the *chat* path; generation uses the hardcoded `prompts.py` constants |
| | `updated_at` | TEXT DEFAULT `datetime('now')` | `database.py:312` | frontend |

No JSON-in-TEXT columns. The blob columns are YAML (`yaml_content` ×3).

---

## Persistence layer

Raw `sqlite3`, no ORM. One connection opened and (not) closed per function call — 17 module-level functions in
`database.py`, each taking `db_path: str`. No pooling, no `check_same_thread` override needed since nothing is
shared across threads. All routes correctly wrap calls in `asyncio.to_thread` (`resumes.py:50,61,72,119,129,
151,159,170,182,189,197,198`; `chat.py:36,44,47,48,63,79`; `rules.py:27,32,38`; `system_prompt.py:21,29,34`;
`master_resume.py:90,98,104,115,157`; `main.py:26`) — no DB call is left on the event loop. Thread-safety is
fine by construction; the defects are closure (#10), missing pragmas/indexes (#11), and non-atomic upserts
(#5).

Transactions: `with conn` gives one implicit transaction per function, so `upsert_master_resume`'s
history-insert + prune + update (`database.py:75-96`) is atomic, as is `reset_rules`' delete+reinsert
(`database.py:282-286`). The explicit `conn.commit()` calls before the trailing `SELECT`s are redundant but
harmless. `init_db`'s `executescript` (`database.py:36`) issues an implicit COMMIT first — fine here.

No N+1 in the classic sense. The unbounded reads are #18 (full chat history per turn) and `list_resumes`'
unindexed `COUNT(*)` + sort.

---

## RenderCV pipeline — end to end

```
LLM / user YAML (str)
  → normalize_to_rendercv()            yaml_utils.py:409   [SYNC ON EVENT LOOP — P1 #4]
      safe_load (:412)  — parse failure returns input VERBATIM (:414)
      strip design cv-level + top-level (:423-424)
      flatten cv.contact → cv.* + socials (:427-451)
      phone → E.164 via phonenumbers, else DROP (:454-459, _normalize_phone:82)
      website → prepend https:// (:462-463)
      _normalize_social_networks (:466) — canonicalize, strip URL, drop unknown
      hoist _SECTION_KEYS into cv.sections (:469-474)
      label/title → headline (:477-479)
      drop keys ∉ _CV_ALLOWED_KEYS (:481-484)
      coerce every section to a list (:487-494)
      per-section normalizers (:497-506)
      _clean_highlights + _fix_date_order per entry (:509-513)
      _validate_and_repair (:519) — up to 5× deepcopy + pydantic build, PRUNE on failure
      yaml.dump(allow_unicode=True, sort_keys=False) (:521)
  → BackendAPI.render()                backend_api.py:19
  → RenderCVAdapter.render()           adapters.py:69
      TemporaryDirectory()             :70
      safe_load, merge locale.yaml top-level if "locale" absent, re-dump  :77-84
      write tmpdir/resume.yaml         :86
      asyncio.create_subprocess_exec(  :87-96
        rendercv render <tmp>/resume.yaml
        --design <backend>/rendercv_config/design.yaml
        --pdf-path <tmp>/resume.pdf
        --dont-generate-markdown --dont-generate-html --dont-generate-png )
      await communicate()              :97   [NO TIMEOUT — P1 #6]
      returncode != 0 → RenderError(stdout+stderr)  :98-105
      read tmpdir/resume.pdf → bytes   :106
  → write PDFS_DIR/{resume_id}.pdf     resumes.py:125-127 / :186-188
  → update_resume(pdf_path)            resumes.py:129 / :189
```

**Concurrency — safe, by accident.** rendercv's default `--output-folder rendercv_output` resolves relative to
the *input file*, not the CWD. Verified by running the exact command line from a third directory: the `.typ`
landed in the input file's directory, not the CWD. Since each render gets its own `TemporaryDirectory`, two
simultaneous renders cannot collide on disk. Nothing in the code documents or tests this invariant — passing a
relative `--pdf-path`, or rendercv changing the resolution base, would break it silently.

**Cleanup.** `TemporaryDirectory` removes everything including the stray `rendercv_output/NAME_CV.typ` —
`--dont-generate-typst` is not passed (only md/html/png are), so a Typst file is written and discarded every
render.

**Working-directory assumptions.** `_CONFIG_DIR = Path(__file__).parent.parent / "rendercv_config"`
(`adapters.py:12`) is `__file__`-relative, not CWD-relative, so it survives the `WORKDIR /app/backend` in the
Dockerfile. `rendercv` must be on `PATH`; resolved via `uv run` at `Dockerfile:41`.

**Failure surfacing.** `RenderError` carries the raw concatenated stdout+stderr of a CLI written for a terminal
— including Rich box-drawing characters and ANSI. That string is returned to the browser verbatim: 500 +
`RENDER_FAILED` via `main.py:45-47`, 422 via `master_resume.py:121-122`, or an SSE `error` event via
`resumes.py:138-139`. It is never parsed into field-level errors the editor could highlight.

**Config threading — what is actually done now** (the recent commits are accurate):
- `design.yaml` — passed as `--design <abs path>` (`adapters.py:89`). Stripped from the document at both
  levels (`yaml_utils.py:423-424`). Verified by `test_yaml_utils.py:5-42` and `test_llm.py:121-122`. ✓
- `locale.yaml` — **not** passed as a flag; its parsed contents are merged into the top level of the user's
  document (`adapters.py:77-84`). Works, but rests on a wrong premise (#13).
- `settings.yaml` — not threaded in at all. Dead file (#12).

---

## YAML validation

`yaml.safe_load` everywhere — `yaml_utils.py:412`, `adapters.py:77,80`, all tests. No `yaml.load`, no
`Loader=`, no `!!python/object` exposure. No YAML injection risk found.

What escapes validation:
- **`PUT /api/master-resume`** — nothing validates it (P0 #3).
- **Unparseable YAML** — `normalize_to_rendercv:411-414` swallows the exception and returns the input string
  unchanged. Same for `not isinstance(data, dict)` (`:415-416`) and a missing/non-dict `cv` (`:418-420`). In
  all three cases malformed input flows onward as if normalized.
- **`PATCH /api/resumes/{id}`** — `yaml_content` (`resumes.py:43,161`) is stored without normalization; only
  the later `POST /render` discovers it is invalid.
- **The audit pass** — `resumes.py:106-109` splits on the literal `AUDIT_END` and takes everything after. If
  the LLM omits the marker, the *entire* audit prose is treated as YAML; `normalize_to_rendercv` then fails to
  parse it and returns it verbatim (`:414`), and it is persisted as `yaml_content` at `resumes.py:120` before
  `render` rejects it.

Unicode/escaping: `yaml.dump(..., allow_unicode=True)` (`yaml_utils.py:521`, `adapters.py:83`) is correct.
Note `planning/master-resume.yaml:~322` contains a `’` escape inside a double-quoted scalar, evidence the
file was round-tripped at some point by a dumper *without* `allow_unicode` — harmless on reload, but it shows
the file has been machine-rewritten by a path that no longer exists.

Schema contract: see P2 #19 — five locations, no single source of truth, already mutually contradictory.

---

## Uncommitted work

**`backend/app/yaml_utils.py` (+~190 lines) — complete, coherent, and tested.** Six additions:
1. `_normalize_phone` rewritten from a 10/11-digit regex to real `phonenumbers` validation returning E.164 or
   `None`. A genuine correctness fix — the old version fabricated `+1-555-000-0000` from a placeholder, which
   rendercv then rejected, failing the whole render. Side effect: previously-accepted valid international
   numbers are now *kept* (they were silently dropped before), covered by `test_international_phone_kept`.
2. `_CV_ALLOWED_KEYS` allowlist + `label`/`title` → `headline` aliasing (`:477-484`).
3. `_VALID_NETWORKS`/`_NETWORK_ALIASES` + `_normalize_social_networks` (`:149-171`).
4. `_clean_highlights` and `_fix_date_order` applied to every section (`:509-513`).
5. Section-shape coercion — drops `None` sections, wraps scalars (`:487-494`). This is what fixes the
   `certifications:`-with-no-value crash.
6. `_validate_and_repair` backstop (`:368-406`).

Prune-ordering logic reviewed closely: `sorted(..., key=(len(loc), _loc_sort_key(loc)), reverse=True)` yields
deepest-first, and within equal depth highest index first — so deleting `experience[1]` before `experience[0]`
never shifts a pending index. The `any(p[:len(loc)] == loc for p in pruned)` guard correctly skips a location
whose descendant was already removed this round. The 5-iteration cap and the `if not changed: return` bail
both terminate. No ordering bug found.

The substantive concern is #7 (deletes without telling anyone). Secondary: #4 (event loop), #14 (private-API
coupling, fails open silently), #15 (validates `classic`, renders `engineeringresumes`).

Also note the diff's line-230 addition,
`if not e.get("area") and e.get("degree"): e["area"] = str(e.pop("degree"))` — it *destroys* `degree` to
satisfy rendercv's required `area`. `"MBA"` renders as area "MBA" with no degree rather than as a degree.
Correct-by-necessity given rendercv's model, but lossy, and `test_education_without_area_uses_degree_text`
(`test_rendercv_validation.py:95`) locks the behavior in.

**`backend/app/routes/master_resume.py` — one line, correct.**
`+ "- Omit phone entirely if no phone number appears in the source — never invent one."` at `:76`. Directly
complements the phonenumbers change: stop the LLM inventing `+1-555-000-0000` at the source rather than only
dropping it downstream. The prompt still contradicts itself elsewhere (`design: theme: classic` at `:65-66`,
which normalize strips).

**`backend/tests/test_rendercv_validation.py` (untracked, 215 lines) — good, should be committed.**
15 tests, one per observed real-world failure, organized by failure class, with an end-to-end test (`:178`)
that feeds deliberately nasty input through `normalize_to_rendercv` and asserts it builds against rendercv's
real model. `pytest.importorskip("rendercv")` guards it. All 49 tests across the three files pass in 0.60s.
Gaps: no test asserts the backstop *doesn't* over-prune a valid document, and nothing asserts the
`_validate_and_repair` import path still resolves (a rendercv reorg would silently skip rather than fail, #14).

**`planning/master-resume.yaml` (untracked, 340 lines) — do not commit as-is.**
Beyond the PII exposure (#23), running it through the real normalizer surfaces a live defect:

```
sections: ['education','experience','projects','skills','certifications','extra_curricular_activities']
cert[0]:  {'name': 'Claude 101',
           'highlights': ['Issued by Anthropic',
                          '[Certificate](https://verify.skilljar.com/c/hr943kh82n3i)']}
```

All 9 certifications use `company`/`position` keys, so `_normalize_certifications`
(`yaml_utils.py:288-297`) logs **18 warnings** on every render — warnings whose text (*"the LLM routed an
experience-shaped entry into certifications"*, `yaml_utils.py:277-279`) blames the LLM for what is actually
the hand-authored master resume's own shape. The canonical document does not conform to the schema its own
import prompt specifies. Either the file should use `name`/`issuer`, or `_normalize_certifications` should
stop warning on this shape. Also `extra_curricular_activities` is hoisted but has no normalizer (#21), and the
single 42-skill group contradicts `GENERATION_SYSTEM_PROMPT`'s "2–4 labeled groups, 15–20 skills"
(`prompts.py:40-41`).

The `.gitignore` and `docker-compose.yml` diffs are unrelated and fine (the compose change drops the obsolete
`version: "3.9"` key).

---

## Restructure proposal

### A. Persistence → repositories + models + migrations

```
backend/app/database.py                       →  DELETE (split as below)
backend/db/schema.sql                         →  backend/migrations/0001_initial.sql
                                                 (+ UNIQUE(user_id) on master_resume & system_prompt,
                                                    FKs with ON DELETE CASCADE,
                                                    indexes on (user_id), (user_id, created_at),
                                                    ISO-8601 UTC timestamp defaults)

NEW backend/app/db/engine.py        — connect(): WAL, busy_timeout=5000, foreign_keys=ON,
                                      row_factory=Row; a `session()` contextmanager that
                                      actually CLOSES; one place for to_thread dispatch
NEW backend/app/db/migrate.py       — schema_version table + ordered .sql apply-on-boot;
                                      called from main.py lifespan in place of init_db
NEW backend/app/db/models.py        — Pydantic row models: MasterResume, MasterResumeVersion,
                                      GeneratedResume, ChatMessage, GenerationRule, SystemPrompt
                                      (routes stop returning raw dicts)
NEW backend/app/db/repositories/master_resume.py   ← database.py:57-110  (+ real ON CONFLICT upsert)
NEW backend/app/db/repositories/resumes.py         ← database.py:115-216 (+ bounded limit/page)
NEW backend/app/db/repositories/chat.py            ← database.py:221-250 (+ SQL-side LIMIT)
NEW backend/app/db/repositories/rules.py           ← database.py:255-288
NEW backend/app/db/repositories/system_prompt.py   ← database.py:293-327
NEW backend/app/db/seed.py                         ← database.py:7-27,37-51 (DEFAULT_RULES,
                                                     DEFAULT_SYSTEM_PROMPT) — idempotent, post-migrate
```

Alembic is available but heavy for raw sqlite3; a ~40-line `migrate.py` over numbered `.sql` files plus a
`schema_version` table is proportionate and removes the P0. If an ORM is wanted anyway, SQLModel gives models +
Alembic together, and the repository boundary above is exactly what makes that swap mechanical later.

### B. Rendering service isolation

```
backend/app/adapters.py:68-106 (RenderCVAdapter)  →  backend/app/rendering/rendercv_runner.py
                                                     + asyncio.wait_for timeout (settings.RENDER_TIMEOUT_S)
                                                     + asyncio.Semaphore(settings.MAX_CONCURRENT_RENDERS)
                                                     + --dont-generate-typst
                                                     + --settings <settings.yaml>    (fixes #12)
                                                     + --locale-catalog <locale.yaml> (replaces the
                                                       top-level merge; deletes adapters.py:75-84)
NEW backend/app/rendering/config.py    — _CONFIG_DIR + a RenderProfile(design/locale/settings paths),
                                         overridable by env so the person's name leaves repo config
NEW backend/app/rendering/errors.py    — parse rendercv stderr into field-located RenderIssue objects
                                         instead of shipping ANSI-laden CLI text to the browser
backend/app/adapters.py:25-65  (LiteLLM)  →  backend/app/llm/litellm_adapter.py
backend/app/adapters.py:109-129 (PyMuPDF) →  backend/app/pdf/pymupdf_adapter.py
backend/app/adapters.py                   →  DELETE once emptied
```

### C. Canonical schema — one source of truth

```
NEW backend/app/resume_schema/models.py     — Pydantic models (Cv, Section entry unions,
                                              SocialNetwork) built ON TOP of rendercv's own
                                              public model, not hand-copied constants.
                                              _CV_ALLOWED_KEYS / _VALID_NETWORKS / _SECTION_KEYS
                                              (yaml_utils.py:26-54) become derived:
                                              set(Cv.model_fields), the SocialNetwork network
                                              Literal, etc. — they can no longer drift from rendercv.
NEW backend/app/resume_schema/prompt.py     — generate the LLM-facing schema text FROM those models,
                                              replacing the hand-written _IMPORT_SYSTEM_PROMPT block
                                              (master_resume.py:20-77) and the yaml_utils docstring.
NEW backend/app/resume_schema/validate.py   — validate(str) -> (Document, list[RenderIssue]);
                                              used by PUT /api/master-resume (closes P0 #3) and
                                              PATCH /api/resumes (closes the gap at resumes.py:161)

backend/app/yaml_utils.py:409-521 (normalize_to_rendercv)
    →  backend/app/resume_schema/normalize.py
       signature change: str -> NormalizeResult(yaml: str, dropped: list[DroppedField])
       so pruned emails/phones/networks reach the UI instead of only the log (closes P1 #7).
       Call sites to update: master_resume.py:120, resumes.py:69, resumes.py:94, resumes.py:110
       — all four wrapped in asyncio.to_thread (closes P1 #4).

backend/app/yaml_utils.py:339-406 (_prune_path/_loc_sort_key/_validate_and_repair)
    →  backend/app/resume_schema/repair.py
       import rendercv internals ONCE at module import; on ImportError raise at startup
       rather than degrading to a silent no-op (closes P2 #14);
       probe with the real design.yaml theme, not "classic" (closes P2 #15).

backend/app/yaml_utils.py:202-336 (per-section normalizers)
    →  backend/app/resume_schema/sections.py
       + add a work_experience → experience alias so the hoisted key is actually
         normalized (closes P2 #21)

backend/app/yaml_utils.py  →  DELETE once emptied.

NEW pyproject dependency: "phonenumbers>=9"   (closes P2 #16)

Tests follow the split:
  backend/tests/test_rendercv_validation.py (untracked) → tests/resume_schema/test_normalize.py
  backend/tests/test_yaml_utils.py                      → tests/resume_schema/test_sections.py
  backend/tests/test_database.py                        → tests/db/test_repositories.py
  NEW tests/db/test_migrations.py — apply 0001 to an empty DB, then every later migration to a
                                    *populated* DB, asserting data survives. This is the test that
                                    would have caught P0 #1.
```

### D. Sequencing

1. **#1 and #5 together** — one migration pair: `0001_initial.sql` reproducing the current schema exactly,
   `0002_unique_user_id.sql` adding the constraints (requires dedupe-then-rebuild on SQLite).
2. **#4 and #6** — both nearly one-line, highest impact per unit of change.
3. **#3** via `resume_schema/validate.py`.
4. Everything else follows the module moves in A/B/C.
