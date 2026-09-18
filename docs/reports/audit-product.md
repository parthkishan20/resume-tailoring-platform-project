# ResumeTailor — Spec vs Implementation Audit

**Repo:** `/Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform`
**Branch:** `main` @ `e943dfb` (52 commits, last commit 2026-07-14)
**Scope:** product specification, documentation, and planning artifacts cross-checked against the shipped backend routes, frontend components, and types. Read-only audit; no files were modified.

---

## 1. The product as specified

**Vision** (`planning/PLAN.md:7-19`):

> "ResumeTailor is an AI-powered workstation for job seekers. Users maintain a single **master resume** in render-cv YAML format, then generate tailored, ATS-optimized resumes for specific job descriptions — all without leaving the browser."
>
> - "**Master resume first:** one source of truth in render-cv YAML; all generated resumes derive from it"
> - "**AI-assisted everywhere:** an LLM chat assistant can perform any workstation action on the user's behalf"
> - "**Built by agents:** personal project built entirely by AI coding agents demonstrating orchestrated, production-quality full-stack development"
>
> Core principles: "Everything through the workstation"; "Simple, clean, easy to understand code — no over-engineering"

### Intended user journey, end to end

From `PLAN.md:21-45`:

1. **First launch.** "The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. **No login, no signup.**"
2. **API key setup.** "Users add their OpenRouter API key to a `.env` file before starting the container. The API key is injected via environment variable and never sent from the browser or stored in the database. It is only used server-side to authenticate with OpenRouter."
3. **Guided empty state** (no master resume yet): "Instructions for creating a master resume"; "A sample `master-resume.yaml` file to download as a starting point"; "**A rendered preview of that sample** (like `planning/example-yaml-preview.png`)"; "A link to rendercv.com"; "Option to drag-and-drop an existing PDF resume for AI-powered conversion to YAML".
4. **Master resume.** Create blank or from sample; upload a PDF for AI extraction; paste/edit YAML in the workstation; **live preview as they edit**; or drive all of it through the chat assistant.
5. **Generation.** Paste a JD → tailored ATS-optimized resume derived from the master; configure generation rules; live preview; **edit the generated resume post-generation**; **re-render the PDF after edits**; **rename or delete**; browse a **sortable log** (by date or by job description).
6. **Evaluation.** "Score a master resume **or generated resume** against a job description. Output: ATS keyword match percentage + qualitative LLM critique of gaps and suggestions + side-by-side keyword diff highlighting missing and matched terms."
7. **Chat.** "Conversational assistant that can perform **any workstation action** (create/edit resume, generate, evaluate). Full conversation history persisted in the database. **Users can view, edit, or reset the default system prompt** used by the assistant."

### Full intended feature list (`PLAN.md:47-100`)

**Master Resume:** create new (blank or from sample) · upload PDF → AI converts to render-cv YAML · paste/edit YAML directly · live preview while editing · create/edit via chat assistant.

**Resume Generation:** paste JD → tailored ATS-optimized resume · configure generation rules per section · live preview of generated resume · edit generated resume directly · re-render PDF after edits · rename or delete generated resumes · sortable log (date / job description).

**Generation Rules** *(applied at generation time as LLM prompt instructions)*: max entries per section (education, experience, projects, extracurricular, certifications) · max entries in skills · max characters per bullet ("to keep each point to one line") · max bullet points per experience/project/extracurricular entry · "Rules are global defaults (not per-job-description), but some rules are specified per resume section".

**Evaluation:** score master **or generated** resume vs JD → ATS keyword match % + qualitative critique + side-by-side matched/missing keyword diff.

**AI Chat Assistant:** performs any workstation action · full history persisted · user-editable and resettable system prompt.

**Visual design** (`PLAN.md:86-131`): light/dark theme toggle · smooth animations and progress indicators for long-running operations · "Professional, data-dense layout — every pixel earns its place" · "Desktop-first; responsive down to tablet" · "Single-page application: one shell layout with collapsible panels, no multi-route navigation" · exact 14-token monochrome palette · font Inter.

**Infrastructure** (`PLAN.md:340-418`): multi-stage Dockerfile · single container, port 8000 · two named volumes · HEALTHCHECK on `/api/health` · four idempotent start/stop scripts (mac + windows) · lazy DB init.

**Testing** (`PLAN.md:436-471`): backend pytest (LLM structured output, routes, PDF generation, PDF import) · frontend React Testing Library · Playwright E2E in `test/` with a dedicated `docker-compose.test.yml`, 8 named scenarios, `LLM_MOCK=true`.

### Stated non-goals and constraints

- `PLAN.md:151` — "SQLite over Postgres | **No auth = no multi-user** = no need for a database server; self-contained, zero config"
- `PLAN.md:225` — master-resume history is "a safety net, not a feature… **There is no UI for browsing history in v1**"
- `PLAN.md:415-418` — "A Terraform configuration for App Runner **may** be provided in a `deploy/` directory as a **stretch goal, but is not part of the core build**"
- `PLAN.md:127-129` — "**Note for agents:** The semantic state tokens (`error`, `warning`, `destructive`, `success`) are intentionally mapped to monochrome grey values. **Do not replace them with conventional red/green/yellow** — this is a deliberate design choice for this tool."
- `docs/superpowers/plans/2026-07-06-resumetailor-build.md:15-24` — "`planning/PLAN.md` is the authoritative spec — **no agent invents endpoints, tables, or UI not in it**"; "Single Docker container, port 8000 only"; "**No auth — single user, `user_id` always `"default"`**"; "Dark theme only on first load"; "No texlive — rendercv v2.x uses Typst installed as a pip dep"; "All long-running LLM ops use SSE"
- `docs/superpowers/specs/2026-07-06-agent-team-design.md:174` — "**No scope creep:** No agent adds endpoints, UI panels, database tables, or behaviors not specified in PLAN.md."
- `docs/superpowers/plans/2026-07-06-rendercv-config-integration.md:12-18` — "No new environment variables or `Settings` fields"; "Do not modify the Dockerfile"

---

## 2. Spec vs reality matrix

Legend: ✅ implemented · 🟡 partially implemented · ❌ missing · ⚠️ implemented but contradicts the spec

### 2.1 Master resume

| # | Specified feature | Spec ref | Status | Evidence |
|---|---|---|---|---|
| 1 | Guided empty state: instructions, sample YAML download, rendercv.com link | `PLAN.md:37-44` | ✅ | `frontend/src/components/EmptyState.tsx:76-151`; download link `:100-106`; rendercv.com link `:142-149` |
| 2 | "A rendered preview of that sample (like `planning/example-yaml-preview.png`)" on the empty state | `PLAN.md:41` | ❌ | `EmptyState.tsx` renders headline + two CTAs + drop zone + link only. No preview image, no PDF iframe. `planning/example-yaml-preview.png` is never referenced by any frontend file |
| 3 | "Create a new master resume (blank or from sample)" | `PLAN.md:51` | 🟡 | "Start from Sample" implemented (`EmptyState.tsx:97-99` → `WorkstationShell.tsx:26-30`, persists immediately). No "start blank" path — the only way to an empty editor is to load the sample and clear it |
| 4 | Drag-and-drop PDF → AI converts to render-cv YAML | `PLAN.md:44,52` | ✅ | `EmptyState.tsx:56-74` (`handleFile`, `onDrop`), drop zone `:109-122`; backend `backend/app/routes/master_resume.py:127-158` |
| 5 | PDF import reachable once a master resume exists | `PLAN.md:52`, `README.md:29` | 🟡 | Import UI exists **only** in the empty state. `MasterResumePanel.tsx` has no import affordance; the user must delete the master resume (`MasterResumePanel.tsx:90`) to see the drop zone again |
| 6 | Import constraints: PDF only (`application/pdf`), max 10 MB, max 50 pages | `PLAN.md:206` | 🟡 | Content-type checked at the route (`master_resume.py:132-133` → 400). Size and page limits live only in the adapter (`backend/app/adapters.py:109-127`) and surface as **HTTP 422** via `main.py:50-52`, not the spec'd 400 |
| 7 | Paste or edit YAML directly, with syntax highlighting | `PLAN.md:54`, `README.md:26` | ✅ | `MasterResumePanel.tsx:102-110` — CodeMirror 6 with `@codemirror/lang-yaml`, line numbers, dark theme |
| 8 | **Live** preview of the master resume "as they edit" | `PLAN.md:55` | 🟡 | Preview is a PDF iframe that re-fetches only when `previewKey` bumps, and that happens only on save (`MasterResumePanel.tsx:36`; preview at `:117-121` pointing to `/api/master-resume/preview`). Typing changes nothing until Save is clicked. Editor/Split/Preview modes exist (`:71-79`) |
| 9 | "Use the AI chat assistant to create or edit the master resume" | `PLAN.md:56` | ❌ | Chat never writes to the database — see #26. `ChatPanel.tsx:56-58` listens for a `master_resume_updated` action the backend never emits |
| 10 | Master resume history: last 10 versions, pruned, no UI | `PLAN.md:217-225` | ✅ | `backend/db/schema.sql:8-13`; write + prune in `backend/app/database.py:73-85` (`HISTORY_LIMIT`). No UI, as specified |
| 11 | Delete the master resume | `PLAN.md:206` (`DELETE /api/master-resume`) | ✅ | `MasterResumePanel.tsx:44-52,90` (confirm-button); `master_resume.py:102-106` |

### 2.2 Generation

| # | Specified feature | Spec ref | Status | Evidence |
|---|---|---|---|---|
| 12 | Paste a JD → generate a tailored, ATS-optimized resume from the master | `PLAN.md:59` | ✅ | `GenerationPanel.tsx:31-57`; `backend/app/routes/resumes.py:53-146`. Two-pass generate → audit pipeline at `:75-110`, matching `planning/example-Prompt.md` |
| 13 | Generation streams via SSE with progress events | `PLAN.md:275-296` | ✅ | `resumes.py:66,96,112` emit the three PLAN §11 progress strings; client `frontend/src/lib/sse.ts:9-48`, consumed `GenerationPanel.tsx:38-50` |
| 14 | Configure generation rules per section at generation time | `PLAN.md:60,68-73` | ✅ | `GenerationPanel.tsx:110-134` (collapsible numeric grid); persisted via `routes/rules.py:30-34` |
| 15 | Live preview of the generated resume | `PLAN.md:61` | ✅ | `GenerationPanel.tsx:153-159` → `PdfPreview.tsx:54-62` |
| 16 | **"Edit the generated resume directly (post-generation tweaks)"** | `PLAN.md:62` | ❌ | No editor for generated resumes exists anywhere in `frontend/src/components/`. `api.updateResume` (`frontend/src/lib/api.ts:35-40`) has **zero callers**. `ResumeListPanel.tsx` shows a PDF and a download link only |
| 17 | **"Re-render the PDF after edits"** | `PLAN.md:63` | ❌ (backend only) | `POST /api/resumes/{id}/render` implemented (`resumes.py:180-192`); `api.renderResume` (`lib/api.ts:43-44`) has **zero callers** |
| 18 | **"Rename … generated resumes"** | `PLAN.md:64` | ❌ (backend only) | `PATCH /api/resumes/{id}` accepts `name` (`resumes.py:157-165`, `ResumeUpdate` at `:41-44`); no rename control in `ResumeListPanel.tsx` |
| 19 | "…or delete generated resumes" | `PLAN.md:64` | ✅ | `ResumeListPanel.tsx:37-46,103-109`; `resumes.py:195-203` also unlinks the PDF file |
| 20 | "View all generated resumes in a sortable log (by date or by job description)" | `PLAN.md:65` | ✅ | `ResumeListPanel.tsx:57-64` segmented control (`sort-date` / `sort-jd`); `database.py:124-125` maps to `created_at` / `job_description` |
| 21 | Sort **order** ascending/descending | `PLAN.md:203` (`?sort=date\|jd&order=asc\|desc`) | ❌ (frontend) | `ResumeListPanel.tsx:20` — `const [order] = useState<SortOrder>("desc")`: no setter, no control, permanently descending. Backend honors it (`database.py:125`) |
| 22 | Paginated list (`page`, `limit`) | `PLAN.md:203` | 🟡 | Backend paginates correctly (`database.py:116-137` returns `{items,total,page,limit}`). Frontend always requests page 1 / limit 20 (`lib/api.ts:29-32`) and renders no pager — resumes beyond 20 are unreachable in the UI |
| 23 | Generated resume named meaningfully | `PLAN.md:496-499` (mock: `"Mock Resume — Software Engineer"`) | ⚠️ | Actual name is `f"Resume — {body.job_description[:40]}"` (`resumes.py:118`) regardless of mock mode. E2E constants had to be rewritten to `"Resume —"` (`.superpowers/sdd/progress.md:49`) |

### 2.3 Rules, evaluation, chat

| # | Specified feature | Spec ref | Status | Evidence |
|---|---|---|---|---|
| 24 | Rules: max entries per section (education, experience, projects, extracurricular, certifications), max skills, max chars/bullet, max bullets/entry | `PLAN.md:68-72` | ✅ | `database.py:7-20` — 12 seeded defaults across 6 sections covering all four rule families |
| 25 | Rules "applied at generation time as LLM prompt instructions", global defaults | `PLAN.md:68,73` | ✅ | `backend/app/prompts.py:193-203` (`rules_block`) appends "USER-CONFIGURED LIMITS — these override any conflicting counts above"; injected into both passes at `resumes.py:72,77,101` |
| 26 | Rules persist across sessions | `README.md:36` | ✅ | `generation_rules` table with `UNIQUE(user_id, section, rule_key)` (`schema.sql:34-41`); upsert `routes/rules.py:30-34` |
| 27 | Reset rules to defaults | `PLAN.md:253` (`DELETE /api/rules`) | ❌ (frontend) | `routes/rules.py:37-39` works; `api.resetRules` (`lib/api.ts:58`) has **zero callers** |
| 28 | Evaluate **"a master resume or generated resume"** against a JD | `PLAN.md:76` | 🟡 | Backend is generic — takes arbitrary `yaml_content` (`routes/evaluate.py:42-45`). Frontend only ever evaluates the master resume: `EvaluationPanel.tsx:47,59-62`, and the panel is mounted only with `masterResume` (`WorkstationShell.tsx:81`). Generated resumes cannot be evaluated from the UI |
| 29 | Output: ATS match % + critique + side-by-side matched/missing keyword diff | `PLAN.md:77` | ✅ | `EvaluationPanel.tsx:119-155` — score ring `:18-45`, critique card `:130-132`, matched/missing badge columns `:133-154` |
| 30 | **Chat assistant "can perform any workstation action" on the user's behalf** | `PLAN.md:12,80,299-317` | ❌ | `routes/chat.py:39-74` is a plain streaming completion over history. The `done` event is hardcoded: `yield _sse("done", {"result": {"text": full_text, "action": None}})` (`chat.py:65`). No tool/function calling, no structured-action parsing, no database writes, no fallback to the "migrate to LLM function calling" path described at `PLAN.md:315`. **This is the largest single gap — it is one of three stated core principles** |
| 31 | Action types `resume_created`, `master_resume_updated`, `evaluation_complete`, `rules_updated` | `PLAN.md:317` | 🟡 (types only) | Declared in `frontend/src/lib/types.ts:54-57`. Only `master_resume_updated` is handled client-side (`ChatPanel.tsx:56-58`); the backend emits none of the four |
| 32 | README: "Ask it to rewrite a section, add a bullet, or restructure the YAML — changes are applied directly to your master resume" | `README.md:45-46` | ❌ | Same root cause as #30. The README describes behavior that does not exist |
| 33 | Chat history persisted in the database; viewable | `PLAN.md:82,243` | ✅ | `chat.py:34-36` (GET), persistence at `:44` (user) and `:63` (assistant); loaded by `ChatPanel.tsx:20-22` |
| 34 | Clear conversation history | `PLAN.md:247` (`DELETE /api/chat`) | ✅ | `chat.py:77-79`; UI `ChatDrawer.tsx:18-25,35-37` |
| 35 | Chat history capped before sending to the LLM | not specified | ✅ (undocumented addition) | `chat.py:19,53` — `LLM_HISTORY_LIMIT = 30`. Sensible, but an unspecified behavior |
| 36 | **"Users can view, edit, or reset the default system prompt used by the assistant"** | `PLAN.md:83` | ❌ (backend only) | `routes/system_prompt.py:19-34` fully implements GET/PUT/DELETE and the prompt is used at `chat.py:48-49`. `api.getSystemPrompt` / `updateSystemPrompt` / `resetSystemPrompt` (`lib/api.ts:61-69`) have **zero callers** — there is no settings panel, modal, or route in the frontend |

### 2.4 Visual design and shell

| # | Specified feature | Spec ref | Status | Evidence |
|---|---|---|---|---|
| 37 | **Light/dark theme toggle** | `PLAN.md:88` | ❌ | `frontend/src/app/layout.tsx:20` — `<html lang="en" className="dark">`, hardcoded. `next-themes@^0.3.0` is declared in `frontend/package.json:16` but imported nowhere: grep for `next-themes` / `ThemeProvider` across `frontend/src` returns no hits. The wave-1 frontend plan explicitly listed `next-themes` in its tech stack (`wave1-frontend-engineer.md:12`) |
| 38 | Exact monochrome color tokens; error/warning/destructive/success are grey | `PLAN.md:98-129`; `wave1-frontend-engineer.md:24-46` | ⚠️ **contradicts spec** | `frontend/src/app/globals.css:5-38` is a different design system entirely: `--background:#0c0d0f` (spec `#111212`), gold accent `--accent:#d9a84e` (spec `#323434`), and conventional semantics `--success:#5bd087`, `--warning:#f59e5b`, `--error:#f07373`, `--destructive:#f07373` — the exact substitution `PLAN.md:129` forbids. A later "tailor's thread" redesign superseded the spec and no document records the decision |
| 39 | Font: Inter (sans-serif) | `PLAN.md:131` | ⚠️ superseded | `layout.tsx:5-11` loads Inter **plus** Fraunces (display, used for headings via `font-display`) and JetBrains Mono (`--font-mono`, used in the editor and timestamps) |
| 40 | Single-page app, one shell, collapsible panels, no multi-route navigation | `PLAN.md:93,322-324` | ✅ | One route (`frontend/src/app/page.tsx`, 5 lines); `WorkstationShell.tsx:55-90` switches a `View` union (`types.ts:66`) via `Sidebar.tsx:60-92`; chat is a collapsible drawer (`WorkstationShell.tsx:19,83-89`) |
| 41 | Panel areas: chat, editor+preview, generation form, resume log, evaluation | `PLAN.md:324-330` | ✅ | All five present: `ChatDrawer`/`ChatPanel`, `MasterResumePanel`, `GenerationPanel`, `ResumeListPanel`, `EvaluationPanel` |
| 42 | "Desktop-first; **responsive down to tablet**" | `PLAN.md:92` | ❌ | Zero Tailwind breakpoint prefixes in any component — `grep -rc 'sm:\|md:\|lg:\|xl:' frontend/src/components/*.tsx` returns 0 for all ten components (the two hits in `ui/Button.tsx:22-23` are `size` variant keys, not breakpoints). Fixed widths: sidebar 76px (`Sidebar.tsx:62`) + input column 420px (`GenerationPanel.tsx:79`, `EvaluationPanel.tsx:86`) + list 320px (`ResumeListPanel.tsx:69`) + chat 380px (`ChatDrawer.tsx:28`) — the layout cannot fit a tablet viewport |
| 43 | "Smooth animations and progress indicators for long-running operations" | `PLAN.md:89` | ✅ | `ui/Spinner.tsx`; progress text `GenerationPanel.tsx:101-102,165`; animated score ring `EvaluationPanel.tsx:31-37`; `prefers-reduced-motion` guard `globals.css:82-88` |
| 44 | "Professional, data-dense layout" | `PLAN.md:91` | ✅ | Split panes, 12–14px type scale, monospace metadata throughout |
| 45 | PDF preview via `<iframe>` with a blob URL; backend serves `Content-Disposition: inline` | `PLAN.md:329`, `PLAN.md:207` | ✅ | `PdfPreview.tsx:19-31` (fetch → `createObjectURL`), iframe `:54-62`, revoke on unmount `:35-38`; backend `resumes.py:176-177` |
| 46 | `data-testid` on all interactive elements | `agent-team-design.md:112`; `wave1-frontend-engineer.md:21` | 🟡 | Present on most: `empty-state`, `pdf-import-zone`, `yaml-editor`, `save-master-resume`, `job-description`, `generate-button`, `rules-toggle`, `rules-form`, `resume-list`, `resume-list-item`, `resume-name`, `sort-date`, `sort-jd`, `evaluate-button`, `evaluate-result`, `chat-input`, `chat-send`, `chat-message`, `nav-*`. **Missing on the evaluation JD textarea** (`EvaluationPanel.tsx:91-98` has `id="eval-jd"` but no testid) — flagged by the integration tester and never fixed |

### 2.5 Backend architecture

| # | Specified feature | Spec ref | Status | Evidence |
|---|---|---|---|---|
| 47 | Three port protocols + exception hierarchy | `backendAPI_interface.md:44-110,332-350` | ✅ | `backend/app/ports.py` — `LLMPort`, `PDFRenderPort`, `PDFExtractPort`, `BackendError`, `LLMAuthError`, `LLMUnavailableError`, `RenderError`, `PDFExtractError` |
| 48 | `BackendAPI` facade with `complete`/`stream`/`render`/`extract` | `backendAPI_interface.md:196-230` | ✅ | `backend/app/backend_api.py` |
| 49 | `create_real_backend()` factory as the single wiring point | `backendAPI_interface.md:300-313` | ⚠️ | Exists (`backend_api.py:26-34`) but reads `settings.OPENAI_API_KEY`, not `os.environ["OPENROUTER_API_KEY"]` — see §3 |
| 50 | FastAPI DI via `get_backend()`, `LLM_MOCK` swap | `backendAPI_interface.md:316-330` | ✅ (relocated) | Moved to `backend/app/deps.py:7-17` to break a circular import; `main.py:13` re-exports it. Documented only in `.superpowers/sdd/t5-backend-report.md` |
| 51 | Adapters: LiteLLM, rendercv CLI subprocess, PyMuPDF | `backendAPI_interface.md:234-295` | ✅ | `backend/app/adapters.py` — `LiteLLMAdapter:25-65`, `RenderCVAdapter:68-106`, `PyMuPDFAdapter:109-129` |
| 52 | Tier 1 `SimulatedBackendAPI` (`LLM_MOCK=true`) with PLAN §11 constants | `backend_simulator.md:30-160` | ✅ | `backend/app/simulator.py:10-114`; constants `MOCK_CHAT_RESULT`, `MOCK_GENERATION_RESULT_YAML`, `MOCK_EVALUATION_RESULT`, `MOCK_IMPORT_YAML`, `MOCK_GENERATION_PROGRESS` all match PLAN §11 verbatim |
| 53 | Tier 2 `ConfigurableBackendAPI` + per-port simulators for unit tests | `backend_simulator.md:222-330` | ✅ | `backend/tests/helpers/simulator.py`; used by all route tests via `conftest.py` |
| 54 | Two-pass generation (generate → audit), strip `AUDIT_START…AUDIT_END` | `backend_API.md:120-140`; `example-Prompt.md` | ✅ | `resumes.py:75-110`; strip logic `:106-109` |
| 55 | Prompts `GENERATION_SYSTEM_PROMPT` and `CRITIQUE_SYSTEM_PROMPT` from `example-Prompt.md` | `agent-team-design.md:83` | ✅ | `backend/app/prompts.py` carries both verbatim |
| 56 | All `database.py` calls wrapped in `asyncio.to_thread()` | `wave2-backend-api-engineer.md:15` | ✅ | Every route: `chat.py:36,44,47,48,63`, `master_resume.py:90,98,104,115,157`, `resumes.py:50,61,72,119,129,151,159,170,182,189,197,198`, `rules.py:27,32,38`, `system_prompt.py:21,29,34` |
| 57 | Lazy DB init creating tables + seeding defaults | `PLAN.md:186-192` | ✅ | `main.py:20-27` lifespan (migrated off the deprecated `on_event` the T5 report flagged); `database.py:38-50` seeds rules and the system prompt idempotently |
| 58 | YAML normalizer translating LLM YAML → valid rendercv | `README.md:139` | ✅ (heavily extended, uncommitted) | `backend/app/yaml_utils.py`. Working tree adds +219 lines: `_CV_ALLOWED_KEYS` allow-listing `:24-29`, social-network normalization `:31-42`, `phonenumbers`-backed phone validation, date-order fixing, highlight cleaning |

### 2.6 Infrastructure, deployment, testing

| # | Specified feature | Spec ref | Status | Evidence |
|---|---|---|---|---|
| 59 | Multi-stage Dockerfile: Node 20 → Python 3.12 | `PLAN.md:362-380` | ✅ | `Dockerfile:4-13` (stage 1), `:17-24` (stage 2) |
| 60 | **No texlive** — Typst via the rendercv pip dependency | `backend_API.md:206-219`; `resumetailor-build.md:22` | ✅ | `Dockerfile` installs no TeX; `backend/pyproject.toml:9` pins `rendercv[full]>=2.8`. PLAN.md §9's texlive instruction was correctly overridden |
| 61 | uv-managed Python project, `uv sync --frozen` in Docker | `PLAN.md:154,371` | ✅ | `Dockerfile:8,23`; `backend/uv.lock` committed |
| 62 | HEALTHCHECK `GET /api/health`, 30s interval, 60s start period | `PLAN.md:377` | ✅ | `Dockerfile:35-36`; mirrored in `docker-compose.yml:13-19` |
| 63 | Two named volumes `resumedb-data:/app/db`, `resumepdf-data:/app/pdfs` | `PLAN.md:395-402` | ✅ | `docker-compose.yml:8-10,22-24` |
| 64 | FastAPI serves the static Next.js export on the same origin | `PLAN.md:137-146` | ✅ | `Dockerfile:27` copies the export to `backend/static/`; `main.py:68-70` mounts it with `html=True` |
| 65 | Four idempotent start/stop scripts (mac + windows) | `PLAN.md:404-414` | ✅ | `scripts/start_mac.sh`, `stop_mac.sh` (both `0755`), `start_windows.ps1`, `stop_windows.ps1` — **all four undocumented in the README** |
| 66 | `.env.example` committed, `.env` gitignored | `PLAN.md:35,357` | ✅ | `.env.example` present; `git check-ignore .env` → `.gitignore:43` |
| 67 | `docker-compose.test.yml` with app (`LLM_MOCK=true`) + Playwright container | `PLAN.md:458-460` | ✅ | `docker-compose.test.yml:4-40`. Minor: carries an obsolete `version: "3.9"` key at `:2` |
| 68 | All 8 E2E scenarios from PLAN §10 | `PLAN.md:462-471` | ✅ | `test/e2e/01-fresh-start` … `08-rules.spec.ts`, 13 tests total, all reported passing (`t6-tester-report.md:11-26`) |
| 69 | Backend unit tests: routes, LLM, PDF | `PLAN.md:438-442` | ✅ | 89 test functions across 11 files: `test_database.py` (26), `test_llm.py` (15), `test_rendercv_validation.py` (15, **untracked**), `test_yaml_utils.py` (8), route tests (25) |
| 70 | Frontend unit tests: component rendering, editor + preview, list sort, chat states | `PLAN.md:444-449` | 🟡 | Only 3 test files: `__tests__/ChatPanel.test.tsx`, `MasterResumePanel.test.tsx`, `ResumeListPanel.test.tsx`. No tests for `GenerationPanel`, `EvaluationPanel`, `EmptyState`, `PdfPreview`, `Sidebar`, `WorkstationShell`. `npm test` is `jest --passWithNoTests` (`package.json:9`) |
| 71 | Terraform / App Runner deployment (explicit stretch goal) | `PLAN.md:415-418` | ❌ (correct non-goal) | No `deploy/` directory. Correctly out of scope |
| 72 | CI running the three test tiers | not specified | ❌ | No `.github/` directory. All 105 tests run only by hand |

### 2.7 Summary counts

- **Fully implemented:** 40 of 72 tracked items
- **Partially implemented:** 13
- **Missing:** 14 (of which 2 — Terraform, CI — are legitimate non-goals/unspecified)
- **Implemented but contradicting the spec:** 5 (palette, fonts, generated-resume naming, `create_real_backend` provider, rendercv `--locale` handling)

**The four gaps that matter most, in order:**
1. **Chat cannot act** (#30) — one of three stated core principles, fully absent.
2. **No system-prompt UI** (#36) — backend complete, frontend nonexistent.
3. **Generated resumes are read-only in the UI** (#16, #17, #18) — three specified capabilities, all backend-complete and frontend-absent.
4. **No theme toggle and no responsive layout** (#37, #42) — both specified, both absent; `next-themes` was installed and never wired.

---

## 3. Documented API contract vs actual routes

### 3.1 Endpoint inventory

Every endpoint in `PLAN.md` §7 exists, with one addition:

| Documented endpoint | Implemented at |
|---|---|
| `GET /api/health` | `routes/health.py:7-9` |
| `GET /api/master-resume` | `routes/master_resume.py:88-93` |
| `PUT /api/master-resume` | `master_resume.py:96-99` |
| `DELETE /api/master-resume` | `master_resume.py:102-106` |
| `POST /api/master-resume/import` | `master_resume.py:127-158` |
| `GET /api/resumes` | `routes/resumes.py:46-50` |
| `POST /api/resumes/stream` | `resumes.py:53-146` |
| `GET /api/resumes/{id}` | `resumes.py:149-154` |
| `PATCH /api/resumes/{id}` | `resumes.py:157-165` |
| `GET /api/resumes/{id}/pdf` | `resumes.py:168-177` |
| `POST /api/resumes/{id}/render` | `resumes.py:180-192` |
| `DELETE /api/resumes/{id}` | `resumes.py:195-203` |
| `GET /api/chat` | `routes/chat.py:34-36` |
| `POST /api/chat/stream` | `chat.py:39-74` |
| `DELETE /api/chat` | `chat.py:77-79` |
| `GET/PUT/DELETE /api/rules` | `routes/rules.py:25-39` |
| `GET/PUT/DELETE /api/system-prompt` | `routes/system_prompt.py:19-34` |
| `POST /api/evaluate/stream` | `routes/evaluate.py:51-73` |
| *(undocumented)* | **`GET /api/master-resume/preview`** — `master_resume.py:109-124` |

### 3.2 Drift list

| # | Drift | Documented | Actual | Severity |
|---|---|---|---|---|
| D1 | **LLM provider inverted** | `OPENROUTER_API_KEY`; model `openrouter/openai/gpt-oss-120b:free`; `create_real_backend()` reads `os.environ["OPENROUTER_API_KEY"]` — `PLAN.md:165-174`, `backendAPI_interface.md:300-313`, and the whole of `backend_API.md:24-44` | `OPENAI_API_KEY`, default model `gpt-4o-mini` — `backend/app/config.py:8-9`; `adapters.py:28` sets `os.environ["OPENAI_API_KEY"]`; `backend_api.py:31`; `.env.example:5-11`; `docker-compose.test.yml:15-17`. README documents the OpenAI form (`README.md:110-118`) | **High** — `planning/backend_API.md` and `backendAPI_interface.md` give a new contributor the wrong setup end-to-end |
| D2 | **Undocumented endpoint** | — | `GET /api/master-resume/preview` (`master_resume.py:109-124`). Added during final review because its absence caused "a silent UI hang" (`.superpowers/sdd/progress.md:47-48`). Absent from PLAN §7, `backendAPI_interface.md`, and README | Medium |
| D3 | **Error body shape** | `{ "error": "Human-readable message", "code": "MACHINE_READABLE_CODE" }` for **all** non-2xx — `PLAN.md:319-336` | Only the four port-exception handlers use that shape (`main.py:35-52`). Every `HTTPException` returns FastAPI's default `{"detail": "..."}`: `master_resume.py:92,106,117,122,133`, `resumes.py:153,164,172,175,184`, `system_prompt.py:23` | **High** — the frontend compensates ad hoc: `lib/api.ts:9-11` reads `body.error`; `PdfPreview.tsx:23` reads `body?.detail ?? body?.error`. Two shapes coexist and neither doc says so |
| D4 | **422 for invalid YAML** | "422 \| Malformed YAML that fails render-cv validation" — `PLAN.md:333` | `RenderError` maps to **500** globally (`main.py:45-47`). Only `/api/master-resume/preview` catches it and re-raises 422 (`master_resume.py:121-122`). `POST /api/resumes/{id}/render` therefore returns **500** for invalid YAML (`resumes.py:185`) | Medium |
| D5 | **400 for oversized / too-long PDF** | "400 \| Invalid request body or parameters"; constraints stated at `PLAN.md:206` | `PDFExtractError` → **422** (`main.py:50-52`); the adapter raises it for >10 MB and >50 pages (`adapters.py:114-127`) | Low |
| D6 | **Chat `done` payload** | `result` "may include an optional `action` field alongside the assistant's text"; four supported action types — `PLAN.md:301-317` | Always `{"text": ..., "action": None}` (`chat.py:65`) | **High** (= feature gap #30) |
| D7 | **Mock generation payload** | `name: "Mock Resume — Software Engineer"`, `pdf_path: "mock.pdf"` — `PLAN.md:496-501` | Name `f"Resume — {jd[:40]}"` (`resumes.py:118`); `pdf_path` `{id}.pdf` (`resumes.py:130,190`). `mock.pdf` is only the fixture bytes the simulator returns (`simulator.py:6,103-104`) | Medium — forced an E2E constant rewrite (`progress.md:49`) |
| D8 | **`token` events** | The event vocabulary (`progress`/`token`/`done`/`error`) is presented as common to all SSE routes — `PLAN.md:281-291` | `token` is emitted only by chat (`chat.py:60`). Generation and evaluation emit `progress`/`done`/`error` only (`resumes.py:66,96,112,133`; `evaluate.py:55,64`) | Low |
| D9 | **rendercv CLI flags** | `--pdf-path --dont-generate-markdown --dont-generate-html --dont-generate-png --dont-generate-typst --quiet` — `backend_API.md:243-252`, `backendAPI_interface.md:237-249` | `--design <path> --pdf-path --dont-generate-markdown --dont-generate-html --dont-generate-png` (`adapters.py:86-94`). No `--quiet`, no `--dont-generate-typst`; `--design` added by the config-integration work | Medium |
| D10 | **`--locale` flag** | "Add `"--design", str(_CONFIG_DIR / "design.yaml")` **and `"--locale", str(_CONFIG_DIR / "locale.yaml")`** to the subprocess args" — `docs/superpowers/specs/2026-07-06-rendercv-config-integration-design.md:24`; repeated in the plan | `--locale` is **not passed**. Locale YAML is parsed and merged into the document instead (`adapters.py:76-84`), per commit `3b50be8` "fix: embed locale content in YAML instead of passing --locale file path". The approved design doc was never updated | Medium — an *approved* spec that the code contradicts |
| D11 | **LiteLLM error mapping** | `AuthenticationError → HTTP 500 (internal config error)`; `RateLimitError`/`ServiceUnavailableError`/`APIConnectionError → 503` — `backend_API.md:150-180` | Matches (`main.py:35-42`, `adapters.py:41-44,56-59`), but every message and example in the doc names OpenRouter | Low |
| D12 | **`ContextWindowExceededError` → 400** | `backend_API.md:176-179` | Not handled anywhere; falls through to the generic `except Exception` in each SSE generator (`resumes.py:142-143`, `chat.py:70-71`, `evaluate.py:69-70`) and surfaces as `GENERATION_FAILED`/`CHAT_FAILED`/`EVALUATION_FAILED` | Low |
| D13 | **`BackendAPI` DI location** | `get_backend()` defined in `main.py` — `backendAPI_interface.md:316-330` | Defined in `deps.py:7-17`, re-exported by `main.py:13` to break a routes→main circular import | Low (accurate in `t5-backend-report.md` only) |
| D14 | **Facade + simulator shapes** | `backendAPI_interface.md:196-230`; `backend_simulator.md` Tier 1/Tier 2 locations | Match exactly | None — these docs are still accurate |

### 3.3 Implemented-but-unused routes

Endpoints with zero frontend callers (dead surface area from the UI's perspective):

- `PATCH /api/resumes/{id}` — `api.updateResume` unused
- `POST /api/resumes/{id}/render` — `api.renderResume` unused
- `GET /api/resumes/{id}` — `api.getResume` unused
- `GET /api/system-prompt`, `PUT /api/system-prompt`, `DELETE /api/system-prompt` — all three unused
- `DELETE /api/rules` — `api.resetRules` unused

---

## 4. Deferred / TODO work

### 4.1 Source-code markers

`grep -rn 'TODO\|FIXME\|HACK\|XXX' backend/app frontend/src backend/tests test/e2e test/fixtures` returns **zero hits**. The codebase carries no inline debt markers — all known outstanding work lives in the agent reports below, which is itself a documentation problem (§5).

### 4.2 Deferred items from prior agent reports

| Item | Source | Still open? | Evidence |
|---|---|---|---|
| **T3 Frontend Engineer report never written** — the file is a 2-line stub | `.superpowers/sdd/t3-frontend-report.md:1-2` ("`# T3 Frontend Engineer — Report` / `(implementer fills this in)`") | **Yes** | No record exists of frontend design decisions or deviations — including the palette reversal (#38) and the dropped theme toggle (#37) |
| `data-testid="evaluate-jd"` on the EvaluationPanel textarea | `t6-tester-report.md:73-76` — "Add `data-testid="evaluate-jd"` … so tests can target it unambiguously without relying on placeholder text" | **Yes** | `EvaluationPanel.tsx:91-98` still has only `id="eval-jd"`; `test/e2e/07-evaluation.spec.ts` still selects by placeholder |
| `SimulatedBackendAPI.complete()` import branch "is fragile if future endpoints also use `response_format`" | `t6-tester-report.md:78-81` | **Yes** | `simulator.py:92-95` still discriminates on the mere presence of `response_format` |
| `PDFExtractError` dead-code branch in the generation stream | `progress.md:35` | **Yes** | `resumes.py:140-141` — the generation path never extracts PDFs, so the handler is unreachable |
| `AUDIT_END` stripping untested | `progress.md:35` | **Yes** | No test in `test_routes_resumes.py` exercises `resumes.py:106-109` |
| `stream()` raises on iteration rather than on await; the fake LLM test does not validate the await convention | `progress.md:21` | **Yes** | `adapters.py:46-65` — `_gen()` wrapper defers the raise |
| `MOCK_CHAT_RESPONSE` unused; scenario 6 seeding is "best-effort" | `progress.md:41` | **Yes** | `test/e2e/06-resume-list-sort.spec.ts` |
| `*.egg-info/` missing from `.gitignore` | `progress.md:31` | **Yes** | `.gitignore` |
| `settings.yaml` trailing whitespace in `typst_path`; missing final newline | `progress.md:59` | **Yes** | `backend/rendercv_config/settings.yaml` |
| `list_resumes` omits `yaml_content` | `progress.md:16-17` — judged an "intentional list-view optimization, not a defect" | By design | `database.py:132-133`; `types.ts:13` marks `yaml_content?` optional |
| Chat drawer toggle has no testid | `progress.md:26` | **Closed** | `Sidebar.tsx:87` now sets `data-testid="nav-chat"` |
| `yaml-editor` testid matches two elements in the mock | `progress.md:26` | Partially | `MasterResumePanel.tsx:99` puts it on the wrapper div; CodeMirror nests inside |
| `on_event` deprecation warnings (FastAPI 0.111+) | `t5-backend-report.md` "Key Decisions" | **Closed** | `main.py:20-30` now uses a `lifespan` context manager |
| Port 8000 occupied by another local process; tests were run on 8080 | `t6-tester-report.md:56-60` | Environmental | Matches the recorded E2E gotcha; `docker-compose.test.yml:7` still maps 8000:8000 |
| Reports used `python -m pytest` instead of `uv run pytest` | `progress.md:59` | Cosmetic | — |

### 4.3 Uncommitted / untracked work in the tree

Not covered by any plan, spec, or report:

| Path | State | Notes |
|---|---|---|
| `backend/app/yaml_utils.py` | Modified, **+219 lines** | Adds `_CV_ALLOWED_KEYS` allow-listing (`:24-29`), `_VALID_NETWORKS`/`_NETWORK_ALIASES` social normalization (`:31-42`), `phonenumbers`-based phone validation replacing the old 10/11-digit format check, `_fix_date_order`, `_clean_highlights`. Substantial behavior change with no design record |
| `backend/tests/test_rendercv_validation.py` | **Untracked**, 15 tests | Docstring: "Each test reproduces a real failure observed when feeding LLM-generated YAML to `rendercv render`". Valuable regression suite sitting outside version control |
| `planning/master-resume.yaml` | **Untracked** | **Contains real personal data** — full name, university email, phone number, home city, personal website, LinkedIn/GitHub handles. `planning/` is not gitignored, so a `git add -A` would commit it |
| `backend/app/routes/master_resume.py` | Modified, +1 line | Prompt rule at `:76` — "Omit phone entirely if no phone number appears in the source — never invent one" |
| `docker-compose.yml` | Modified, −2 lines | — |
| `.gitignore` | Modified, +5 lines | Adds `.agents/`, `skills-lock.json`, `.claude/skills/` |
| `.claude/settings.json` | Modified | Harness config |

**Undeclared dependency:** `yaml_utils.py` now imports `phonenumbers`, which is **not listed** in `backend/pyproject.toml:5-13`. It resolves only as a transitive dependency of `rendercv[full]`. If rendercv ever drops it, the normalizer breaks at import time.

---

## 5. Documentation quality

### 5.1 What a new contributor *can* learn today

From `README.md` alone: what the product does (with eight screenshots), the tech stack per layer, a three-command Docker quick start, the five environment variables and their defaults, a block-diagram of the container, and the commands to run backend and E2E tests. For a personal project that is already above average.

### 5.2 What they cannot learn from any current document

1. **Local development is under-specified and partly misleading.** `README.md:80-88` instructs `npm run build` then `cp -r out ../backend/static`, but the Next config uses `distDir: 'out'` (set during the T3 fixes, `progress.md:23`) and the Dockerfile copies from `/build/frontend/out` (`Dockerfile:27`). The interaction between `distDir` and the export output directory is documented nowhere and is easy to get wrong. `npm run dev` on port 3000 is never mentioned — a contributor who tries it gets 404s on every `/api/*` call with no explanation. **The four `scripts/` entry points are absent from the README entirely**, despite `PLAN.md:404-414` treating them as the primary launch path.

2. **Architecture beyond the ASCII box.** Nothing user-facing documents the ports/adapters/facade design: `ports.py` (protocols + exceptions) → `adapters.py` (real implementations) → `backend_api.py` (facade) → `deps.py` (DI with `LLM_MOCK` swap). Nor why `deps.py` exists at all (circular-import break — recorded only in `t5-backend-report.md`). Nor the two simulator tiers. Nor the `asyncio.to_thread()` convention that wraps every synchronous sqlite call. The nearest thing is `planning/backendAPI_interface.md`, which is stale on the provider and on the DI location.

3. **The data model exists only inside `PLAN.md:196-215`.** No document explains that `master_resume` holds one row per user, that `pdf_path` stores a bare filename resolved against `PDFS_DIR` (`resumes.py:173,186`), that generation rules are `(section, rule_key, rule_value)` triples seeded at `database.py:7-20`, or that history pruning fires on every save.

4. **The YAML normalizer is invisible.** `yaml_utils.py` is the highest-risk file in the repo — it is the sole translation layer between non-deterministic LLM output and rendercv's pydantic schema — and it is the most actively edited (it accounts for the entire uncommitted diff). The README gives it a single clause (`README.md:139`). Its contract — which `cv:` keys survive, which phone numbers get dropped and why, how loose dates are coerced, which social networks are recognized — exists only in code and in an untracked test file.

5. **The prompt / generation pipeline.** The two-pass generate→audit flow, the `AUDIT_START`/`AUDIT_END` stripping contract, how generation rules are injected as a system-prompt suffix (`prompts.py:193-203`), the import prompt's schema block (`master_resume.py:20-77`), and the evaluation JSON schema (`evaluate.py:22-39`) are documented nowhere outside `planning/example-Prompt.md` — which shows the prompts but not the pipeline that uses them.

6. **Deployment and operations.** No guidance on backups (the SQLite file plus the PDF directory are the *only* state), volume migration, where logs go, why `--workers 1` (`Dockerfile:41`), expected image size, or recovery when `rendercv` fails to render. No troubleshooting section at all — notably missing: "port 8000 already in use" (a known recurring failure), "preview renders blank", "the LLM returned YAML that won't validate".

7. **No repository hygiene documents.** No `CONTRIBUTING.md`, `LICENSE`, `CHANGELOG.md`, ADRs, or `.github/` directory. The 89 backend tests, 3 frontend test files, and 13 E2E tests are run entirely by hand; nothing prevents a regression from landing.

8. **No record of why the UI diverged from the spec.** The gold "tailor's thread" palette, the three-font stack, the sidebar navigation model, and the dropped theme toggle are all live in code and contradicted by `PLAN.md` §2 — with the empty T3 report as the only place such a decision would have been captured.

### 5.3 Stale or misleading documents, ranked

| Doc | Lines | Verdict |
|---|---|---|
| `planning/backend_API.md` | 423 | **Rewrite or archive.** Every section is OpenRouter-specific while the shipped stack is OpenAI-compatible LiteLLM (D1). Its rendercv CLI flags no longer match `adapters.py` (D9). Its one durable contribution — "**These are wrong for render-cv v2.x**… The PDF is compiled by the `typst` compiler, not LaTeX" (`:206-219`), which correctly overrode `PLAN.md:366-368` — belongs in an ADR |
| `planning/backendAPI_interface.md` | 414 | **Archive.** The design it specifies was built faithfully, so the doc has served its purpose; but `create_real_backend()` (`:300-313`) is now wrong on the provider and the DI example (`:316-330`) is wrong on location |
| `planning/PLAN.md` | 475 | **Stale on three fronts, yet still the only product spec that exists.** §2 palette and font contradict shipped CSS; §7 omits `/api/master-resume/preview`; §11 mock payloads no longer match the simulator's observable output. Needs rewriting into a product spec, not deletion — everything in §1 of this report comes from it |
| `docs/superpowers/specs/2026-07-06-rendercv-config-integration-design.md` | 39 | **Stale.** Marked "Status: Approved", yet its `--locale` decision was reversed in implementation (D10) with no update |
| `docs/superpowers/plans/*.md` (7 files) | 4,192 | **Archive.** Step-by-step instructions for a build that completed. `wave1-frontend-engineer.md:24-46` actively misleads — it restates the monochrome tokens as "exact — do not change" |
| `.superpowers/sdd/*` (24 files) | ~1,100 md + 13 `.diff` + 5 `.txt` | **Harvest, then archive/delete.** Build-process exhaust. The `.diff` and review `.txt` blobs duplicate git history and should go. But `progress.md` and the six `t*-report.md` files are the **only** record of the ~13 known-minor issues in §4.2 — extract those into an issue tracker first |
| `.claude/commands/agents/reviewer.md` | 6 | **Broken.** Targets `plannin/PLAN.md` (typo for `planning/`) and writes to `planning/REVIEW.md`, which does not exist |
| `.claude/commands/doc-review.md` | 1 | Functional but thin — a single unpunctuated sentence scoped to `planning/`, the directory about to be archived |
| `README.md` | 141 | Mostly accurate. Three problems: overstates chat (`:45-46`, "changes are applied directly to your master resume" — see #30/#32), omits `scripts/` entirely, and implies rename/edit/re-render are usable when they are backend-only |
| `planning/example-Prompt.md` | 189 | **Live content, wrong location.** `prompts.py` carries both prompts verbatim; this is effectively source, not planning |
| `planning/backend_simulator.md` | 492 | **Accurate.** Describes what was built. Belongs in a testing doc rather than `planning/` |
| `docs/screenshots/*` (8 PNGs) | — | Current and genuinely useful; keep |

---

## 6. Multi-user / auth story

### 6.1 Documented intent

- `PLAN.md:27` — "A browser opens to `http://localhost:8000`. **No login, no signup.**"
- `PLAN.md:29-33` — "The API key is injected via environment variable and **never sent from the browser or stored in the database**. It is only used server-side."
- `PLAN.md:151` — "SQLite over Postgres | **No auth = no multi-user** = no need for a database server; self-contained, zero config"
- `PLAN.md:194` — "All tables include a `user_id` column defaulting to `"default"`. This is **hardcoded for now (single-user) but enables future multi-user support without a schema migration**."
- `resumetailor-build.md:18` — restated as a hard build constraint: "**No auth — single user, `user_id` always `"default"`**"

### 6.2 Implementation

Exactly as specified, with one deliberate seam and one forward-compatibility gap.

**Constant and defaults.** `backend/app/database.py:4` — `DEFAULT_USER_ID = "default"`.

**Data layer is genuinely parameterized.** Every database function takes `user_id: str = DEFAULT_USER_ID` as a keyword-default and filters on it:

- `get_master_resume` `:57-62`; `upsert_master_resume` `:68-100` (including history insert `:77-78` and prune `:81-85`, both scoped by `user_id`); `delete_master_resume` `:104-108`
- `list_resumes` `:116-137` (count and page both filtered); `create_resume` `:146-153`; `get_resume` `:162-168`; `update_resume` `:179-202`; `delete_resume` `:208-213`
- `get_chat_messages` `:221-227`; `add_chat_message` `:233-…`; `clear_chat`
- `get_rules`, `upsert_rules`, `reset_rules`; `get_system_prompt`, `upsert_system_prompt`, `reset_system_prompt`
- Seeding is scoped too: `init_db` checks `WHERE user_id = ?` before inserting defaults (`:38-50`)

**Schema is forward-compatible.** All six tables declare `user_id TEXT NOT NULL DEFAULT 'default'` (`backend/db/schema.sql:3,9,17,27,35,44`), and `generation_rules` is uniquely keyed on `UNIQUE(user_id, section, rule_key)` (`:40`) — the only table where multi-tenancy would otherwise collide.

**Transport layer has no identity at all.** **No route ever passes `user_id`** — every call site relies on the default: `chat.py:36,44,47,48,63`; `master_resume.py:90,98,104,115,157`; `resumes.py:50,61,72,119,129,151,159,170,182,189,197,198`; `rules.py:27,33,38`; `system_prompt.py:21,29,34`. There is no session, cookie, header, token, or `Depends(get_current_user)` anywhere in `backend/app/`.

**`user_id` leaks into the client as a vestigial field.** `frontend/src/lib/types.ts:3,10,28,43` carry it on four interfaces, and `ChatPanel.tsx:36,50` hardcodes `user_id: "default"` when constructing optimistic messages. Harmless, but it is client-side state that means nothing.

### 6.3 Assessment

The *data layer* is one threaded parameter away from multi-tenancy — genuinely good forward planning, exactly as `PLAN.md:194` promised. The *transport layer* has no concept of identity, which is correct for the stated scope.

Two caveats worth recording that no document currently states:

1. **PDF storage is not forward-compatible.** Generated PDFs are written flat as `{PDFS_DIR}/{resume_id}.pdf` (`resumes.py:125-127,186-188`) and read back the same way (`resumes.py:173`). There is **no `user_id` in the path**. Unlike the schema, the filesystem layout *would* require migration to support multiple users.

2. **Zero-auth becomes a real vulnerability the moment the container is exposed.** `GET /api/resumes/{id}/pdf` (`resumes.py:168-177`) serves any resume PDF to any caller who can reach port 8000; `PUT /api/master-resume` lets any caller overwrite the resume; `DELETE /api/chat` lets any caller wipe history. This is entirely appropriate for a localhost single-user tool and entirely inappropriate for the "deploy to AWS App Runner, Render, or any container platform" aspiration at `PLAN.md:415-418`. That tension is undocumented and should be stated explicitly in a deployment document.

---

## 7. Recommended documentation structure

### 7.1 Target tree

```
README.md                    # what it is, screenshots, 3-command quick start, doc index. Nothing else.
ARCHITECTURE.md              # the mental model a contributor needs before reading code
CONTRIBUTING.md              # how to run it, test it, and change it safely
LICENSE
docs/
├── API.md                   # endpoint reference, generated from OpenAPI + hand-annotated SSE flows
├── DATA_MODEL.md            # schema, record lifecycles, storage layout
├── AI_PIPELINE.md           # prompts, two-pass flow, rules injection, the YAML normalizer contract
├── DEPLOYMENT.md            # Docker, volumes, backup/restore, scripts/, the no-auth exposure warning
├── TROUBLESHOOTING.md       # the failure modes that actually happen
├── adr/
│   ├── 0001-single-container-sqlite-no-auth.md
│   ├── 0002-rendercv-typst-not-latex.md
│   ├── 0003-ports-adapters-facade-and-two-tier-simulator.md
│   ├── 0004-openai-compatible-litellm-not-openrouter.md
│   ├── 0005-gold-accent-redesign-supersedes-monochrome-palette.md
│   └── 0006-rendercv-locale-embedded-not-cli-flag.md
├── screenshots/             # unchanged
└── archive/                 # frozen; each file gets a "historical, do not trust" banner
    ├── planning/
    └── superpowers/
.github/
└── workflows/ci.yml         # pytest + jest + playwright against the LLM_MOCK container
```

### 7.2 What belongs in each document

**`README.md`** — product pitch, the eight screenshots (already strong), `cp .env.example .env` → `docker compose up --build` → `localhost:8000`, the environment-variable table, and a "Documentation" index linking everything below. **Remove** the Development Setup and Architecture sections (they move to `CONTRIBUTING.md` and `ARCHITECTURE.md`). **Fix** the chat description at `:45-46` to say what chat does today (a context-aware assistant over your resume) rather than what it was specified to do. **Add** a one-line pointer to `scripts/start_mac.sh` / `start_windows.ps1`.

**`ARCHITECTURE.md`** — container and port topology; the request path (static export → same-origin `/api/*` → route → `BackendAPI` facade → port protocol → adapter); why `deps.py` exists and how `LLM_MOCK` swaps the whole backend; the `asyncio.to_thread()` convention over synchronous sqlite; the SSE event vocabulary with a table of which routes emit which events (correcting D8); the two simulator tiers and when to use each; the frontend model (one route, `WorkstationShell` + the `View` union, no router, drawer-based chat). Absorbs the accurate content of `planning/backendAPI_interface.md` and `planning/backend_simulator.md`.

**`CONTRIBUTING.md`** — prerequisites (Python 3.12 + uv, Node 20, Docker); the backend dev loop (`uv sync`; `LLM_MOCK=true DB_PATH=… PDFS_DIR=… uv run uvicorn app.main:app --reload`); the frontend build/copy dance **with `distDir: 'out'` explained** so the README's current instruction stops being a trap; `uv run pytest`, `npm test`, `npx playwright test` plus the port-8000 caveat; commit message conventions; and the two house rules the test suites depend on — *every interactive element gets a `data-testid`*, and *every database call goes through `asyncio.to_thread()`*.

**`docs/API.md`** — one section per endpoint with request/response shapes, generated from the live OpenAPI schema (`/openapi.json`) so it cannot drift, hand-annotated with the SSE event sequences OpenAPI cannot express. **Must document the two coexisting error shapes** (`{error, code}` from port handlers vs `{detail}` from `HTTPException`) — or better, first normalize them by registering an `HTTPException` handler in `main.py` that emits `{error, code}`, then document the single shape. Must include `/api/master-resume/preview` (D2).

**`docs/DATA_MODEL.md`** — the six tables with column semantics; the one-row-per-user pattern for `master_resume` and `system_prompt`; history write-and-prune behavior; the `pdf_path`-is-a-bare-filename convention and how `PDFS_DIR` resolves it; the rules triple format and the seeded defaults; **and the `user_id` forward-compatibility note including the PDF-path caveat from §6.3**.

**`docs/AI_PIPELINE.md`** — the generate→audit two-pass flow with the `AUDIT_START`/`AUDIT_END` contract; how `rules_block()` mutates the system prompt and why rules are prompt-level rather than post-processing; the PDF-import prompt and its schema block; the evaluation JSON schema; and — most valuable — the `normalize_to_rendercv()` contract: which `cv:` keys survive, how dates are coerced, why invalid phone numbers are dropped rather than passed through, how social networks are canonicalized. `planning/example-Prompt.md` folds in here (or moves beside `prompts.py` as source). This is the document that saves the next contributor the most time.

**`docs/DEPLOYMENT.md`** — image build and size; both named volumes and what each holds; `scripts/start_mac.sh` / `stop_mac.sh` / the PowerShell equivalents and their idempotence guarantees; backup = copy `resumedb-data` + `resumepdf-data`; health-check semantics and the 60s start period; the `--workers 1` rationale; and an explicit, prominent **"this application has no authentication — anyone who can reach the port can read, overwrite, and delete all data. Do not expose it to a network."**

**`docs/TROUBLESHOOTING.md`** — port 8000 already in use (the known recurring one); preview renders blank or errors; `rendercv` validation failures and how the normalizer absorbs them; phone numbers silently dropped; LLM 401 vs 429 symptoms and which HTTP code each surfaces as; what `LLM_MOCK=true` guarantees and what it does not.

**`docs/adr/`** — short, dated, immutable records. Six are already *earned* by decisions that were taken in code and never written down, and they map one-to-one onto the drifts catalogued in §3:

- **0001** single container + SQLite + no auth (from `PLAN.md:148-158`) — the foundational trade-off
- **0002** rendercv v2.x uses Typst, not LaTeX; PLAN.md §9's texlive list is wrong (rescues the one durable insight in `backend_API.md:206-219`)
- **0003** ports/adapters/facade + two-tier simulator, and why `deps.py` exists
- **0004** OpenAI-compatible LiteLLM, not OpenRouter (D1) — the highest-value ADR, because two planning docs still assert the opposite
- **0005** the gold "tailor's thread" redesign supersedes the monochrome palette and the Inter-only font rule (#38, #39) — so the next reader stops treating `PLAN.md:98-131` as binding
- **0006** rendercv locale is embedded in the document, not passed as `--locale` (D10) — supersedes an "Approved" spec

### 7.3 Disposition of the existing trees

**`planning/`** → move to `docs/archive/planning/`, each file prefixed with a banner: *"Historical build-time specification, superseded by `docs/`. Retained for provenance; do not rely on it."* Three exceptions:

- `example-Prompt.md` is **live content** — move to `docs/AI_PIPELINE.md` or beside `backend/app/prompts.py`.
- `PLAN.md` should be **rewritten** into a current product spec before archiving the original — it is the only document that states what the product is meant to be, and §1 of this report is drawn entirely from it.
- **`planning/master-resume.yaml` must not be committed.** It holds real personal data (name, email, phone, address) and `planning/` is not gitignored. Add it (or `planning/*.yaml`) to `.gitignore`, or move it out of the repository.

**`docs/superpowers/` and `.superpowers/sdd/`** → `docs/archive/superpowers/`. Delete the 13 `review-*.diff` blobs and 5 `review-*.txt` files outright — they duplicate git history. **Before archiving, harvest `progress.md` and the six `t*-report.md` files into a real issue tracker**: the ~13 "minor noted" items in §4.2 have no other home, and archiving them unread loses them.

**`.claude/commands/`** — fix `agents/reviewer.md` (the `plannin/` typo, and retarget away from the nonexistent `planning/REVIEW.md`) or delete it; retarget `doc-review.md` from `planning/` to `docs/`.

**Add `.github/workflows/ci.yml`** running `uv run pytest`, `npm test`, and the Playwright suite against the `LLM_MOCK=true` container. The documentation claims three tiers of testing; today nothing enforces any of them, and the strongest new test file in the repo (`backend/tests/test_rendercv_validation.py`) is not even tracked.
