# ResumeTailor - An AI Resume Tailoring Workstation

## Project Specification

## 1. Vision

ResumeTailor is an AI-powered workstation for job seekers. Users maintain a single **master resume** in render-cv YAML format, then generate tailored, ATS-optimized resumes for specific job descriptions — all without leaving the browser.

- **Master resume first:** one source of truth in render-cv YAML; all generated resumes derive from it
- **AI-assisted everywhere:** an LLM chat assistant can perform any workstation action on the user's behalf
- **Built by agents:** personal project built entirely by AI coding agents demonstrating orchestrated, production-quality full-stack development

**Core principles:**
- Everything through the workstation
- Simple, clean, easy to understand code — no over-engineering

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup.

**API key setup:** Users add their OpenRouter API key to a `.env` file before starting the container. The API key is injected via environment variable and never sent from the browser or stored in the database. It is only used server-side to authenticate with OpenRouter. A `.env.example` file is committed to the repo with setup instructions.

On first launch (no master resume yet), the user sees a guided empty state:
- Instructions for creating a master resume
- A sample `master-resume.yaml` file to download as a starting point
- A rendered preview of that sample (like `planning/example-yaml-preview.png`)
- A link to rendercv.com
- Option to drag-and-drop an existing PDF resume for AI-powered conversion to YAML

### What Users Can Do

**Master Resume**
- Create a new master resume (blank or from sample)
- Upload an existing PDF resume → AI extracts and converts it to render-cv YAML
- Paste or edit YAML directly in the workstation
- Live preview of the master resume as they edit
- Use the AI chat assistant to create or edit the master resume

**Resume Generation**
- Paste a job description and generate a tailored, ATS-optimized resume from the master resume
- Configure generation rules per section (see Rules below)
- View a live preview of the generated resume
- Edit the generated resume directly (post-generation tweaks)
- Re-render the PDF after edits
- Rename or delete generated resumes
- View all generated resumes in a sortable log (by date or by job description)

**Generation Rules** *(applied at generation time as LLM prompt instructions)*
- Max entries per section (education, experience, projects, extracurricular, certifications)
- Max entries in the skills section
- Max characters per bullet point (to keep each point to one line)
- Max bullet points per experience / project / extracurricular entry
- Rules are global defaults (not per-job-description), but some rules are specified per resume section (e.g., max entries for education vs. experience can differ)

**Evaluation**
- Score a master resume or generated resume against a job description
- Output: ATS keyword match percentage + qualitative LLM critique of gaps and suggestions + side-by-side keyword diff highlighting missing and matched terms

**AI Chat Assistant**
- Conversational assistant that can perform any workstation action (create/edit resume, generate, evaluate)
- Full conversation history persisted in the database
- Users can view, edit, or reset the default system prompt used by the assistant

### Visual Design

- Light/dark theme toggle
- Smooth animations and progress indicators for long-running operations (PDF generation, AI responses)
- Professional, data-dense layout — every pixel earns its place
- Desktop-first; responsive down to tablet
- Single-page application: one shell layout with collapsible panels, no multi-route navigation

**Color Scheme** *(intentionally monochrome — all semantic state colors use neutral greys)*

| Token | Value |
|-------|-------|
| `background` | `#111212` |
| `foreground` | `#f2f3f3` |
| `card` / `popover` / `surface` / `muted` / `input` | `#191a1a` |
| `border` / `accent` | `#323434` |
| `primary` | `#f2f3f3` |
| `primary-foreground` | `#111212` |
| `primary-hover` | `#e5e6e6` |
| `secondary-foreground` / `accent-foreground` | `#e5e6e6` |
| `muted-foreground` / `error` | `#7d8282` |
| `destructive` / `warning` | `#979b9b` |
| `success` | `#cbcdcd` |
| `ring` | `#f2f3f3` |

**Font:** Inter (sans-serif)

> **Note for agents:** The semantic state tokens (`error`, `warning`, `destructive`, `success`) are intentionally mapped to monochrome grey values. Do not replace them with conventional red/green/yellow — this is a deliberate design choice for this tool.

## 3. Architecture Overview

Single container, single port.

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  └── /*              Static file serving        │
│                      (Next.js export)           │
│                                                 │
│  SQLite database (volume-mounted)               │
│  PDF storage (volume-mounted)                   │
└─────────────────────────────────────────────────┘
```

- **Frontend:** Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend:** FastAPI (Python), managed as a uv project
- **Database:** SQLite, single file at `db/resumedb.db`, volume-mounted for persistence
- **AI integration:** LiteLLM → OpenRouter using `openai/gpt-oss-120b:free` for all LLM tasks (generation, evaluation, chat, PDF import), with structured outputs for task executions
- **PDF generation:** render-cv Python library (`rendercv` pip package), invoked in-process

**Decision Rationale**

| Decision | Rationale |
|----------|-----------|
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | One command to run; no docker-compose complexity for production |
| uv for Python | Fast, modern Python project management; reproducible lockfile |
| render-cv as Python library | In-process invocation; no subprocess overhead, no extra CLI in the Docker image |
| `.env` for API keys | Keys never transit the backend or get stored; standard pattern for self-hosted tools |

## 4. Directory Structure

```
resume-tailoring-platform/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions and initialization logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; resumedb.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

**Key Boundaries**

`frontend/` is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints. Internal structure is up to the Frontend Engineer agent.

`backend/` is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, API routes, and LLM integration. Internal structure is up to the Backend agent.

`backend/db/` contains schema SQL definitions and initialization logic. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.

`db/` at the top level is the runtime volume mount point. The SQLite file (`db/resumedb.db`) is created here by the backend and persists across container restarts via Docker volume.

`planning/` contains project-wide documentation, including this plan. All agents reference files here as the shared contract.

`test/` contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.

`scripts/` contains start/stop scripts that wrap Docker commands.

## 5. Environment Variables

```
# Required: OpenRouter API key for LLM functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# LLM model used for all tasks (generation, evaluation, chat, PDF import)
LLM_MODEL=openai/gpt-oss-120b:free

# Optional: deterministic mock LLM responses (for testing)
LLM_MOCK=false
```

**Behavior**
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via `docker --env-file`)

## 6. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without a schema migration.

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `master_resume` | The user's master resume YAML | `id`, `user_id`, `yaml_content`, `updated_at` |
| `master_resume_history` | Last 10 saved versions of the master resume | `id`, `user_id`, `yaml_content`, `saved_at` |
| `generated_resumes` | Metadata + YAML for each tailored resume | `id`, `user_id`, `name`, `job_description`, `yaml_content`, `pdf_path`, `created_at`, `updated_at` |
| `chat_messages` | Conversation history with LLM | `id`, `user_id`, `role` (user/assistant), `content`, `created_at` |
| `generation_rules` | Per-user generation constraints | `id`, `user_id`, `section`, `rule_key`, `rule_value` |
| `system_prompt` | User-editable LLM system prompt | `id`, `user_id`, `content`, `updated_at` |

**Master resume history:** Each save to `master_resume` also inserts a row into `master_resume_history`. The backend prunes rows for that `user_id` beyond the 10 most recent, keeping recovery possible without unbounded growth. There is no UI for browsing history in v1 — it is a safety net, not a feature.

**PDF storage:** Generated PDFs are written to `/app/pdfs/{id}.pdf` inside the container. This directory is volume-mounted (see Section 9). The `pdf_path` column stores the filename only (e.g., `42.pdf`); the backend resolves the full path as `/app/pdfs/{pdf_path}`.

## 7. API Endpoints

### Health Check
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Returns `200 { "status": "ok" }`. Used by Docker HEALTHCHECK and start scripts. |

### Master Resume
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/master-resume` | Get current user's master resume YAML |
| PUT | `/api/master-resume` | Save/update master resume YAML |
| DELETE | `/api/master-resume` | Delete the master resume |
| POST | `/api/master-resume/import` | Upload a PDF and convert to YAML via LLM. Accepts `multipart/form-data`. Constraints: PDF only (`application/pdf`), max 10 MB, max 50 pages. |

### Generated Resumes
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/resumes` | Paginated list with metadata (`?sort=date\|jd&order=asc\|desc&page=N&limit=N`) |
| POST | `/api/resumes/stream` | Generate a new tailored resume — SSE stream (see Streaming section below) |
| GET | `/api/resumes/{id}` | Full YAML + metadata |
| PATCH | `/api/resumes/{id}` | Update name or YAML content |
| GET | `/api/resumes/{id}/pdf` | Serve PDF inline (`Content-Type: application/pdf`, `Content-Disposition: inline`) |
| POST | `/api/resumes/{id}/render` | Re-render PDF from current YAML |
| DELETE | `/api/resumes/{id}` | Delete resume and PDF file |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chat` | Get conversation history |
| POST | `/api/chat/stream` | Send a message — SSE stream (see Streaming section below) |
| DELETE | `/api/chat` | Clear conversation history |

### Generation Rules
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/rules` | Get current generation rules |
| PUT | `/api/rules` | Update generation rules |
| DELETE | `/api/rules` | Reset rules to defaults |

### System Prompt
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/system-prompt` | Get current system prompt |
| PUT | `/api/system-prompt` | Update system prompt |
| DELETE | `/api/system-prompt` | Reset to default |

### Evaluation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/evaluate/stream` | Score a resume against a job description — SSE stream (see Streaming section below) |

### Streaming (SSE)

All long-running LLM operations use **Server-Sent Events** (`Content-Type: text/event-stream`) via FastAPI `StreamingResponse`. The frontend opens an `EventSource` (or `fetch` with a readable stream) and handles events as they arrive.

**Event shape** (each SSE event is a JSON line):
```
event: progress
data: {"message": "Analyzing job description..."}

event: token
data: {"delta": "Here is your"}

event: done
data: {"result": { ...full response payload... }}

event: error
data: {"error": "...", "code": "..."}
```

- `progress` events carry status strings for display in the UI during non-streaming steps (e.g., PDF rendering).
- `token` events carry incremental text deltas for chat responses.
- `done` carries the full final payload (persisted resume object, evaluation result, or assistant message).
- `error` terminates the stream on failure.

### Chat Assistant — Workstation Actions

The chat assistant can perform workstation actions (generate resume, evaluate, edit master resume) on the user's behalf. The mechanism uses **structured action output** parsed by the frontend:

1. The LLM returns a response where the `done` SSE event's `result` may include an optional `action` field alongside the assistant's text:
   ```json
   {
     "text": "I've generated a tailored resume for you.",
     "action": { "type": "resume_created", "resume_id": 42 }
   }
   ```
2. The frontend inspects `action.type` and triggers the corresponding UI update or API call (e.g., refresh the resume list, open the new resume).
3. If structured output proves insufficient for complex multi-step actions, migrate to LLM function calling (tool use) where the backend executes tool calls before returning the final SSE response.

**Supported action types:** `resume_created`, `master_resume_updated`, `evaluation_complete`, `rules_updated`.

### Error Responses

All non-2xx responses return a consistent JSON body:
```json
{ "error": "Human-readable message", "code": "MACHINE_READABLE_CODE" }
```

| HTTP Status | When |
|-------------|------|
| 400 | Invalid request body or parameters |
| 404 | Resource not found (resume ID, etc.) |
| 422 | Malformed YAML that fails render-cv validation |
| 500 | LLM call failed, PDF rendering failed, or unexpected server error |
| 503 | LLM provider unavailable or rate-limited |

## 8. Frontend Design

### Layout

Single-page application with a persistent shell: header, main content area with collapsible panels, footer. No client-side routing beyond the root. The frontend engineer decides the exact component architecture and panel arrangement.

Panel areas:
- AI chat assistant (persistent, right or bottom)
- Master resume YAML editor + live preview
- Resume generation form (job description input, rules configuration)
- Generated resumes log/list (sortable)
- Evaluation results display

### Technical Notes
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with the custom dark theme defined in Section 2
- On first load with no master resume: show guided empty state with sample YAML, rendered preview, and setup instructions
- **PDF preview:** Display generated PDFs inline using an `<iframe>` with a blob URL (fetch `GET /api/resumes/{id}/pdf`, create `URL.createObjectURL`, set as `iframe.src`). The backend serves PDFs with `Content-Disposition: inline`. The frontend engineer chooses the exact embedding component.
- **SSE handling:** Long-running operations (chat, generate, evaluate) use SSE streams. Use the `EventSource` API or `fetch` with a `ReadableStream`. Show a progress/loading state while the stream is open; update the UI progressively on `token` events; finalize on the `done` event; display an error on the `error` event.

## 9. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build  (produces static export)

Stage 2: Python 3.12 slim
  - Install system dependencies:
      texlive-latex-base, texlive-latex-extra, texlive-fonts-recommended
      (required by rendercv for PDF generation; adds ~500MB to image)
  - Install uv
  - Copy backend/
  - uv sync  (install Python dependencies from lockfile, including rendercv)
  - Copy frontend build output into backend/static/
  - Expose port 8000
  - HEALTHCHECK: GET http://localhost:8000/api/health (interval 30s, start-period 60s)
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```
docker run \
  -v resumedb-data:/app/db \
  -v resumepdf-data:/app/pdfs \
  -p 8000:8000 \
  --env-file .env \
  resumetailor
```

Two named volumes are required:
- `resumedb-data` → `/app/db` — persists the SQLite database file (`resumedb.db`)
- `resumepdf-data` → `/app/pdfs` — persists generated PDF files

Both volumes must be included in all run commands and the `docker-compose.yml`. The start scripts mount both volumes automatically.

### Start/Stop Scripts

`scripts/start_mac.sh` (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

`scripts/stop_mac.sh` (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

`scripts/start_windows.ps1` / `scripts/stop_windows.ps1`: PowerShell equivalents for Windows.

All scripts are idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

## 10. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest):**
- LLM: structured output parsing handles all valid schemas; graceful handling of malformed responses
- API routes: correct status codes, response shapes, error handling
- PDF generation: render-cv integration produces valid PDF output
- PDF import: LLM-based YAML extraction from PDF text produces valid render-cv YAML

**Frontend (React Testing Library or similar):**
- Component rendering with mock data
- Master resume editor and live preview update
- Generated resumes list rendering and sort controls
- Chat message rendering and loading states

### E2E Tests (in `test/`)

**Infrastructure:** A separate `docker-compose.test.yml` in `test/` spins up the app container plus a Playwright container. Browser dependencies stay out of the production image.

**Environment:** Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios:**
- Fresh start: empty state renders, sample YAML and preview are visible
- Master resume: create from sample, edit YAML, confirm live preview updates
- PDF upload: drag-and-drop triggers import, converted YAML appears in editor
- Resume generation: paste a job description, generate, PDF preview renders
- Chat (mocked): send a message, receive a response, action is reflected in UI
- Generated resumes list: sort by date and by job description works correctly
- Evaluation: score and critique are returned and displayed for a resume + JD pair
- Rules: update a rule, regenerate, confirm rule is applied in output

## 11. Mock LLM Responses

When `LLM_MOCK=true`, the backend returns the following deterministic responses for each LLM operation. These are used by E2E tests so assertions have a fixed target.

### Chat (`POST /api/chat/stream`)

SSE stream ending with:
```json
{
  "text": "I understand. Here's what I can help you with: editing your master resume, generating a tailored resume, or evaluating a resume against a job description.",
  "action": null
}
```

### Resume Generation (`POST /api/resumes/stream`)

Progress events: `"Analyzing job description..."`, `"Tailoring content..."`, `"Rendering PDF..."`

Done event `result` — a `generated_resume` object with:
- `name`: `"Mock Resume — Software Engineer"`
- `job_description`: *(echoed from request)*
- `yaml_content`: minimal valid render-cv YAML with one education entry, one experience entry, one skills entry
- `pdf_path`: `"mock.pdf"` (a pre-generated static PDF committed to the test fixtures directory)

### Evaluation (`POST /api/evaluate/stream`)

Done event `result`:
```json
{
  "match_score": 72,
  "critique": "The resume covers most required skills but lacks explicit mention of Kubernetes and CI/CD pipelines listed in the job description.",
  "matched_keywords": ["Python", "REST API", "PostgreSQL"],
  "missing_keywords": ["Kubernetes", "CI/CD", "Docker Compose"]
}
```

### PDF Import (`POST /api/master-resume/import`)

Returns the same minimal valid render-cv YAML as the resume generation mock.
