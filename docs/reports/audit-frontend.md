# Frontend Audit — `resume-tailoring-platform`

Scope: `frontend/` (Next.js 14.2.5 static export + Tailwind 3.4, served by FastAPI), `docs/screenshots/`, `Dockerfile`, `docker-compose.yml`, `backend/app/main.py` + `backend/app/routes/*` (read only for contract comparison). Read-only audit; no files modified.

**Correction to the brief:** `frontend/out` and `backend/static` are **not** committed to git. Both are gitignored (`.gitignore:39` `frontend/out/`, `.gitignore:57` `backend/static/`) and `git ls-files frontend/out` / `git ls-files backend/static` each return 0 entries. They exist only as stale local build artifacts — see P1-11 and the Build/Deploy section.

---

# Findings, ranked

## P0

### P0-1. Unsaved editor edits are silently destroyed by navigation
`MasterResumePanel.tsx:23` holds the YAML buffer in local `useState`:

```tsx
const [yaml, setYaml] = useState(resume.yaml_content);
```

`WorkstationShell.tsx:64-70` conditionally renders the panel:

```tsx
{view === "editor" && (
  <MasterResumePanel resume={masterResume} onSave={setMasterResume} onDelete={handleMasterDeleted} />
)}
```

Clicking Generate / Resumes / Evaluate in the sidebar **unmounts the panel and discards the buffer**. There is no dirty guard, no route guard, no `beforeunload` handler, no draft persistence. The header explicitly shows `· edited` (`MasterResumePanel.tsx:65`) right up to the moment the state is thrown away. Come back to the Editor and your work is gone with no warning and no undo. This is the worst bug in the app.

### P0-2. Every `DELETE` call throws
`api.ts:6-13`:

```ts
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) { ... }
  return res.json() as Promise<T>;   // line 12 — unconditional
}
```

The backend returns **204 No Content** for three endpoints:
- `DELETE /api/master-resume` — `backend/app/routes/master_resume.py:102` (`status_code=204`)
- `DELETE /api/resumes/{resume_id}` — `backend/app/routes/resumes.py:195` (`status_code=204`)
- `DELETE /api/chat` — `backend/app/routes/chat.py:77` (`status_code=204`)

`Response.json()` on an empty body rejects with `SyntaxError: Unexpected end of JSON input`. All three `request<void>(...)` call sites (`api.ts:26`, `api.ts:42`, `api.ts:48`) therefore reject on success. Consequences:

- **`MasterResumePanel.tsx:44-52`** — the delete succeeds server-side, the `catch` fires, `onDelete()` never runs, and the user sees a red error bar reading `Unexpected end of JSON input`. The resume is gone from the DB while the UI still shows it.
- **`ChatDrawer.tsx:18-25`** — `api.clearChat()` succeeds, the `catch` swallows it (`// non-critical`), `setClearKey((k) => k + 1)` never fires, so `ChatPanel` is never remounted and the transcript stays on screen. The button looks broken.
- **`ResumeListPanel.tsx:37-46`** — `onDeleted?.(id)` never fires, so a deleted-but-currently-selected resume stays in the preview pane (`WorkstationShell.tsx:31-33` is never invoked). The `fetchList(sort)` at `:45` runs outside the try/catch and masks the list side of the bug, which is why it has gone unnoticed.

Fix: `if (res.status === 204 || res.headers.get("content-length") === "0") return undefined as T;` before line 12.

### P0-3. Any backend failure on load is rendered as "you have no resume"
`api.ts:17-18`:

```ts
getMasterResume: () => request<MasterResume | null>("/api/master-resume").catch(() => null),
```

A blanket catch. A 500, a 503 from `LLMUnavailableError` (`main.py:41-43`), a network drop, a proxy failure, a JSON parse error — all collapse to `null`. `WorkstationShell.tsx:51-53` then renders the onboarding screen:

```tsx
if (!masterResume) {
  return <EmptyState onImport={handleImport} onLoadSample={handleLoadSample} />;
}
```

A user with a saved master resume sees "Every job deserves a tailored resume" and a **Start from Sample** button which, at `WorkstationShell.tsx:26-30`, immediately `PUT`s the sample YAML over their real data:

```tsx
const handleLoadSample = useCallback(async (yaml: string) => {
  const saved = await api.saveMasterResume(yaml);   // destructive
  setMasterResume(saved);
}, []);
```

The genuine 404 case (`master_resume.py:91-92`, `raise HTTPException(404, "No master resume found")`) is indistinguishable from total backend failure. Only a 404 should map to `null`; everything else must surface an error state.

### P0-4. The chat drawer advertises a capability the backend does not have
`ChatPanel.tsx:76-79` tells the user:

> "Ask for edits to your master resume — rewrite a section, add a bullet, restructure the YAML. **Changes apply directly.**"

`backend/app/routes/chat.py:63` always emits:

```python
yield _sse("done", {"result": {"text": full_text, "action": None}})
```

There is no tool-calling, no YAML mutation, no write path of any kind in `chat_stream` — it is `api.stream(messages)` and nothing else (`chat.py:57-63`). Consequently:
- `ChatPanel.tsx:53-58`, the whole `master_resume_updated` branch, is dead code.
- `ChatAction` (`types.ts:54-57`) is dead — declared, never imported anywhere.
- `ChatDrawer`'s `onAction` prop (`ChatDrawer.tsx:11`) and `WorkstationShell.tsx:86` `onAction={setMasterResume}` are dead wiring.

It is a plain chatbot with copy claiming otherwise. Either implement tool-calling in `chat.py` or change the copy.

### P0-5. Keyboard users cannot import a PDF
`EmptyState.tsx:109-122`:

```tsx
<div
  data-testid="pdf-import-zone"
  onDrop={onDrop}
  onDragOver={(e) => e.preventDefault()}
  onClick={() => fileRef.current?.click()}
  className="seam-dashed w-full max-w-md cursor-pointer rounded-xl border-2 ..."
>
  <input ref={fileRef} type="file" accept=".pdf" className="hidden" ... />
```

A bare `<div onClick>`: no `role`, no `tabIndex`, no `onKeyDown`. The `<input type="file">` inside it carries `className="hidden"` (`:119`), which sets `display: none` and removes it from the tab order too. There is **no keyboard path to the primary onboarding action**. The only alternatives on that screen are "Start from Sample" (overwrites with dummy data) and a YAML download link.

### P0-6. Streams are never aborted — no `AbortController` exists anywhere in the codebase
`sse.ts:9-13` accepts a signal:

```ts
export async function* readSseStream(path: string, body: unknown, signal?: AbortSignal)
```

**No call site passes one.** Grep for `AbortController` across `frontend/src` returns nothing. The three call sites:
- `ChatPanel.tsx:40` — `readSseStream("/api/chat/stream", { message: userMsg })`
- `GenerationPanel.tsx:38` — `readSseStream("/api/resumes/stream", { job_description: jd })`
- `EvaluationPanel.tsx:59` — `readSseStream("/api/evaluate/stream", {...})`

Consequences:
- Closing the chat drawer mid-stream (`WorkstationShell.tsx:83`, `{chatOpen && <ChatDrawer .../>}`) unmounts `ChatPanel` while the async generator keeps calling `setMessages` (`ChatPanel.tsx:43`) — React unmounted-update warnings and an orphaned HTTP connection.
- Navigating away mid-generation unmounts `GenerationPanel` and orphans a 30s+ LLM-plus-Typst job; `onGenerated` (`GenerationPanel.tsx:44`) never fires, so the result is lost from the UI even though `resumes.py:133` persisted it.
- `PdfPreview.tsx:19` likewise has no abort — only a `cancelled` boolean flag guarding `setState`. The Typst render keeps running server-side.

---

## P1

### P1-7. Props-to-state desync in the editor
`MasterResumePanel.tsx:23` derives `yaml` from the `resume` prop at mount only, with no resync effect. Any external update to `masterResume` in the shell leaves the editor showing stale text, while `dirty` at `:28`:

```tsx
const dirty = yaml !== resume.yaml_content;
```

flips to `true` against the **new** prop — the header caption lies ("· edited" when the user edited nothing), and a subsequent Save would clobber the external update. Currently latent only because P0-4 means nothing external ever updates it. It becomes live the moment chat tool-calling or any background refresh lands.

### P1-8. Generate and Evaluate silently use the *saved* resume, not what is on screen
- `EvaluationPanel.tsx:59-62` sends `masterResume.yaml_content` — i.e. the last **saved** version from the shell's state, not the editor buffer.
- `GenerationPanel` does not use `masterResume` at all: `:18` destructures it into `_masterResume` and discards it; the backend re-reads the DB itself (`resumes.py:61`, `get_master_resume(_db_path())`).

Edit the YAML, don't save, switch to Generate → you tailor the **old** resume with zero indication. Combined with P0-1, the user's edits are both ignored and then destroyed.

### P1-9. Backend error messages never reach the user
`api.ts:8-11`:

```ts
if (!res.ok) {
  const body = await res.json().catch(() => ({ error: res.statusText }));
  throw new Error(body.error ?? res.statusText);
}
```

Only the four custom exception handlers in `main.py:36-52` emit `{"error": ..., "code": ...}`. Every FastAPI `HTTPException` serializes as `{"detail": ...}`:
- `master_resume.py:92` — `"No master resume found"`
- `master_resume.py:104` — `"No master resume to delete"`
- `master_resume.py:124` — render failure detail
- `master_resume.py:132` — `"File must be a PDF"`
- `resumes.py:152`, `:162`, `:172` etc.

So every `HTTPException` surfaces to the user as the bare `res.statusText` — "Not Found", "Unprocessable Entity", "Bad Request". `PdfPreview.tsx:23` gets this right:

```ts
throw new Error(body?.detail ?? body?.error ?? `Preview failed (${res.status})`);
```

which makes the inconsistency provable rather than theoretical: two error-reading strategies in the same codebase, one correct.

Separately, the `code` field (`NO_MASTER_RESUME`, `LLM_AUTH_ERROR`, `LLM_UNAVAILABLE`, `RENDER_FAILED`, `PDF_EXTRACT_FAILED`, `GENERATION_FAILED`, `CHAT_FAILED`, `EVALUATION_FAILED`) is **parsed nowhere** in the frontend. `Error` is a string bag; the UI cannot branch on "you need to configure an API key" vs "the renderer crashed".

### P1-10. PDF preview re-renders server-side on every mount
`PdfPreview.tsx:14-39` fetches on `[pdfUrl]` with no cache, no ETag check, no request dedupe, no debounce:

```tsx
useEffect(() => {
  let url: string; let cancelled = false;
  setBlobUrl(null); setError(null);
  fetch(pdfUrl).then(...).then((blob) => { url = URL.createObjectURL(blob); setBlobUrl(url); })
  return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
}, [pdfUrl]);
```

`/api/master-resume/preview` (`master_resume.py:109-124`) runs a full `normalize_to_rendercv` plus a Typst compile on **every** call. Because:
- Split is the default mode (`MasterResumePanel.tsx:26`), the preview mounts on first paint;
- every Save bumps `previewKey` (`MasterResumePanel.tsx:36`), forcing a remount and another full render;
- switching Editor → Generate → Editor unmounts and remounts the whole panel, triggering another;

…a typical session fires many multi-second Typst compiles. There is no "preview is stale — re-render?" affordance, no cached last-good PDF, and nothing debounces a rapid Save-Save.

The blob lifecycle itself is correct (the `cancelled` early-return at `:28` prevents a leaked `createObjectURL`, and the closure-captured `url` is revoked properly), but there is no `AbortController` (see P0-6).

### P1-11. Both build-artifact trees are two commits stale
- `frontend/out/index.html` — **Jul 9 09:47**
- `backend/static/index.html` — **Jul 9 09:47**
- `diff -rq frontend/out backend/static` → identical, byte for byte.
- `Sidebar.tsx` and `ChatDrawer.tsx` landed in commit `e943dfb`, **2026-07-14**.

So the artifacts predate the current navigation shell by five days and two commits. `main.py:68-70` mounts `backend/static` at `/` when it exists:

```python
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
```

Running the backend locally therefore serves a UI two commits behind the source **with no warning**. Docker is fine (`Dockerfile:8-11` builds fresh; `:24` `COPY --from=frontend-builder /build/frontend/out ./static/`), but there is no local build-and-copy step: no `postbuild` script, no `predev` hook, nothing in `package.json:5-10`.

### P1-12. `distDir: 'out'` publishes build internals
`next.config.js:1-7`:

```js
const nextConfig = { output: 'export', distDir: 'out', trailingSlash: true, images: { unoptimized: true } };
```

`distDir` is the Next **build** directory (normally `.next`); `output: 'export'` already emits the static site to `out/` by default. Overriding `distDir` to `out` collapses the two, so Next writes its build manifests and build-ID directory into the same tree that is exported and shipped — `frontend/out/_next/mhpNN7BjcF2Un7tCkJb92/` is the build-ID dir sitting next to `_next/static/`. `Dockerfile:24` copies the whole tree into `backend/static/`, which `main.py:70` serves publicly with `html=True`. Build IDs and manifests become fetchable. Correct config: drop `distDir` entirely.

### P1-13. No routing at all — the app is one route with `useState` for navigation
`app/page.tsx:3-5` renders a single `<WorkstationShell />`. The view is state (`WorkstationShell.tsx:17`):

```tsx
const [view, setView] = useState<View>("editor");
```

Consequences: no deep links; no browser back/forward; no shareable URL for a generated resume; a refresh dumps you back to Editor with `selectedResume` (`:18`) cleared; the `404.html` produced by the export is unreachable in practice because there are no other paths. `trailingSlash: true` plus `StaticFiles(html=True)` means only `/` resolves.

With `output: 'export'` the cheap fix is `?view=` plus `history.pushState`; the correct fix is real routes (see Restructure).

### P1-14. Library silently truncates at 20 and reports the wrong count
`api.ts:29-32`:

```ts
listResumes: (sort: SortField = "date", order: SortOrder = "desc", page = 1) =>
  request<ResumeListResponse>(`/api/resumes?sort=${sort}&order=${order}&page=${page}&limit=20`),
```

`limit` is hardcoded to 20 and `page` is never passed by any caller (`ResumeListPanel.tsx:26` calls `api.listResumes(s, order)`). `ResumeListPanel.tsx:27` destructures only `data.items` and **discards `data.total`**, then `:53-55` renders:

```tsx
<span className="text-xs text-muted-foreground">
  {items.length} tailored {items.length === 1 ? "resume" : "resumes"}
</span>
```

At 21+ resumes the user sees "20 tailored resumes" — the page size, presented as the total — and has no pagination UI to reach the rest. `ResumeListResponse.total` (`types.ts:21`) exists and is thrown away.

Also `ResumeListPanel.tsx:20`: `const [order] = useState<SortOrder>("desc");` — state with no setter. Dead.

### P1-15. Race conditions on rapid interaction
- **`ResumeListPanel.tsx:23-35`** — `fetchList` has no sequence guard, no abort, no request-id check. Toggling sort quickly fires overlapping requests; the slower response wins and the list contradicts the highlighted segment.
- **`GenerationPanel.handleGenerate` (`:31`)** and **`EvaluationPanel.handleEvaluate` (`:53`)** guard re-entry only via the `disabled` prop on the button (`GenerationPanel.tsx:98`, `EvaluationPanel.tsx:104`). There is no in-function `if (generating) return;`. A keyboard Enter repeat or a programmatic click between state flush and re-render starts a second stream. Contrast `ChatPanel.tsx:29`, which does guard correctly: `if (!input.trim() || sending) return;`.
- **`MasterResumePanel.handleSave` (`:30`)** has no re-entry guard either; the button `disabled={saving}` at `:86` is the only protection.

### P1-16. Accessibility — `role="tab"` misuse
`ui/SegmentedControl.tsx:22-44`:

```tsx
<div role="tablist" className="inline-flex ...">
  {options.map((o) => (
    <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)} ...>
```

Declares the ARIA tabs pattern with **no `aria-controls`, no element with `role="tabpanel"`, no roving `tabIndex`, no arrow-key handler**. Screen readers announce "tab 1 of 3" and arrow keys do nothing — a broken implementation of a pattern that was the wrong choice to begin with. Neither usage is a tab:
- `MasterResumePanel.tsx:71-79` — Editor/Split/Preview is a **view toggle**.
- `ResumeListPanel.tsx:57-64` — By Date / By JD is a **sort control**.

Both should be `role="radiogroup"` + `role="radio"` with arrow-key navigation, or plain buttons with `aria-pressed`.

### P1-17. Accessibility — the streaming chat is silent to screen readers
`ChatPanel.tsx:74-108` — the message list has no `aria-live`, no `role="log"`, no `aria-atomic`. Tokens stream into the DOM (`:43-52`) with zero announcement. The "Thinking…" indicator (`:101-106`) is likewise unannounced. A screen-reader user gets no feedback that a reply is arriving or has finished.

On top of that, `:83` uses `key={i}` while the array is simultaneously appended to and last-element-replaced (`:43-52`) — an index-key reconciliation hazard on a list whose tail mutates on every token.

### P1-18. Accessibility — not one `role="alert"` on any error
Every error surface is a silent `<p>`:
- `MasterResumePanel.tsx:93-95`
- `GenerationPanel.tsx:104-108`
- `EvaluationPanel.tsx:110-114`
- `ChatPanel.tsx:110`
- `EmptyState.tsx:137`

Failures — including the P0-2 delete error and the P1-9 stringly-typed backend errors — are entirely invisible to assistive tech.

### P1-19. Accessibility — resume list items are not operable
`ResumeListPanel.tsx:83-91`:

```tsx
<div key={r.id} data-testid="resume-list-item" onClick={() => onSelect(r)} className="group cursor-pointer ...">
```

No `role`, no `tabIndex`, no `onKeyDown`. The entire library is mouse-only. (The nested delete button at `:103-109` is focusable and correctly reveals itself via `focus-visible:opacity-100`, so a keyboard user can delete a resume they cannot select.)

### P1-20. Accessibility — the chat drawer is not a dialog and has no focus management
`ChatDrawer.tsx:28`:

```tsx
<aside className="flex h-full w-[380px] shrink-0 flex-col border-l border-border bg-surface-1">
```

No `aria-label`, no `role`, no labelled region. Opening it does not move focus; there is no Escape-to-close; closing it does not return focus to the `nav-chat` toggle (`Sidebar.tsx:82-89`). Because `WorkstationShell.tsx:83` fully unmounts it (`{chatOpen && <ChatDrawer ... />}`), every reopen:
- refetches the entire chat history (`ChatPanel.tsx:20-22`),
- discards any half-typed message (`ChatPanel.tsx:15`),
- discards any in-flight stream (see P0-6).

The close and clear buttons themselves are correctly labelled (`ChatDrawer.tsx:35`, `:38`).

### P1-21. Contrast failures against the app's own palette
Computed against `--background: #0c0d0f` (`globals.css:6`), WCAG 2.1 relative luminance:

| Token | Value | Ratio vs bg | Requirement | Verdict |
|---|---|---|---|---|
| `--faint-foreground` | `#5c6169` | **≈ 3.1:1** | 4.5:1 (normal text) | **fail** |
| `--border` | `#26282d` | **≈ 1.3:1** | 3:1 (form boundaries / UI) | **fail** |
| `.seam-dashed` | `rgba(217,168,78,0.35)` → ≈ `#543f20` | **≈ 2.0:1** | 3:1 (non-text indicator) | **fail** |
| `--muted-foreground` | `#8b9099` | ≈ 6.1:1 | 4.5:1 | pass |
| `--accent` | `#d9a84e` | ≈ 8.9:1 | 4.5:1 | pass |

Where each failure bites:
- **`--faint-foreground`** — the `updated …` caption (`MasterResumePanel.tsx:64`), list dates (`ResumeListPanel.tsx:100`), the delete icon at rest (`ResumeListPanel.tsx:106`), and **every** `placeholder:text-faint` (`GenerationPanel.tsx:91`, `EvaluationPanel.tsx:97`, `ChatPanel.tsx:119`). Most of these are also `text-[11px]`, compounding it.
- **`--border`** — every panel divider (`MasterResumePanel.tsx:59`, `:115`; `GenerationPanel.tsx:71`, `:79`; `Sidebar.tsx:62`; `ChatDrawer.tsx:28`, `:29`) and every input border (`GenerationPanel.tsx:91`, `EvaluationPanel.tsx:97`, `ChatPanel.tsx:111`). Form-field boundaries are effectively invisible.
- **`.seam-dashed`** (`globals.css:64-67`) — the active-nav stitch (`Sidebar.tsx:48-53`), the PDF drop zone (`EmptyState.tsx:114`), and all three empty-state circles. **The one motif carrying the entire brand concept is the one that fails contrast.**

The global focus ring is correct: `globals.css:58-61`, `:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }` — gold on dark at ~8.9:1. `prefers-reduced-motion` is also handled (`globals.css:83-89`).

---

## P2

### P2-22. Type safety — nine unchecked casts of `unknown`
`sse.ts:4-7` types the payload honestly:

```ts
export interface SseEvent { event: string; data: unknown; }
```

…and then every consumer asserts blindly:
- `ChatPanel.tsx:42` — `(event.data as { delta: string }).delta`
- `ChatPanel.tsx:54` — `event.data as { result: { text: string; action: unknown } }`
- `ChatPanel.tsx:56` — `(result.result?.action as { type?: string })?.type`
- `ChatPanel.tsx:60` — `(event.data as { error: string }).error`
- `GenerationPanel.tsx:40` — `(event.data as { message: string }).message`
- `GenerationPanel.tsx:42` — `(event.data as { result: GeneratedResume }).result`
- `GenerationPanel.tsx:47` — `(event.data as { error: string }).error`
- `EvaluationPanel.tsx:64` — `(event.data as { result: EvaluationResult }).result`
- `EvaluationPanel.tsx:66` — `(event.data as { error: string }).error`

No literal `any` appears in `frontend/src`, which makes the codebase look safer than it is. A malformed `done` payload is an unguarded runtime `TypeError` inside an async generator loop.

The fix was half-started and abandoned: `types.ts:59-61` declares

```ts
export interface SseProgressEvent { message: string; }
export interface SseTokenEvent { delta: string; }
export interface SseErrorEvent { error: string; code: string; }
```

…and **nothing imports them**. A discriminated union is the obvious shape:

```ts
type SseEvent =
  | { event: "progress"; data: { message: string } }
  | { event: "token";    data: { delta: string } }
  | { event: "done";     data: { result: unknown } }
  | { event: "error";    data: { error: string; code: string } };
```

Note also `SseErrorEvent.code` — the backend does send `code` on every error (`resumes.py:135-143`, `chat.py:64-71`, `evaluate.py:66-73`) and the frontend reads only `.error` everywhere.

### P2-23. Zero runtime validation; types hand-maintained against an untyped API
`api.ts:6-13` casts raw JSON straight to `T`. Nothing parses, nothing validates. Meanwhile **no backend route declares a `response_model`** — `resumes.py:46`, `:149`, `:157`, `:180`; `rules.py:25`, `:29`, `:35`; `chat.py:34`; `master_resume.py:88`, `:96`; `system_prompt.py`. Routes return raw `sqlite3.Row`-derived dicts.

Drift already visible:
- `GeneratedResume.yaml_content?: string` (`types.ts:13`) — optional purely as a guess; the DB row shape decides.
- `Rule.rule_value: string` (`types.ts:37`) — driven by `<input type="number">` (`GenerationPanel.tsx:125-130`), so the UI's mental model and the type disagree.
- `MasterResume.updated_at: string` (`types.ts:5`) is fed straight into `new Date(...)` (`MasterResumePanel.tsx:67`) with no format guarantee; the test fixture uses `"2026-01-01"` while SQLite emits `"2026-01-01T00:00:00"`.
- `ChatAction` (`types.ts:54-57`) describes four action types the backend never emits (see P0-4).

No OpenAPI codegen, no zod, no io-ts, no contract test.

### P2-24. tsconfig is `strict` but not strict; there is no linter at all
`tsconfig.json:11` sets `"strict": true`. Missing: `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `noUnusedLocals`, `noUnusedParameters` (the last two would have caught the `_masterResume` dead props in P2-27).

There is **no ESLint whatsoever**: no `eslint` or `eslint-config-next` in `package.json:20-35`, no `.eslintrc*` anywhere in `frontend/`, no `lint` script in `package.json:5-10`. `next lint` is unavailable. `eslint-plugin-jsx-a11y` — which ships with `eslint-config-next` by default — would have flagged P0-5, P1-19, and P2-31 mechanically.

`tsconfig.json:36` also includes `"out/types/**/*.ts"`, a consequence of the `distDir` override (P1-12).

### P2-25. Bundle — 1.1 MB of uncompressed JS on a single route, all eager
`frontend/out/_next/static/chunks/` (1.6 MB total export, 1.1 MB of chunks):

| Chunk | Size |
|---|---|
| `818-355f4c6893cd9657.js` | 250 KB |
| `363642f4-e0566eac810c15bd.js` | 195 KB |
| `fd9d1056-851a54dc28dcef93.js` | 173 KB |
| `framework-f66176bb897dc684.js` | 141 KB |
| `23-b618f94ad5ea4cd3.js` | 124 KB |
| `main-c980e89993b16cc4.js` | 110 KB |
| `polyfills-78c92fac7aa8fdd8.js` | 91 KB |

CodeMirror is statically imported (`MasterResumePanel.tsx:3-4`):

```tsx
import CodeMirror from "@uiw/react-codemirror";
import { yaml as yamlLang } from "@codemirror/lang-yaml";
```

…and because `page.tsx:1` → `WorkstationShell.tsx:3-10` statically imports all four panels, **the editor ships to users who are still on the onboarding screen**. Nothing anywhere uses `next/dynamic`. There is exactly one route, so Next's route-level code splitting buys nothing.

Fonts: three Google families via `next/font` (`layout.tsx:5-11`) — Inter, Fraunces (with the `opsz` variable axis, a large file), JetBrains Mono. Self-hosted at build time, so no third-party RTT, but three families is heavy for a UI that uses the display face at two sizes (see UI section, item 6).

`lucide-react` is imported by named icon (`Sidebar.tsx:2`, `ChatDrawer.tsx:3`, etc.), which tree-shakes correctly.

### P2-26. Dead dependency: `next-themes`
`package.json:16` — `"next-themes": "^0.3.0"`. Imported nowhere in `frontend/src`. Meanwhile:
- `layout.tsx:20` hardcodes `<html lang="en" className="dark">`.
- `globals.css:5-40` defines only a single `:root` block — there is no light palette and no `@media (prefers-color-scheme: light)`.
- `tailwind.config.ts:5` sets `darkMode: "class"` with nothing to toggle.

There is no theme system — a dark-only page with the scaffolding of one. Either build the light palette or delete the dependency and the `darkMode` config.

### P2-27. Dead props drilled through the shell
- `ChatPanel.tsx:13` — `export default function ChatPanel({ masterResume: _masterResume, onAction }: Props)`
- `GenerationPanel.tsx:18` — `export default function GenerationPanel({ masterResume: _masterResume, onGenerated }: Props)`

Both destructure-and-discard. `WorkstationShell.tsx:72` and `:85` drill the prop through anyway, and `ChatDrawer.tsx:15`/`:44` relays it a second hop. Three components carry a prop nobody reads.

### P2-28. Rules editing fails silently and can desync
`GenerationPanel.tsx:59-67`:

```tsx
async function handleRuleChange(section: string, key: string, value: string) {
  if (value.trim() === "") return;               // silent no-op
  try {
    const updated = await api.updateRules([{ section, rule_key: key, rule_value: value }]);
    setRules(updated);
  } catch {
    // silently fail — rules are non-critical
  }
}
```

The inputs are **uncontrolled** (`defaultValue={r.rule_value}`, `:127`) with stable keys (`:121`), so `setRules(updated)` cannot re-render them — React reuses the DOM node and `defaultValue` is ignored after mount. A failed save therefore leaves the typed value on screen while the server holds the old one, with no error shown. Clearing an input to empty is a no-op that also leaves the empty box visible.

No range validation either: `rules_block()` (`resumes.py:71`) feeds these values straight into the generation prompt, so `9999` bullets is accepted client-side.

`upsert_rules` (`backend/app/database.py:266-277`) is a true upsert over the primary key, so sending a single rule does not clobber the others — that part is correct.

### P2-29. SSE parser fragility
`sse.ts:24-48`:
- **CRLF** — `buffer.split("\n")` (`:33`). Any intermediary that rewrites line endings leaves a trailing `\r`, which breaks both `line.slice(6).trim()` event-name matching and `JSON.parse(raw)`. `.trim()` at `:38` saves the data line but not the `event:` line, which already trims at `:37` — so partially mitigated, by accident.
- **Multi-line `data:`** — the SSE spec says consecutive `data:` lines concatenate with `\n`. This parser yields each one as a separate event (`:41`).
- **Trailing partial line** — `buffer = lines.pop() ?? ""` (`:34`); if the stream ends without a final newline, the last event is silently dropped. Survives only because `_sse()` (`resumes.py:33-34`) always appends `\n\n`.
- **No `id:` / `retry:` handling**, no reconnect, no heartbeat/timeout.
- `:20-23` — `if (!res.ok || !res.body)` then `await res.json()`; in the `res.ok && !res.body` branch the body is already null and `res.json()` rejects into the `.catch`, so it degrades to `statusText`. Harmless but unintentional.
- `:29-31` — the loop runs until the server closes; a `done` event does not terminate it. Acceptable given the backend closes, but it means a hung server hangs the UI forever with no timeout.

### P2-30. PDF preview has no screen-reader story and no fallback
`PdfPreview.tsx:54-63`:

```tsx
<iframe src={`${blobUrl}#toolbar=0&navpanes=0`} className="h-full w-full rounded-lg border border-border bg-white" title="Resume PDF Preview" />
```

A single `<iframe>` over a `blob:` URL is the entire accessible representation of the user's resume. No text alternative, no "view as text" toggle, no download link in the editor preview — only the Generate and Library panes offer one (`GenerationPanel.tsx:145-151`, `ResumeListPanel.tsx:121-127`). `#toolbar=0&navpanes=0` is a Chrome-only hint that `docs/screenshots/03-master-resume-preview.png` shows being ignored (the full PDF toolbar with page thumbnails is visible); Firefox and Safari render their own chrome regardless.

### P2-31. Unlabelled rule inputs
`GenerationPanel.tsx:120-131` — `<label className="text-[11px] ...">` with no `htmlFor`, and `<input type="number">` with no `id`. Not associated. The only correctly labelled fields in the app are `jd-input` (`GenerationPanel.tsx:81-92`) and `eval-jd` (`EvaluationPanel.tsx:88-98`). The chat textarea (`ChatPanel.tsx:112-120`) has a placeholder and a `data-testid` but no label and no `aria-label`.

### P2-32. Sidebar semantics
`Sidebar.tsx:41` — `aria-current={active && !subtle ? "page" : undefined}` on a `<button>` in a state-driven nav. Nothing navigates (no URL changes), so `"page"` is wrong; `aria-current="true"` is correct until P1-13 is fixed. Also:
- `<nav>` at `:62` has no `aria-label` and no list semantics (`<ul>`/`<li>`).
- Nav labels render at `text-[10px]` (`:55`).
- The product name exists only as `title="ResumeTailor"` on a div (`:63-68`) — invisible to touch, and a `title` on a non-interactive element is unreliable for screen readers.
- No skip link anywhere in `layout.tsx` or `WorkstationShell.tsx`.

The `aria-pressed` handling for the chat toggle (`:42`) is correct, and the comment at `:34-35` explaining the `subtle` variant is good.

### P2-33. `ConfirmButton` arms silently
`ui/ConfirmButton.tsx:39-49` — a two-step destructive button. `onBlur={() => setArmed(false)}` (`:44`) disarms on focus loss, so a keyboard user who tabs away loses the armed state with no announcement. The `aria-label` swap (`:46`) is not in a live region, so the arm transition is unannounced. A 3-second timeout (`:31`) is a weak affordance for deleting the user's only master resume (`MasterResumePanel.tsx:90`). A real `<dialog>` with a focus trap is warranted for that one.

The cleanup at `:26` (`useEffect(() => () => clearTimeout(timer.current), [])`) is correct.

### P2-34. Tests test almost nothing, and e2e selectors are dictating production copy
Three files, seven assertions total:
- `__tests__/ChatPanel.test.tsx` — "renders chat input and send button"; "displays message after send" (asserts `length > 0`).
- `__tests__/MasterResumePanel.test.tsx:24-31` — save calls the API; `:33-38` — a `data-testid` exists.
- `__tests__/ResumeListPanel.test.tsx` — renders 2 items; sort calls the API with `("jd","desc")`.

Nothing covers `api.ts`, `sse.ts`, any error path, the P0-2 204 bug, or any panel's loading/empty/error states. `package.json:9` runs `jest --passWithNoTests`. No coverage threshold.

Worse, e2e selectors have leaked into production source as constraints. `MasterResumePanel.tsx:62-63`:

```tsx
{/* Caption must not start with "s": "Resume"+"s…" would collide with
    getByText("Resumes") used by the e2e nav tests. */}
```

That is a test-selector concern dictating user-visible copy. The offending selector is `test/e2e/07-evaluation.spec.ts:22` — `page.getByText("evaluate", { exact: false })` — and `test/e2e/02-master-resume.spec.ts:46` — `page.getByText("Preview").click()`. Both should be `data-testid`s, freeing the copy.

### P2-35. `docs/screenshots/` is wholly obsolete — the README misrepresents the product
All 8 PNGs are dated **Jul 6** and show a **different application**:
- A top header bar reading "ResumeTailor | AI Resume Workstation" — no such element exists in the current source.
- Horizontal top tabs **Generate | Resumes | Evaluate** — the current app has a 76px left icon rail (`Sidebar.tsx:62`).
- A bottom-docked **"AI Chat Assistant ▼"** strip spanning the window — the current app has a right-side 380px drawer (`ChatDrawer.tsx:28`).
- Plain white/grey buttons, no accent colour anywhere — the current palette is gold `#d9a84e` (`globals.css:18`).
- An empty state headlined **"Welcome to ResumeTailor / Start by creating your master resume — the single source of truth for all generated resumes."** The current copy is **"Every job deserves a *tailored* resume."** (`EmptyState.tsx:86-92`).
- Sans-serif headings throughout — the current design uses Fraunces (`layout.tsx:6-10`).
- `03-master-resume-preview.png` shows the full Chrome PDF toolbar, contradicting `#toolbar=0` (see P2-30).

`README.md:11-23` embeds all eight in a feature grid. Anyone evaluating this repo sees a product that no longer exists — and sees the *pre-redesign* version, which is markedly worse.

---

# 1. App architecture

**Routing.** One route. `app/page.tsx:3-5` renders `<WorkstationShell />`; `next.config.js:2-6` sets `output: 'export'` with `trailingSlash: true`. Navigation is `useState<View>` (`WorkstationShell.tsx:17`) switching four conditionally-rendered panels (`:64-81`). `View` is `"editor" | "generate" | "resumes" | "evaluate"` (`types.ts:66`). See P1-13.

**State management.** No store, no context, no reducer — `useState` throughout, five pieces in the shell:

```tsx
const [masterResume, setMasterResume] = useState<MasterResume | null>(null);  // server state
const [loading, setLoading] = useState(true);                                 // fetch state
const [view, setView] = useState<View>("editor");                             // UI state
const [selectedResume, setSelectedResume] = useState<GeneratedResume | null>(null); // server+UI
const [chatOpen, setChatOpen] = useState(true);                               // UI state
```

`WorkstationShell.tsx:15-19`. Server state and UI state sit in the same bag with no distinction, no cache, no invalidation, no staleness tracking. Each panel then keeps its *own* server state locally — `GenerationPanel.tsx:24` `rules`, `ResumeListPanel.tsx:18` `items`, `ChatPanel.tsx:14` `messages` — fetched on mount and discarded on unmount. Closing and reopening the chat drawer refetches the entire history (P1-20); leaving and returning to the Library refetches the whole list.

**Data fetching.** Manual `fetch` via a 8-line wrapper (`api.ts:6-13`). No cache, no dedupe, no retry, no stale-while-revalidate, no request cancellation, no TanStack Query / SWR / RSC data loading. Three distinct fetch idioms coexist:
1. `api.*` → `request<T>` (`api.ts`)
2. `readSseStream` async generator (`sse.ts`)
3. A hand-rolled `fetch` + blob pipeline inside `PdfPreview.tsx:19-34`

Loading/error/empty coverage is uneven:
- `WorkstationShell.tsx:40-49` — a loading screen, but **no error screen** (P0-3 folds errors into empty).
- `ResumeListPanel.tsx:71-79` — loading, empty, but **no error state**; `:28-29` catches and sets `items: []`, so a failed fetch renders "No tailored resumes yet."
- `GenerationPanel.tsx:28` — `api.getRules().catch(() => setRules([]))`; a failed rules fetch renders an empty rules form with no explanation.
- `ChatPanel.tsx:21` — `.catch(() => setMessages([]))`; a failed history fetch renders the onboarding hint as if the conversation were new.

The pattern is consistent and consistently wrong: **every failure is rendered as emptiness.**

**Prop drilling.** Shallow (two hops max) but carries dead weight: `masterResume` → `ChatDrawer` → `ChatPanel` where it is discarded (P2-27); `masterResume` → `GenerationPanel` where it is discarded. `onAction` → `ChatDrawer` → `ChatPanel` for a code path the backend never triggers (P0-4). Five callbacks are `useCallback`-memoized in the shell (`:25-38`) but three of the five consumers are conditionally rendered and remount anyway, so the memoization buys nothing.

**Component responsibilities — what is doing too much:**

| Component | LOC | Concerns |
|---|---|---|
| `GenerationPanel.tsx` | 182 | JD form + SSE generation orchestration + rules CRUD + result header + download + PDF preview host + empty state |
| `EvaluationPanel.tsx` | 175 | JD form + SSE orchestration + an inline `ScoreRing` SVG component (`:18-45`) + `scoreColor` (`:12-16`) + keyword columns + empty state |
| `ResumeListPanel.tsx` | 148 | List fetch + sort + delete + selection + preview pane + download + empty state |
| `EmptyState.tsx` | 153 | Marketing hero + a 27-line hardcoded YAML constant (`:9-35`) + data-URI download + drag-drop + file input + PDF import orchestration |
| `MasterResumePanel.tsx` | 127 | Editor buffer + dirty tracking + save + delete + mode toggle + preview-key invalidation + CodeMirror config |

`ScoreRing` (`EvaluationPanel.tsx:18-45`) is the best-designed element in the app and is trapped inside a panel where nothing else can use it. `SAMPLE_YAML` (`EmptyState.tsx:9-35`) is product data living in a presentational component. The three empty states (`GenerationPanel.tsx:168-176`, `ResumeListPanel.tsx:137-142`, `EvaluationPanel.tsx:162-169`) are the same block copy-pasted three times and never extracted.

`ui/` is genuinely reusable and well-sized (`Button` 39 L, `Badge` 26 L, `Spinner` 22 L, `SegmentedControl` 47 L, `ConfirmButton` 51 L). `Button` correctly uses `forwardRef` and spreads `...rest` (`ui/Button.tsx:26-37`). `SegmentedControl` is properly generic over `T extends string` (`ui/SegmentedControl.tsx:16`). The problem is not quality but coverage: there is no `Dialog`, no `Alert`, no `Field`, no `EmptyState`, no `PanelHeader` — exactly the primitives whose absence produces the duplication above.

---

# 2. API client layer

**`api.ts` (83 lines).** A flat object of 17 methods over a single `request<T>` wrapper.

- **Base URL config: none.** Every path is a bare relative string (`"/api/master-resume"`, `` `/api/resumes/${id}` ``). No `NEXT_PUBLIC_API_URL`, no env var, no `basePath`. This works only because FastAPI serves the static export from the same origin (`main.py:68-70`). It means `next dev` on :3000 cannot reach a backend on :8000 without a `rewrites` block, which `next.config.js` does not have — so local frontend development against a live backend is impossible without editing config. It also forecloses any split deployment (CDN + API host).
- **Error handling.** See P1-9 — reads `body.error`, backend `HTTPException` sends `{detail}`. The `code` field is never read. `Error` is the only error type; there is no `ApiError` carrying `status`/`code`.
- **204 handling: none.** See P0-2.
- **Blanket catch.** `api.ts:18` — see P0-3.
- **Typing accuracy.** See P2-23. `request<T>` is an unchecked cast.
- **`getPdfUrl`** (`api.ts:72`) returns a string, not a request — fine, used for `<a download>` (`GenerationPanel.tsx:146`, `ResumeListPanel.tsx:122`).
- **`importPdf`** (`api.ts:75-82`) correctly omits `Content-Type` so the browser sets the multipart boundary. Correct.
- **Unused methods:** `getResume`, `updateResume`, `renderResume` (`api.ts:33-44`), `getSystemPrompt`, `updateSystemPrompt`, `resetSystemPrompt` (`api.ts:61-69`), `resetRules` (`api.ts:58`). Eight of seventeen methods have no caller — the system-prompt editing feature exists in the backend (`routes/system_prompt.py`) and in the client, with no UI at all.

**`sse.ts` (49 lines).** An async generator over `fetch` + `ReadableStream`.

- Abort/cancel: parameter exists, never passed (P0-6).
- Reconnect: none. No `EventSource` fallback, no retry, no backoff, no timeout.
- Parser correctness: P2-29.
- Error surface: `:20-23` mirrors `api.ts`'s wrong `err.error` read, but here it is *right* — streaming routes return HTTP 200 and deliver failures as SSE `error` events (`resumes.py:135-143`, `chat.py:64-71`, `evaluate.py:66-73`), so the `!res.ok` branch only fires on framework-level failures. The in-stream `error` events *are* handled by all three consumers.
- **Race conditions on rapid interaction:** see P1-15. Additionally, an SSE `error` event does not break the loop in any consumer (`ChatPanel.tsx:59-61`, `GenerationPanel.tsx:46-49`, `EvaluationPanel.tsx:65-67`) — they set an error string and keep iterating, so a subsequent `done` would overwrite the error state. Currently unreachable because the backend returns after yielding an error, but the client should not depend on that.

**`PdfPreview.tsx` as a third client.** Bypasses `api.ts` entirely (`:19`), implements its own error-body read (`:22-23` — the only correct one, P1-9), its own loading state (`:48-53`), its own error state (`:41-47`), and its own blob lifecycle (`:27-38`). No abort, no cache (P1-10).

---

# 3. Type safety

- **`any`: zero occurrences** in `frontend/src`. This is misleading — see P2-22, nine `as` casts of `unknown`.
- **Discriminated unions: missing** where they matter most (`SseEvent`, `api.ts` results). Three orphan interfaces were written for exactly this and never wired up (`types.ts:59-61`, P2-22).
- **Backend drift:** P2-23. No route has a `response_model`; no codegen; types are hand-copied.
- **Dead types:** `ChatAction` (`types.ts:54-57`), `SseProgressEvent`/`SseTokenEvent`/`SseErrorEvent` (`types.ts:59-61`). Four of the eleven exported types are unused.
- **tsconfig:** P2-24. `strict: true` but missing `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noUnusedLocals`, `noUnusedParameters`.
- **No linter at all:** P2-24.
- **Jest uses a different tsconfig** — `package.json:38-47` inlines `{ "jsx": "react-jsx" }`, overriding `tsconfig.json:18`'s `"jsx": "preserve"`. Tests therefore type-check under a slightly different config than the build, and `ts-jest` here does not enforce `strict` diagnostics on test files.
- **Typed correctly where it counts:** `ui/SegmentedControl.tsx:16` is properly generic; `ui/Button.tsx:7` extends `React.ButtonHTMLAttributes`; the `Variant`/`Size`/`Tone` `Record<>` maps (`ui/Button.tsx:12,21`, `ui/Badge.tsx:5`) are exhaustive by construction. The primitives are the best-typed part of the codebase.

---

# 4. UI/UX and visual design assessment

**Caveat, stated up front:** the screenshots in `docs/screenshots/` cannot be used to judge the current design — all eight predate the redesign and show a materially different application (P2-35). What they *are* useful for is a before/after: the redesign was real and it moved the app from "bootstrap admin panel with a bottom chat strip" to something with a point of view. The assessment below therefore reads the current source, and the verdict is that the problems remaining are execution problems, not direction problems.

### The old UI (what the screenshots actually show)
A top bar ("ResumeTailor" / "AI Resume Workstation"), three horizontal tabs, a left editor pane, and a bottom-docked collapsible "AI Chat Assistant ▼" strip that eats ~40% of vertical space and shows a mid-scroll assistant message clipped at the top. Buttons are flat grey/white rectangles. Zero accent colour. The evaluation tab is an empty right column with a textarea and a disabled grey button. It reads as scaffolding.

### The current UI (from source)

**Layout.** 76px icon rail (`Sidebar.tsx:62`) → main column → 380px chat drawer (`ChatDrawer.tsx:28`). Every panel is a 56px header (`h-14`) over a two-column split:
- Editor — 50/50, `w-1/2` each (`MasterResumePanel.tsx:100`, `:115`)
- Generate — fixed `w-[420px]` + fluid (`GenerationPanel.tsx:79`, `:138`)
- Evaluate — fixed `w-[420px]` + fluid (`EvaluationPanel.tsx:86`, `:117`)
- Library — fixed `w-[320px]` + fluid (`ResumeListPanel.tsx:69`, `:116`)

Consistent, legible, and the right shape for a workstation. The chrome is quiet and the content gets the room. This is a good skeleton.

**What is actually wrong:**

**1. Zero responsive handling.** `WorkstationShell.tsx:56` is `flex h-screen overflow-hidden` with three fixed-width columns. 76 + 420 + 380 = **876px of fixed chrome** before any content. Below ~1200px the Generate result column is unusable; below ~900px the layout breaks outright. **Not one breakpoint** (`sm:`/`md:`/`lg:`/`xl:`) appears in any component file. No mobile story, no drawer auto-collapse, no min-width guard. Additionally the editor's 50/50 split is not draggable — a resizable splitter is the first thing anyone wants in a YAML-plus-preview view, and its absence is felt immediately on a 13" screen.

**2. Four headers competing for the same job.** Sidebar labels (`Sidebar.tsx:13-16`): Editor / Generate / Resumes / Evaluate. Panel `<h1>`s: **Master Resume** (`MasterResumePanel.tsx:61`) / Generate (`GenerationPanel.tsx:72`) / **Library** (`ResumeListPanel.tsx:52`) / Evaluate (`EvaluationPanel.tsx:79`). Two of four don't match their own nav item, so the user's mental model has to hold two names for the same place. Meanwhile the product name appears nowhere on screen: just a lone letter "R" in a box (`Sidebar.tsx:63-68`) whose `title` attribute is the only place "ResumeTailor" is spelled out.

**3. Every panel header is a different shape.**
- Editor: title + mono caption + segmented control + Save + ConfirmButton (`MasterResumePanel.tsx:59-92`)
- Generate / Evaluate: title + a floating `text-xs` explainer sentence with no containment (`GenerationPanel.tsx:73-75`, `EvaluationPanel.tsx:80-82`)
- Library: title + count + segmented control (`ResumeListPanel.tsx:50-65`)

The `ml-3 text-xs text-muted-foreground` subtitle is the most generic, most templated thing in the app — it is the visual equivalent of a `<!-- TODO: description -->`.

**4. The gold is doing too little and too much at once.** One accent (`--accent: #d9a84e`, `globals.css:18`) carries: the logo (`Sidebar.tsx:64`), primary buttons (`--primary` is literally the same hex, `globals.css:30`), active nav (`Sidebar.tsx:36`), the focus ring (`globals.css:39,59`), the CodeMirror cursor and selection (`globals.css:79-81`), dashed seams (`globals.css:66`), status dots (`ChatDrawer.tsx:31`, `ChatPanel.tsx:93`), and all three empty-state icons. Because `--accent-dim` is 12% alpha (`globals.css:21`) and `.seam-dashed` is 35%, the **loudest** use (a full-gold Save button, `ui/Button.tsx:13-14`) sits beside the **quietest** (a 2:1 dashed border, P1-21) with nothing in between. Active state reads as decoration rather than signal, and the identity motif is the least visible thing on screen.

**5. Three empty states, one template, copy-pasted.** `GenerationPanel.tsx:167-177`, `ResumeListPanel.tsx:136-143`, `EvaluationPanel.tsx:161-170` are the same block three times: `seam-dashed` circle → a lucide icon at `size={18}` → `max-w-xs text-sm text-muted-foreground` sentence. Not extracted into a component and visually indistinguishable — the icon glyph is the only difference between them. This is the single most templated-looking part of the current app.

**6. Typography barely uses its own system.** Fraunces is loaded with the `opsz` optical-size axis (`layout.tsx:6-10`) — a deliberate, expensive choice — and then used at exactly **two** sizes: `text-lg` for panel titles (`MasterResumePanel.tsx:61` et al.) and `text-4xl` once on the empty state (`EmptyState.tsx:86`). Everything else is Inter at `text-sm`/`text-xs`, with heavy reliance on arbitrary micro-sizes: `text-[10px]` (`Sidebar.tsx:55`, `EvaluationPanel.tsx:41`), `text-[11px]` (`MasterResumePanel.tsx:64`, `ResumeListPanel.tsx:100`, `GenerationPanel.tsx:122`). Six sub-12px sizes. The scale has no middle register: `text-4xl` → `text-lg` → `text-sm` → `text-xs` → `text-[11px]` → `text-[10px]`. Nothing sits between the hero and the body, so no panel can establish hierarchy without reaching for colour.

**7. The `R` monogram is a placeholder.** A serif italic capital in a rounded box, rendered twice at two sizes with duplicated class strings (`Sidebar.tsx:63-68` at `h-10 w-10 rounded-lg text-xl`; `EmptyState.tsx:82-84` at `h-12 w-12 rounded-xl text-2xl`). There is no mark — conspicuous in a design whose entire concept is a tailor's thread. The `.seam-dashed` motif is *right there* and is never used as an identity element.

**8. Dead space in Generate and Evaluate.** Before a run, the left column is a textarea plus a button inside a 420px rail, and the right two-thirds of a 1200px viewport shows one centred sentence in a `max-w-xs` paragraph. The JD input — the actual subject of the page — is `rows={12}` in the *narrowest* column (`GenerationPanel.tsx:90`, `EvaluationPanel.tsx:96`). The proportions are inverted: the thing you're working on is cramped and the thing that doesn't exist yet gets the space.

**9. The copy and the score ring are the strongest things here.** "Every job deserves a *tailored* resume" (`EmptyState.tsx:86-88`), "cuts and re-stitches it to fit each job description" (`:90-92`), "Reading your resume against the role…" (`EvaluationPanel.tsx:159`), "Converting your PDF to YAML…" (`EmptyState.tsx:126`). And `ScoreRing` (`EvaluationPanel.tsx:18-45`) — a dashed stitched track under a "wound thread" arc that animates its `stroke-dashoffset` over 700ms (`:36`), with a mono numeral and a `tracking-widest` uppercase caption. It is genuinely well-made, it is the only place the concept becomes a *form* rather than a colour, and it is buried behind a run, stranded in a 175-line panel where nothing else can reuse it.

**Information architecture.** Four destinations is right. The ordering (Editor → Generate → Resumes → Evaluate) implies a workflow that the app then refuses to support: nothing links Generate's result to the Library, nothing links the Library to Evaluate, and Evaluate scores the *master* resume rather than a generated one (`EvaluationPanel.tsx:60`) — which is arguably backwards, since the thing you'd want to score is the tailored output you're about to send. `WorkstationShell.tsx:34` sets `selectedResume` on generation, but the user has to notice and navigate to Resumes themselves to see it.

---

# 5. Accessibility

Summarised from P0-5, P1-16 through P1-21, P2-30 through P2-33.

**Keyboard navigation**
- PDF import is unreachable by keyboard (P0-5, `EmptyState.tsx:109-122`).
- Resume list items are unreachable by keyboard (P1-19, `ResumeListPanel.tsx:83-91`).
- Segmented controls have no arrow-key support and no roving tabindex (P1-16, `ui/SegmentedControl.tsx:22-44`).
- No skip link anywhere (`layout.tsx`, `WorkstationShell.tsx`).
- CodeMirror's default keymap traps Tab inside the editor; no escape hatch is configured (`MasterResumePanel.tsx:102-110`, `basicSetup={{ lineNumbers: true }}`).
- `ConfirmButton` disarms on blur, so Shift-Tab loses the armed state silently (P2-33).

**Focus management**
- Global `:focus-visible` ring is correct and high-contrast (`globals.css:58-61`).
- Chat drawer: no focus move on open, no Escape, no focus restore on close (P1-20).
- No focus trap on any destructive confirmation (`ConfirmButton` is inline, not a dialog).
- `ResumeListPanel.tsx:106` — the delete button is `opacity-0` at rest but correctly reveals on `focus-visible:opacity-100`. Done right.

**ARIA**
- Tabs: broken pattern, wrong pattern (P1-16).
- Drawer: no `role`, no label (P1-20).
- Streaming chat: no `aria-live`, no `role="log"` (P1-17).
- Errors: no `role="alert"` on any of five error surfaces (P1-18).
- `aria-current="page"` on a button in a non-routing nav (P2-32).
- `ScoreRing` SVG (`EvaluationPanel.tsx:22-38`) has no `role="img"` and no `aria-label`; the score is available as text at `:40`, so it degrades acceptably, but the result region has no live announcement when it appears.
- Correct: `aria-hidden="true"` on decorative dots and the stitch (`Sidebar.tsx:50`, `ChatDrawer.tsx:31`, `ChatPanel.tsx:93,103`, `ui/Spinner.tsx:11`); `aria-pressed` on the chat toggle (`Sidebar.tsx:42`); `aria-label` on icon-only buttons (`ChatDrawer.tsx:35,38`, `ChatPanel.tsx:125`, `ResumeListPanel.tsx:105`).

**Form labels**
- Correct: `jd-input` (`GenerationPanel.tsx:81-92`), `eval-jd` (`EvaluationPanel.tsx:88-98`).
- Missing: rules inputs (P2-31, `GenerationPanel.tsx:120-131`), chat textarea (`ChatPanel.tsx:112-120` — placeholder only).

**Colour contrast** — three failures, detailed in P1-21: `--faint-foreground` ≈ 3.1:1, `--border` ≈ 1.3:1, `.seam-dashed` ≈ 2.0:1.

**Screen-reader story for the PDF preview** — a single `<iframe title="Resume PDF Preview">` over a `blob:` URL is the whole story (P2-30). The user's own resume content is unreachable as text. There is no download affordance in the editor preview, so an AT user cannot even take the file elsewhere to read it.

**Screen-reader story for streaming chat** — nothing is announced: not the arrival of tokens, not the "Thinking…" state, not completion, not errors (P1-17, P1-18). `jest.setup.ts:4` stubs `scrollIntoView`, which is the only reason `ChatPanel.tsx:25` doesn't crash in tests; that auto-scroll is also unconditional, so it fights a user who has scrolled up to read history.

**Motion** — `globals.css:83-89` honours `prefers-reduced-motion` globally. Correct, and the only fully-handled a11y concern in the app.

---

# 6. Performance

- **Bundle**: 1.1 MB of uncompressed JS chunks on a single eagerly-loaded route; CodeMirror ships to users on the onboarding screen; nothing uses `next/dynamic` (P2-25).
- **Fonts**: three families, one with a variable optical-size axis, for a design that uses the display face at two sizes (P2-25, UI item 6).
- **PDF preview**: full server-side Typst compile on every mount, no cache, no ETag, no debounce, no dedupe (P1-10). This is the dominant latency cost in the app by an order of magnitude.
- **Re-render hotspots**: `MasterResumePanel.tsx:106` — `onChange={setYaml}` re-renders the entire panel per keystroke (header, caption, `dirty` recompute at `:28`, segmented control, both column wrappers). `PdfPreview` is not `React.memo`'d, so its wrapper subtree re-renders on each keypress; the `useEffect` dep is `[pdfUrl]` so it does not refetch, but the iframe element is reconciled every time. No `React.memo`, `useMemo`, or `useDeferredValue` anywhere in the codebase. Harmless at 100 lines, noticeable on a real 500-line master resume.
- **Large YAML handling**: CodeMirror 6 virtualizes its viewport, so the editor itself scales. The non-scaling parts are the per-keystroke parent re-render above and the full-document `yaml !== resume.yaml_content` string compare on every render.
- **List**: no virtualization; capped at 20 by the hardcoded limit (P1-14), so virtualization is moot until pagination exists — but so is the library.
- **Refetch churn**: whole-list refetch after every delete (`ResumeListPanel.tsx:45`); full chat-history refetch on every drawer reopen (`ChatPanel.tsx:20-22` + `WorkstationShell.tsx:83`); rules refetch on every Generate-panel mount (`GenerationPanel.tsx:27-29`).
- **Static export constraints**: no SSR, no ISR, no server components doing data loading, no middleware, no image optimization (`next.config.js:6`, `images: { unoptimized: true }`), no route-level code splitting benefit (one route). Everything is client-side after a blank first paint — `WorkstationShell.tsx:40-49` renders a logo-and-spinner screen while `/api/master-resume` resolves, so time-to-content is bundle-parse + one round trip, every load.
- **`overflow-hidden` on the root** (`WorkstationShell.tsx:56`) with `h-screen` means no page-level scroll; each panel manages its own `overflow-y-auto`. Correct for a workstation, but `h-screen` (not `dvh`) breaks on mobile browsers with dynamic toolbars — moot today given P2-25's zero breakpoints.

---

# 7. Build and deploy

**How `frontend/out` reaches `backend/static`:** only inside Docker. `Dockerfile:4-12` builds the export in a `node:20-slim` stage; `Dockerfile:24` copies it:

```dockerfile
COPY --from=frontend-builder /build/frontend/out ./static/
```

`main.py:68-70` mounts it at `/` with `html=True` if the directory exists.

**Are build artifacts committed? No.** `.gitignore:39` ignores `frontend/out/`, `.gitignore:57` ignores `backend/static/`. `git ls-files` returns 0 entries for both paths. The brief's premise was incorrect.

**What is actually broken:**

1. **No local build path.** There is no script that builds and copies for local (non-Docker) runs. `package.json:5-10` has `dev`, `build`, `start`, `test` — no `postbuild`, no copy step. So the only way `backend/static` gets populated locally is by hand, which is exactly why both trees are **five days and two commits stale** (P1-11) and byte-identical to each other. Anyone running `uvicorn app.main:app` locally today serves a UI without the sidebar or the chat drawer, with no indication that anything is wrong.
2. **`distDir: 'out'` ships build internals** to a publicly-mounted directory (P1-12).
3. **No dev proxy.** `next dev` serves on :3000 and every API path is origin-relative (`api.ts`, Section 2), with no `rewrites` in `next.config.js` and no `NEXT_PUBLIC_API_URL`. Frontend hot-reload development against a running backend requires editing config first. This alone explains why the committed workflow is "build and copy", and why it rots.
4. **No CI.** No GitHub Actions workflow, no build/typecheck/test gate. Nothing would have caught the stale artifacts, and nothing runs `tsc --noEmit`.
5. **No cache headers.** `StaticFiles` (`main.py:70`) serves `_next/static/*` — content-hashed, immutable — with default headers. Every deploy re-downloads 1.1 MB that could be `Cache-Control: public, max-age=31536000, immutable`.
6. **`next.config.js` has no `output: 'standalone'` fallback** and the compose file (`docker-compose.yml`) has no build args, so a frontend-only change triggers a full `npm ci` unless Docker layer cache survives — `Dockerfile:6-7` does copy `package*.json` first and `npm ci` separately, which is correct.
7. **What breaks in a real deploy:** single worker (`Dockerfile:37`, `--workers 1`) serving both the API and 1.1 MB of static assets; SQLite on a Docker volume (`docker-compose.yml:8`) so no horizontal scaling; the `/` catch-all mount means any future API path collision is shadowed by `StaticFiles`; and because there is one route (P1-13), a user who bookmarks anything other than `/` gets `404.html`.

**What is done right:** multi-stage build, `npm ci` on a separate layer, `uv sync --frozen --no-dev` (`Dockerfile:21`), a real `HEALTHCHECK` (`Dockerfile:32-33`) matched by a compose healthcheck (`docker-compose.yml:12-18`), named volumes for DB and PDFs, `restart: unless-stopped`, and `env_file`. The container story is solid; the *local* story is what rots.

---

# 8. Restructure proposal

## Target layout

```
frontend/src/
  app/
    layout.tsx
    page.tsx                          # redirect → /editor
    (workstation)/
      layout.tsx                      # Sidebar + ChatDrawer shell (from WorkstationShell)
      editor/page.tsx
      generate/page.tsx
      library/page.tsx
      library/[id]/page.tsx           # generateStaticParams, or ?id= under static export
      evaluate/page.tsx
  features/
    master-resume/
      components/EditorPane.tsx
      components/PreviewPane.tsx
      components/MasterResumeHeader.tsx
      components/Onboarding.tsx
      hooks/useMasterResume.ts
      hooks/useSaveMasterResume.ts
      hooks/useMasterResumeDraft.ts   # sessionStorage-backed, fixes P0-1
      lib/sample-yaml.ts              # from EmptyState.tsx:9-35
    generation/
      components/JobDescriptionForm.tsx
      components/RulesEditor.tsx
      components/GenerationResult.tsx
      hooks/useGenerateResume.ts
      hooks/useRules.ts
    library/
      components/ResumeList.tsx
      components/ResumeCard.tsx
      components/ResumePreviewPane.tsx
      hooks/useResumes.ts
      hooks/useDeleteResume.ts
    evaluation/
      components/EvaluationForm.tsx
      components/KeywordColumns.tsx
      hooks/useEvaluate.ts
    chat/
      components/ChatDrawer.tsx
      components/MessageList.tsx
      components/MessageComposer.tsx
      hooks/useChatHistory.ts
      hooks/useChatStream.ts
  api/
    generated/types.ts                # openapi-typescript against /openapi.json
    schemas.ts                        # zod — one source for runtime + compile time
    client.ts                         # 204-aware, detail|error, typed ApiError
    sse.ts                            # discriminated union + AbortSignal
    queries.ts                        # TanStack Query keys + options
  design-system/
    tokens.css                        # from globals.css:5-40, contrast-fixed
    primitives/Button.tsx
    primitives/Badge.tsx
    primitives/Spinner.tsx
    primitives/ToggleGroup.tsx        # replaces SegmentedControl
    primitives/Dialog.tsx             # new
    primitives/Alert.tsx              # new
    primitives/Field.tsx              # new
    primitives/EmptyState.tsx         # new
    primitives/ScoreRing.tsx          # from EvaluationPanel.tsx:12-45
    patterns/PanelHeader.tsx          # new
    patterns/SplitPane.tsx            # new, resizable
    patterns/DropZone.tsx             # new, keyboard-accessible
    patterns/PdfPreview.tsx
  lib/
    cn.ts
    format.ts                         # date formatting, currently inline x3
```

## Exact file moves

| From | To | Note |
|---|---|---|
| `components/WorkstationShell.tsx` | `app/(workstation)/layout.tsx` | view state → URL segment (P1-13) |
| `components/Sidebar.tsx` | `app/(workstation)/_components/Sidebar.tsx` | buttons → `<Link>` (fixes P2-32) |
| `components/MasterResumePanel.tsx` | split → `features/master-resume/components/{EditorPane,PreviewPane,MasterResumeHeader}.tsx` + `app/(workstation)/editor/page.tsx` | |
| `components/GenerationPanel.tsx` (182 L) | split → `features/generation/components/{JobDescriptionForm,RulesEditor,GenerationResult}.tsx` + `app/(workstation)/generate/page.tsx` | three concerns, three files |
| `components/EvaluationPanel.tsx` (175 L) | `ScoreRing` + `scoreColor` (`:12-45`) → `design-system/primitives/ScoreRing.tsx`; rest → `features/evaluation/` + `app/(workstation)/evaluate/page.tsx` | |
| `components/ResumeListPanel.tsx` (148 L) | split → `features/library/components/{ResumeList,ResumeCard,ResumePreviewPane}.tsx` + `app/(workstation)/library/page.tsx` | |
| `components/ChatPanel.tsx` + `components/ChatDrawer.tsx` | `features/chat/components/{ChatDrawer,MessageList,MessageComposer}.tsx` | |
| `components/EmptyState.tsx` (153 L) | `SAMPLE_YAML` (`:9-35`) → `features/master-resume/lib/sample-yaml.ts`; drop zone (`:109-138`) → `design-system/patterns/DropZone.tsx`; rest → `features/master-resume/components/Onboarding.tsx` | |
| `components/PdfPreview.tsx` | `design-system/patterns/PdfPreview.tsx` | + abort, + cache, + text fallback |
| `components/ui/Button.tsx` | `design-system/primitives/Button.tsx` | unchanged |
| `components/ui/Badge.tsx` | `design-system/primitives/Badge.tsx` | unchanged |
| `components/ui/Spinner.tsx` | `design-system/primitives/Spinner.tsx` | unchanged |
| `components/ui/SegmentedControl.tsx` | `design-system/primitives/ToggleGroup.tsx` | rewrite ARIA (P1-16) |
| `components/ui/ConfirmButton.tsx` | `design-system/primitives/ConfirmButton.tsx` | + live region; destructive cases → `Dialog` |
| `lib/api.ts` | `api/client.ts` + `api/queries.ts` | |
| `lib/sse.ts` | `api/sse.ts` | |
| `lib/types.ts` | **deleted** | replaced by `api/generated/types.ts` + `api/schemas.ts` |
| `app/globals.css:5-40` | `design-system/tokens.css` | contrast fixes (P1-21) |
| `app/globals.css:64-89` | stays in `globals.css` | `.seam-dashed`, CodeMirror chrome, reduced-motion |
| `__tests__/*.tsx` | co-located `*.test.tsx` beside each component | |

## What to introduce, in dependency order

1. **`openapi-typescript`** against the live `/openapi.json`, after adding `response_model=` to every backend route (`resumes.py:46,149,157,180`; `rules.py:25,29,35`; `chat.py:34`; `master_resume.py:88,96`; `system_prompt.py`). Kills hand-maintained `types.ts` and P2-23 at the source. Wire as `npm run codegen` + a CI check that the generated file is current.
2. **zod schemas** (`api/schemas.ts`) derived from the generated types, parsed at the client boundary in `client.ts` and `sse.ts`. Collapses P2-22 and P2-23 together; every `as { delta: string }` cast becomes unnecessary rather than merely discouraged.
3. **A correct fetch wrapper** (`api/client.ts`):
   - `if (res.status === 204) return undefined as T` — fixes **P0-2** (three broken deletes).
   - `body.detail ?? body.error ?? res.statusText` — fixes **P1-9**.
   - throw a typed `ApiError { status, code, message }` so UI can branch on `NO_MASTER_RESUME` / `LLM_AUTH_ERROR` / `LLM_UNAVAILABLE` / `RENDER_FAILED`.
   - remove the blanket `.catch(() => null)` — 404 → `null`, everything else throws — fixes **P0-3**.
   - `NEXT_PUBLIC_API_URL` base with a `rewrites` fallback in `next.config.js`, so `next dev` works against a live backend (Build/Deploy item 3).
4. **TanStack Query** (`api/queries.ts`) — request dedupe and caching (fixes P1-10's repeated Typst compiles and P1-20's history refetch), `staleTime` on the PDF preview, `keepPreviousData` on sort (fixes **P1-15**), optimistic delete with rollback, automatic cancellation on unmount, and real `isLoading`/`isError`/`isSuccess` states so "failure renders as emptiness" (Section 1) stops being the default.
5. **`useSseStream` hook** (`api/sse.ts` + `features/*/hooks/`) — owns an `AbortController`, aborts on unmount, returns a zod-parsed discriminated union. Fixes **P0-6** and **P2-22**. Rewrite the parser: split on `/\r?\n/`, accumulate multi-line `data:` per spec, flush the trailing buffer, add a stall timeout (**P2-29**).
6. **A draft layer for the editor** — `useMasterResumeDraft` persisting to `sessionStorage`, a Next.js route-change guard, and a `beforeunload` handler. Fixes **P0-1** and **P1-7** together, and lets Generate/Evaluate warn on unsaved changes (**P1-8**).
7. **Token layer** (`design-system/tokens.css`) — move `globals.css:5-40`, fix the three contrast failures (**P1-21**): `--faint-foreground` `#5c6169` → ≥ `#767c85`, `--border` `#26282d` → ~`#3a3d44`, `.seam-dashed` alpha `0.35` → `0.55`. Add a genuine light palette or delete `next-themes` and `darkMode: "class"` and commit to dark-only (**P2-26**). Introduce a real type scale with a middle register (UI item 6) and retire the six arbitrary sub-12px sizes.
8. **Real primitives** — `ToggleGroup` with `role="radiogroup"` and arrow keys (**P1-16**); `Dialog` with a focus trap for the chat drawer and destructive confirms (**P1-20**, **P2-33**); `Alert` with `role="alert"` (**P1-18**); `Field` binding label↔input (**P2-31**); `EmptyState` (UI item 5 — deletes three copies); `PanelHeader` (UI item 3 — one shape for four panels); `DropZone` with `role="button"`, `tabIndex={0}`, and `onKeyDown` (**P0-5**); `SplitPane`, resizable (UI item 1).
9. **Pagination in the library** — read `data.total`, add page controls, stop reporting the page size as the total (**P1-14**).
10. **`next/dynamic` on CodeMirror** with an SSR-safe skeleton (**P2-25**); drop `distDir: 'out'` from `next.config.js` (**P1-12**); add a `postbuild` script copying `out` → `../backend/static` (**P1-11**); add `Cache-Control: immutable` for `_next/static` (Build/Deploy item 5).
11. **ESLint + `eslint-config-next` + `eslint-plugin-jsx-a11y` + `@typescript-eslint`**, plus tsconfig tightening (**P2-24**). `jsx-a11y` alone catches P0-5, P1-19, and P2-31 mechanically. Add `noUnusedParameters` to catch the dead `_masterResume` props (**P2-27**).
12. **CI** — `tsc --noEmit`, `lint`, `test`, `build`, and a check that `backend/static` is not stale (Build/Deploy item 4).
13. **Tests worth having** — `client.ts` (204, `detail` vs `error`, `ApiError` codes), `sse.ts` (CRLF, multi-line data, trailing partial, abort), and per-panel loading/empty/**error** states. Drop `--passWithNoTests` (`package.json:9`). Move the e2e copy constraints out of production comments into `data-testid` selectors — fix `test/e2e/07-evaluation.spec.ts:22` (`getByText("evaluate", {exact:false})`) and `test/e2e/02-master-resume.spec.ts:46` (`getByText("Preview")`), which frees `MasterResumePanel.tsx:62-67` from its "caption must not start with 's'" workaround (**P2-34**).
14. **Regenerate `docs/screenshots/`** from Playwright against the current UI, and wire it to CI so they cannot rot again (**P2-35**).

## Sequence

**3 → 1 → 2 → 5 → 4 → 6** clears every P0 except P0-4 and P0-5, and most of the P1 API/state findings with it. Then **7 → 8 → 9** (design system + the UI-section fixes), then **10 → 11 → 12** (build hygiene), then **13 → 14**.

**P0-5** (keyboard PDF import) is a 10-line fix and should be done immediately, out of band — it does not depend on anything above.

**P0-4** is a backend decision, not a frontend one: either implement tool-calling in `backend/app/routes/chat.py:39-75` so the assistant can actually write YAML, or change `ChatPanel.tsx:76-79` to stop promising it and delete the dead `onAction` wiring (`WorkstationShell.tsx:86`, `ChatDrawer.tsx:11,44`, `ChatPanel.tsx:53-58`, `types.ts:54-57`).
