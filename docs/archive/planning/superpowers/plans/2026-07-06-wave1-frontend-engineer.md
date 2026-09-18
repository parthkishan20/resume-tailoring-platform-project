# Frontend Engineer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Next.js 14 TypeScript static-export SPA — all panels, dark theme, SSE handling, PDF preview, and `data-testid` attributes required by the Integration Tester.

**Architecture:** Single-page app (`output: 'export'`). No server components, no routing. All panels in one page. API client calls same-origin `/api/*`. SSE streams for chat, generate, and evaluate. PDF displayed in an `<iframe>` via blob URL.

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, React Testing Library, `@codemirror/core` for YAML editor, `next-themes` for dark/light toggle

## Global Constraints

- Reference: `planning/PLAN.md §2, §7, §8`
- `output: 'export'` — no `next/server`, no API routes in the frontend
- Monochrome dark theme — `error`/`warning`/`destructive`/`success` map to **grey values**, NOT red/green/yellow
- Font: Inter (via `next/font/google`)
- All interactive elements must have `data-testid` attributes (see Task 2 for the full list)
- API client never hardcodes base URL — always relative `/api/*`
- `npm run build` must succeed and produce `frontend/out/`

## Color Tokens (exact — do not change)

```css
--background: #111212;
--foreground: #f2f3f3;
--card: #191a1a;
--popover: #191a1a;
--surface: #191a1a;
--muted: #191a1a;
--input: #191a1a;
--border: #323434;
--accent: #323434;
--primary: #f2f3f3;
--primary-foreground: #111212;
--primary-hover: #e5e6e6;
--secondary-foreground: #e5e6e6;
--accent-foreground: #e5e6e6;
--muted-foreground: #7d8282;
--error: #7d8282;       /* grey — intentional */
--warning: #979b9b;     /* grey — intentional */
--destructive: #979b9b; /* grey — intentional */
--success: #cbcdcd;     /* grey — intentional */
--ring: #f2f3f3;
```

## Required `data-testid` Attributes

These are referenced by `planning/2026-07-06-wave3-integration-tester.md`. Every attribute listed here MUST exist in the rendered HTML:

| `data-testid` | Element | Used by scenario |
|---|---|---|
| `empty-state` | Empty state container | 1 — Fresh start |
| `yaml-editor` | YAML textarea/editor | 2 — Master resume |
| `save-master-resume` | Save button | 2 — Master resume |
| `resume-preview` | Preview iframe or container | 2 — Master resume |
| `pdf-import-zone` | PDF drag-drop target | 3 — PDF upload |
| `job-description` | Job description textarea | 4 — Generation |
| `generate-button` | Generate resume button | 4 — Generation |
| `generated-resume-preview` | Iframe showing generated PDF | 4 — Generation |
| `resume-name` | Resume name element (in list) | 4 — Generation |
| `chat-input` | Chat message textarea | 5 — Chat |
| `chat-send` | Send chat button | 5 — Chat |
| `chat-message` | Individual message (multiple) | 5 — Chat |
| `resume-list` | Resume list container | 6 — Sort |
| `resume-list-item` | Individual list items | 6 — Sort |
| `sort-date` | Sort by date button | 6 — Sort |
| `sort-jd` | Sort by JD button | 6 — Sort |
| `evaluate-button` | Evaluate button | 7 — Evaluation |
| `evaluate-result` | Evaluation results container | 7 — Evaluation |
| `rules-form` | Generation rules form | 8 — Rules |

---

## File Structure

```
frontend/
├── package.json
├── tsconfig.json
├── next.config.js
├── tailwind.config.ts
├── postcss.config.js
├── src/
│   ├── app/
│   │   ├── layout.tsx         global layout + Inter font + ThemeProvider
│   │   ├── page.tsx           single page — imports WorkstationShell
│   │   └── globals.css        Tailwind + CSS variables
│   ├── components/
│   │   ├── WorkstationShell.tsx    top-level panel layout
│   │   ├── Header.tsx              app name + theme toggle
│   │   ├── MasterResumePanel.tsx   YAML editor + save + preview
│   │   ├── GenerationPanel.tsx     JD input + rules + generate button
│   │   ├── ResumeListPanel.tsx     sortable generated resumes list
│   │   ├── EvaluationPanel.tsx     score display + critique + keyword diff
│   │   ├── ChatPanel.tsx           persistent chat assistant
│   │   ├── EmptyState.tsx          first-launch guided empty state
│   │   └── PdfPreview.tsx          iframe + blob URL loader
│   ├── lib/
│   │   ├── api.ts             typed fetch wrappers for all /api/* endpoints
│   │   ├── sse.ts             SSE stream reader utility
│   │   └── types.ts           shared TypeScript interfaces
│   └── __tests__/
│       ├── MasterResumePanel.test.tsx
│       ├── ResumeListPanel.test.tsx
│       └── ChatPanel.test.tsx
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.js`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/app/globals.css`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx` (stub)

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "resumetailor-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "jest --passWithNoTests"
  },
  "dependencies": {
    "next": "14.2.5",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "next-themes": "^0.3.0",
    "@codemirror/lang-yaml": "^6.1.1",
    "@uiw/react-codemirror": "^4.23.0"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "autoprefixer": "^10.4.20",
    "postcss": "^8",
    "tailwindcss": "^3.4.1",
    "typescript": "^5",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^29.7.0",
    "@types/jest": "^29.5.12",
    "ts-jest": "^29.2.3"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create `next.config.js`**

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
};
module.exports = nextConfig;
```

- [ ] **Step 4: Create `tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: "var(--card)",
        border: "var(--border)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
          hover: "var(--primary-hover)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        input: "var(--input)",
        ring: "var(--ring)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 5: Create `postcss.config.js`**

```js
module.exports = { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 6: Create `src/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #111212;
  --foreground: #f2f3f3;
  --card: #191a1a;
  --popover: #191a1a;
  --surface: #191a1a;
  --muted: #191a1a;
  --input: #191a1a;
  --border: #323434;
  --accent: #323434;
  --primary: #f2f3f3;
  --primary-foreground: #111212;
  --primary-hover: #e5e6e6;
  --secondary-foreground: #e5e6e6;
  --accent-foreground: #e5e6e6;
  --muted-foreground: #7d8282;
  --error: #7d8282;
  --warning: #979b9b;
  --destructive: #979b9b;
  --success: #cbcdcd;
  --ring: #f2f3f3;
}

* { box-sizing: border-box; }

body {
  background-color: var(--background);
  color: var(--foreground);
  font-family: var(--font-inter), sans-serif;
  min-height: 100vh;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--background); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
```

- [ ] **Step 7: Create `src/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "ResumeTailor",
  description: "AI-powered resume tailoring workstation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} antialiased`}>{children}</body>
    </html>
  );
}
```

- [ ] **Step 8: Create stub `src/app/page.tsx`**

```tsx
export default function Home() {
  return <div className="p-4 text-foreground">ResumeTailor loading...</div>;
}
```

- [ ] **Step 9: Install and verify build**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/frontend
npm install
npm run build
```

Expected: `out/` directory created, no errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Next.js 14 scaffold with Tailwind dark theme"
```

---

## Task 2: Types and API Client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/sse.ts`

**Interfaces:**
- Produces: all TypeScript interfaces used by components; `api.*` functions called by every component

- [ ] **Step 1: Create `src/lib/types.ts`**

```ts
export interface MasterResume {
  id: number;
  user_id: string;
  yaml_content: string;
  updated_at: string;
}

export interface GeneratedResume {
  id: number;
  user_id: string;
  name: string;
  job_description: string;
  yaml_content?: string;
  pdf_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeListResponse {
  items: GeneratedResume[];
  total: number;
  page: number;
  limit: number;
}

export interface ChatMessage {
  id: number;
  user_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Rule {
  section: string;
  rule_key: string;
  rule_value: string;
}

export interface SystemPrompt {
  id: number;
  user_id: string;
  content: string;
  updated_at: string;
}

export interface EvaluationResult {
  match_score: number;
  critique: string;
  matched_keywords: string[];
  missing_keywords: string[];
}

export interface ChatAction {
  type: "resume_created" | "master_resume_updated" | "evaluation_complete" | "rules_updated";
  resume_id?: number;
}

export interface SseProgressEvent { message: string; }
export interface SseTokenEvent { delta: string; }
export interface SseErrorEvent { error: string; code: string; }

export type SortField = "date" | "jd";
export type SortOrder = "asc" | "desc";
```

- [ ] **Step 2: Create `src/lib/api.ts`**

```ts
import type {
  MasterResume, GeneratedResume, ResumeListResponse,
  ChatMessage, Rule, SystemPrompt, SortField, SortOrder,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Master Resume
  getMasterResume: () =>
    request<MasterResume | null>("/api/master-resume").catch(() => null),
  saveMasterResume: (yaml_content: string) =>
    request<MasterResume>("/api/master-resume", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml_content }),
    }),
  deleteMasterResume: () =>
    request<void>("/api/master-resume", { method: "DELETE" }),

  // Generated Resumes
  listResumes: (sort: SortField = "date", order: SortOrder = "desc", page = 1) =>
    request<ResumeListResponse>(
      `/api/resumes?sort=${sort}&order=${order}&page=${page}&limit=20`
    ),
  getResume: (id: number) =>
    request<GeneratedResume>(`/api/resumes/${id}`),
  updateResume: (id: number, patch: { name?: string; yaml_content?: string }) =>
    request<GeneratedResume>(`/api/resumes/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteResume: (id: number) =>
    request<void>(`/api/resumes/${id}`, { method: "DELETE" }),
  renderResume: (id: number) =>
    request<GeneratedResume>(`/api/resumes/${id}/render`, { method: "POST" }),

  // Chat
  getChatHistory: () => request<ChatMessage[]>("/api/chat"),
  clearChat: () => request<void>("/api/chat", { method: "DELETE" }),

  // Rules
  getRules: () => request<Rule[]>("/api/rules"),
  updateRules: (rules: Rule[]) =>
    request<Rule[]>("/api/rules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rules }),
    }),
  resetRules: () => request<Rule[]>("/api/rules", { method: "DELETE" }),

  // System Prompt
  getSystemPrompt: () => request<SystemPrompt>("/api/system-prompt"),
  updateSystemPrompt: (content: string) =>
    request<SystemPrompt>("/api/system-prompt", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),
  resetSystemPrompt: () =>
    request<SystemPrompt>("/api/system-prompt", { method: "DELETE" }),

  // PDF
  getPdfUrl: (id: number) => `/api/resumes/${id}/pdf`,

  // Import PDF (returns master resume)
  importPdf: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<MasterResume>("/api/master-resume/import", {
      method: "POST",
      body: form,
    });
  },
};
```

- [ ] **Step 3: Create `src/lib/sse.ts`**

```ts
// SSE stream reader for POST endpoints (generate, chat, evaluate)
// Returns an async generator of parsed SSE events.

export interface SseEvent {
  event: string;
  data: unknown;
}

export async function* readSseStream(
  path: string,
  body: unknown,
  signal?: AbortSignal
): AsyncGenerator<SseEvent> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error ?? res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        try {
          yield { event: currentEvent, data: JSON.parse(raw) };
        } catch {
          yield { event: currentEvent, data: raw };
        }
        currentEvent = "message";
      }
    }
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/
git commit -m "feat(frontend): types, API client, SSE reader utility"
```

---

## Task 3: Core Layout + Header + Empty State

**Files:**
- Create: `frontend/src/components/Header.tsx`
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/WorkstationShell.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create `Header.tsx`**

```tsx
"use client";
export default function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-card">
      <span className="text-lg font-semibold tracking-tight text-foreground">
        ResumeTailor
      </span>
      <span className="text-xs text-muted-foreground">AI Resume Workstation</span>
    </header>
  );
}
```

- [ ] **Step 2: Create `EmptyState.tsx`**

```tsx
"use client";
import { useRef } from "react";
import type { MasterResume } from "@/lib/types";
import { api } from "@/lib/api";

const SAMPLE_YAML = `cv:
  name: Your Name
  email: you@example.com
  phone: "+1 555 000 0000"
  location: City, State
  sections:
    education:
    - institution: Your University
      area: Computer Science
      degree: Bachelor of Science
      start_date: 2018-09
      end_date: 2022-05
    experience:
    - company: Your Company
      position: Software Engineer
      start_date: 2022-06
      end_date: present
      location: City, State
      highlights:
      - Built and shipped production features using Python and TypeScript.
      - Reduced API latency by 40 percent through caching and query optimization.
    skills:
    - label: Languages
      details: Python, TypeScript, SQL
    - label: Tools
      details: Docker, Git, FastAPI, React, PostgreSQL
`;

interface Props {
  onImport: (resume: MasterResume) => void;
  onLoadSample: (yaml: string) => void;
}

export default function EmptyState({ onImport, onLoadSample }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    if (!file.name.endsWith(".pdf")) { setError("Please upload a PDF file."); return; }
    setImporting(true);
    setError(null);
    try {
      const result = await api.importPdf(file);
      onImport(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center justify-center h-full gap-8 p-8 text-center"
    >
      <div>
        <h2 className="text-2xl font-semibold text-foreground mb-2">Welcome to ResumeTailor</h2>
        <p className="text-muted-foreground max-w-md">
          Start by creating your master resume — the single source of truth for all generated resumes.
        </p>
      </div>

      <div className="flex gap-4">
        <button
          onClick={() => onLoadSample(SAMPLE_YAML)}
          className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary-hover transition"
        >
          Start from Sample
        </button>
        <a
          href={`data:text/yaml;charset=utf-8,${encodeURIComponent(SAMPLE_YAML)}`}
          download="master-resume.yaml"
          className="px-4 py-2 border border-border text-foreground rounded hover:bg-card transition"
        >
          Download Sample YAML
        </a>
      </div>

      <div
        data-testid="pdf-import-zone"
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => fileRef.current?.click()}
        className="border-2 border-dashed border-border rounded-lg p-8 w-full max-w-md cursor-pointer hover:border-primary transition"
      >
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {importing ? (
          <p className="text-muted-foreground">Importing PDF...</p>
        ) : (
          <>
            <p className="text-foreground font-medium">Drop your existing resume PDF here</p>
            <p className="text-muted-foreground text-sm mt-1">or click to browse — AI will convert it to YAML</p>
          </>
        )}
        {error && <p className="text-error text-sm mt-2">{error}</p>}
      </div>

      <p className="text-muted-foreground text-sm">
        New to render-cv format?{" "}
        <a href="https://rendercv.com" target="_blank" rel="noopener noreferrer"
           className="underline hover:text-foreground">rendercv.com</a>
      </p>
    </div>
  );
}
```

Note: add `import { useState } from "react";` at top of EmptyState.tsx.

- [ ] **Step 3: Create `WorkstationShell.tsx`**

```tsx
"use client";
import { useState, useEffect, useCallback } from "react";
import Header from "./Header";
import EmptyState from "./EmptyState";
import MasterResumePanel from "./MasterResumePanel";
import GenerationPanel from "./GenerationPanel";
import ResumeListPanel from "./ResumeListPanel";
import EvaluationPanel from "./EvaluationPanel";
import ChatPanel from "./ChatPanel";
import type { MasterResume, GeneratedResume } from "@/lib/types";
import { api } from "@/lib/api";

type RightTab = "generate" | "history" | "evaluate";

export default function WorkstationShell() {
  const [masterResume, setMasterResume] = useState<MasterResume | null>(null);
  const [loading, setLoading] = useState(true);
  const [rightTab, setRightTab] = useState<RightTab>("generate");
  const [selectedResume, setSelectedResume] = useState<GeneratedResume | null>(null);
  const [chatOpen, setChatOpen] = useState(true);

  useEffect(() => {
    api.getMasterResume().then((r) => { setMasterResume(r); setLoading(false); });
  }, []);

  const handleImport = useCallback((r: MasterResume) => setMasterResume(r), []);
  const handleLoadSample = useCallback((yaml: string) => {
    setMasterResume({ id: 0, user_id: "default", yaml_content: yaml, updated_at: "" });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header />
      {!masterResume ? (
        <EmptyState onImport={handleImport} onLoadSample={handleLoadSample} />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Left panel: YAML editor + preview */}
          <div className="flex flex-col w-1/2 border-r border-border overflow-hidden">
            <MasterResumePanel
              resume={masterResume}
              onSave={setMasterResume}
              onDelete={() => setMasterResume(null)}
            />
          </div>
          {/* Right panel: tabbed */}
          <div className="flex flex-col flex-1 overflow-hidden">
            <div className="flex border-b border-border">
              {(["generate", "history", "evaluate"] as RightTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setRightTab(tab)}
                  className={`px-4 py-2 text-sm capitalize transition ${
                    rightTab === tab
                      ? "border-b-2 border-primary text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab === "history" ? "Resumes" : tab}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-auto">
              {rightTab === "generate" && (
                <GenerationPanel
                  masterResume={masterResume}
                  onGenerated={(r) => { setSelectedResume(r); setRightTab("history"); }}
                />
              )}
              {rightTab === "history" && (
                <ResumeListPanel
                  selected={selectedResume}
                  onSelect={setSelectedResume}
                />
              )}
              {rightTab === "evaluate" && (
                <EvaluationPanel masterResume={masterResume} />
              )}
            </div>
          </div>
        </div>
      )}
      {/* Chat panel */}
      {masterResume && (
        <div
          className={`border-t border-border transition-all ${chatOpen ? "h-64" : "h-10"}`}
        >
          <button
            onClick={() => setChatOpen((o) => !o)}
            className="w-full h-10 flex items-center px-4 text-sm text-muted-foreground hover:text-foreground"
          >
            AI Chat Assistant {chatOpen ? "▼" : "▲"}
          </button>
          {chatOpen && <ChatPanel masterResume={masterResume} onAction={setMasterResume} />}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Update `src/app/page.tsx`**

```tsx
import WorkstationShell from "@/components/WorkstationShell";

export default function Home() {
  return <WorkstationShell />;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): shell layout, header, empty state"
```

---

## Task 4: Master Resume Panel

**Files:**
- Create: `frontend/src/components/MasterResumePanel.tsx`
- Create: `frontend/src/components/PdfPreview.tsx`
- Create: `frontend/src/__tests__/MasterResumePanel.test.tsx`

- [ ] **Step 1: Create `PdfPreview.tsx`**

```tsx
"use client";
import { useState, useEffect } from "react";

interface Props {
  pdfUrl: string;
  testId?: string;
}

export default function PdfPreview({ pdfUrl, testId = "resume-preview" }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let url: string;
    fetch(pdfUrl)
      .then((r) => r.blob())
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch(() => setBlobUrl(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [pdfUrl]);

  if (!blobUrl) return (
    <div data-testid={testId} className="flex items-center justify-center h-full text-muted-foreground">
      Loading preview...
    </div>
  );
  return (
    <iframe
      data-testid={testId}
      src={blobUrl}
      className="w-full h-full border-0"
      title="Resume PDF Preview"
    />
  );
}
```

- [ ] **Step 2: Create `MasterResumePanel.tsx`**

```tsx
"use client";
import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { yaml as yamlLang } from "@codemirror/lang-yaml";
import PdfPreview from "./PdfPreview";
import type { MasterResume } from "@/lib/types";
import { api } from "@/lib/api";

interface Props {
  resume: MasterResume;
  onSave: (r: MasterResume) => void;
  onDelete: () => void;
}

export default function MasterResumePanel({ resume, onSave, onDelete }: Props) {
  const [yaml, setYaml] = useState(resume.yaml_content);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.saveMasterResume(yaml);
      onSave(updated);
      setPreviewKey((k) => k + 1);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete master resume?")) return;
    await api.deleteMasterResume();
    onDelete();
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
        <span className="text-sm font-medium text-foreground">Master Resume</span>
        <div className="flex gap-2">
          <button
            onClick={() => setShowPreview((v) => !v)}
            className="px-3 py-1 text-xs border border-border rounded hover:bg-card transition"
          >
            {showPreview ? "Editor" : "Preview"}
          </button>
          <button
            data-testid="save-master-resume"
            onClick={handleSave}
            disabled={saving}
            className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary-hover disabled:opacity-50 transition"
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            onClick={handleDelete}
            className="px-3 py-1 text-xs border border-border text-muted-foreground rounded hover:bg-card transition"
          >
            Delete
          </button>
        </div>
      </div>
      {error && <p className="px-4 py-1 text-xs text-error">{error}</p>}
      <div className="flex-1 overflow-hidden">
        {showPreview ? (
          <PdfPreview key={previewKey} pdfUrl="/api/master-resume/preview" testId="resume-preview" />
        ) : (
          <CodeMirror
            data-testid="yaml-editor"
            value={yaml}
            height="100%"
            extensions={[yamlLang()]}
            onChange={setYaml}
            theme="dark"
            basicSetup={{ lineNumbers: true }}
          />
        )}
      </div>
    </div>
  );
}
```

Note: The YAML editor `data-testid` is on the outer wrapper. CodeMirror wraps its DOM, so the Integration Tester uses `locator('[data-testid=yaml-editor]')` to find the container and then types into the inner textarea.

- [ ] **Step 3: Write unit test**

```tsx
// frontend/src/__tests__/MasterResumePanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import MasterResumePanel from "@/components/MasterResumePanel";
import { api } from "@/lib/api";

jest.mock("@/lib/api");
jest.mock("@uiw/react-codemirror", () => ({
  __esModule: true,
  default: ({ value, onChange, "data-testid": testId }: any) => (
    <textarea data-testid={testId} value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

const mockResume = {
  id: 1, user_id: "default", yaml_content: "cv:\n  name: Test", updated_at: "2026-01-01",
};

test("renders save button and calls api.saveMasterResume on click", async () => {
  (api.saveMasterResume as jest.Mock).mockResolvedValue(mockResume);
  const onSave = jest.fn();
  render(<MasterResumePanel resume={mockResume} onSave={onSave} onDelete={jest.fn()} />);
  fireEvent.click(screen.getByTestId("save-master-resume"));
  await waitFor(() => expect(api.saveMasterResume).toHaveBeenCalledWith("cv:\n  name: Test"));
  expect(onSave).toHaveBeenCalledWith(mockResume);
});
```

- [ ] **Step 4: Add jest config to `package.json`**

Add to `frontend/package.json`:

```json
"jest": {
  "testEnvironment": "jsdom",
  "transform": { "^.+\\.(ts|tsx)$": "ts-jest" },
  "moduleNameMapper": {
    "^@/(.*)$": "<rootDir>/src/$1",
    "\\.(css|less)$": "<identity-obj-proxy>"
  },
  "setupFilesAfterFramework": ["@testing-library/jest-dom"]
}
```

Also add `"identity-obj-proxy": "^3.0.0"` to devDependencies and run `npm install`.

- [ ] **Step 5: Run test**

```bash
npm test -- --testPathPattern=MasterResumePanel
```

Expected: 1 PASSED

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MasterResumePanel.tsx frontend/src/components/PdfPreview.tsx \
        frontend/src/__tests__/MasterResumePanel.test.tsx frontend/package.json
git commit -m "feat(frontend): master resume panel with YAML editor and PDF preview"
```

---

## Task 5: Generation Panel + Resume List

**Files:**
- Create: `frontend/src/components/GenerationPanel.tsx`
- Create: `frontend/src/components/ResumeListPanel.tsx`
- Create: `frontend/src/__tests__/ResumeListPanel.test.tsx`

- [ ] **Step 1: Create `GenerationPanel.tsx`**

```tsx
"use client";
import { useState } from "react";
import { readSseStream } from "@/lib/sse";
import PdfPreview from "./PdfPreview";
import type { MasterResume, GeneratedResume } from "@/lib/types";

interface Props {
  masterResume: MasterResume;
  onGenerated: (r: GeneratedResume) => void;
}

export default function GenerationPanel({ masterResume, onGenerated }: Props) {
  const [jd, setJd] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<GeneratedResume | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!jd.trim()) return;
    setGenerating(true);
    setError(null);
    setStatus("Starting...");
    setGenerated(null);
    try {
      for await (const event of readSseStream("/api/resumes/stream", { job_description: jd })) {
        if (event.event === "progress") {
          setStatus((event.data as { message: string }).message);
        } else if (event.event === "done") {
          const result = (event.data as { result: GeneratedResume }).result;
          setGenerated(result);
          onGenerated(result);
          setStatus(null);
        } else if (event.event === "error") {
          setError((event.data as { error: string }).error);
          setStatus(null);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed");
      setStatus(null);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground">Job Description</label>
        <textarea
          data-testid="job-description"
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          placeholder="Paste the full job description here..."
          rows={8}
          className="bg-input border border-border rounded p-3 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
      <button
        data-testid="generate-button"
        onClick={handleGenerate}
        disabled={generating || !jd.trim()}
        className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary-hover disabled:opacity-50 transition text-sm font-medium"
      >
        {generating ? status ?? "Generating..." : "Generate Tailored Resume"}
      </button>
      {error && <p className="text-error text-sm">{error}</p>}
      {generated && (
        <div className="flex-1 flex flex-col gap-2">
          <p data-testid="resume-name" className="text-sm font-medium text-foreground">
            {generated.name}
          </p>
          {generated.pdf_path && (
            <div className="flex-1">
              <PdfPreview
                pdfUrl={`/api/resumes/${generated.id}/pdf`}
                testId="generated-resume-preview"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `ResumeListPanel.tsx`**

```tsx
"use client";
import { useState, useEffect, useCallback } from "react";
import PdfPreview from "./PdfPreview";
import type { GeneratedResume, SortField, SortOrder } from "@/lib/types";
import { api } from "@/lib/api";

interface Props {
  selected: GeneratedResume | null;
  onSelect: (r: GeneratedResume) => void;
}

export default function ResumeListPanel({ selected, onSelect }: Props) {
  const [items, setItems] = useState<GeneratedResume[]>([]);
  const [sort, setSort] = useState<SortField>("date");
  const [order] = useState<SortOrder>("desc");
  const [loading, setLoading] = useState(true);

  const fetchList = useCallback(async (s: SortField) => {
    setLoading(true);
    const data = await api.listResumes(s, order);
    setItems(data.items);
    setLoading(false);
  }, [order]);

  useEffect(() => { fetchList(sort); }, [sort, fetchList]);

  async function handleDelete(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    await api.deleteResume(id);
    fetchList(sort);
  }

  return (
    <div className="flex h-full">
      <div className="w-64 flex flex-col border-r border-border overflow-hidden">
        <div className="flex gap-1 p-2 border-b border-border">
          <button
            data-testid="sort-date"
            onClick={() => setSort("date")}
            className={`flex-1 px-2 py-1 text-xs rounded transition ${sort === "date" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-card"}`}
          >
            By Date
          </button>
          <button
            data-testid="sort-jd"
            onClick={() => setSort("jd")}
            className={`flex-1 px-2 py-1 text-xs rounded transition ${sort === "jd" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-card"}`}
          >
            By JD
          </button>
        </div>
        <div data-testid="resume-list" className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="p-4 text-xs text-muted-foreground">Loading...</p>
          ) : items.length === 0 ? (
            <p className="p-4 text-xs text-muted-foreground">No resumes yet.</p>
          ) : (
            items.map((r) => (
              <div
                key={r.id}
                data-testid="resume-list-item"
                onClick={() => onSelect(r)}
                className={`p-3 border-b border-border cursor-pointer hover:bg-card transition ${selected?.id === r.id ? "bg-card" : ""}`}
              >
                <p data-testid="resume-name" className="text-sm text-foreground truncate">{r.name}</p>
                <p className="text-xs text-muted-foreground truncate mt-0.5">{r.job_description.slice(0, 60)}</p>
                <div className="flex justify-between items-center mt-1">
                  <span className="text-xs text-muted-foreground">
                    {new Date(r.created_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={(e) => handleDelete(r.id, e)}
                    className="text-xs text-muted-foreground hover:text-error"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
      <div className="flex-1">
        {selected?.pdf_path ? (
          <PdfPreview pdfUrl={`/api/resumes/${selected.id}/pdf`} testId="generated-resume-preview" />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Select a resume to preview
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write unit test for ResumeListPanel**

```tsx
// frontend/src/__tests__/ResumeListPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import ResumeListPanel from "@/components/ResumeListPanel";
import { api } from "@/lib/api";

jest.mock("@/lib/api");
jest.mock("@/components/PdfPreview", () => () => <div data-testid="pdf-preview-mock" />);

const mockItems = [
  { id: 1, user_id: "default", name: "Resume A", job_description: "JD A", pdf_path: "1.pdf", created_at: "2026-01-02T00:00:00", updated_at: "2026-01-02T00:00:00" },
  { id: 2, user_id: "default", name: "Resume B", job_description: "JD B", pdf_path: "2.pdf", created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00" },
];

test("renders resume list items", async () => {
  (api.listResumes as jest.Mock).mockResolvedValue({ items: mockItems, total: 2, page: 1, limit: 20 });
  render(<ResumeListPanel selected={null} onSelect={jest.fn()} />);
  await waitFor(() => expect(screen.getAllByTestId("resume-list-item")).toHaveLength(2));
});

test("sort buttons call api with correct sort field", async () => {
  (api.listResumes as jest.Mock).mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 });
  render(<ResumeListPanel selected={null} onSelect={jest.fn()} />);
  fireEvent.click(screen.getByTestId("sort-jd"));
  await waitFor(() => expect(api.listResumes).toHaveBeenCalledWith("jd", "desc"));
});
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/frontend
npm test -- --testPathPattern=ResumeListPanel
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/GenerationPanel.tsx frontend/src/components/ResumeListPanel.tsx \
        frontend/src/__tests__/ResumeListPanel.test.tsx
git commit -m "feat(frontend): generation panel, resume list with sort controls"
```

---

## Task 6: Chat Panel + Evaluation Panel

**Files:**
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/components/EvaluationPanel.tsx`
- Create: `frontend/src/__tests__/ChatPanel.test.tsx`

- [ ] **Step 1: Create `ChatPanel.tsx`**

```tsx
"use client";
import { useState, useEffect, useRef } from "react";
import { readSseStream } from "@/lib/sse";
import { api } from "@/lib/api";
import type { ChatMessage, MasterResume } from "@/lib/types";

interface Props {
  masterResume: MasterResume;
  onAction: (r: MasterResume) => void;
}

export default function ChatPanel({ masterResume, onAction }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getChatHistory().then(setMessages);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    if (!input.trim() || sending) return;
    const userMsg = input.trim();
    setInput("");
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), user_id: "default", role: "user", content: userMsg, created_at: new Date().toISOString() },
    ]);
    let assistantText = "";
    try {
      for await (const event of readSseStream("/api/chat/stream", { message: userMsg })) {
        if (event.event === "token") {
          assistantText += (event.data as { delta: string }).delta;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.id < 0) {
              return [...prev.slice(0, -1), { ...last, content: assistantText }];
            }
            return [
              ...prev,
              { id: -1, user_id: "default", role: "assistant", content: assistantText, created_at: new Date().toISOString() },
            ];
          });
        } else if (event.event === "done") {
          const result = event.data as { result: { text: string; action: unknown } };
          // Refresh master resume if action indicates update
          if ((result.result?.action as { type?: string })?.type === "master_resume_updated") {
            api.getMasterResume().then((r) => r && onAction(r));
          }
        }
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {messages.map((m, i) => (
          <div
            key={i}
            data-testid="chat-message"
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-xs rounded px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-card text-foreground border border-border"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="flex gap-2 p-2 border-t border-border">
        <textarea
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Ask the AI assistant..."
          rows={2}
          className="flex-1 bg-input border border-border rounded px-3 py-2 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <button
          data-testid="chat-send"
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="px-3 py-2 bg-primary text-primary-foreground rounded hover:bg-primary-hover disabled:opacity-50 transition text-sm"
        >
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `EvaluationPanel.tsx`**

```tsx
"use client";
import { useState } from "react";
import { readSseStream } from "@/lib/sse";
import type { MasterResume, EvaluationResult } from "@/lib/types";

interface Props { masterResume: MasterResume; }

export default function EvaluationPanel({ masterResume }: Props) {
  const [jd, setJd] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleEvaluate() {
    if (!jd.trim()) return;
    setEvaluating(true);
    setError(null);
    setResult(null);
    try {
      for await (const event of readSseStream("/api/evaluate/stream", {
        yaml_content: masterResume.yaml_content,
        job_description: jd,
      })) {
        if (event.event === "done") {
          setResult((event.data as { result: EvaluationResult }).result);
        } else if (event.event === "error") {
          setError((event.data as { error: string }).error);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground">Job Description to Evaluate Against</label>
        <textarea
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          placeholder="Paste the job description..."
          rows={6}
          className="bg-input border border-border rounded p-3 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
      <button
        data-testid="evaluate-button"
        onClick={handleEvaluate}
        disabled={evaluating || !jd.trim()}
        className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary-hover disabled:opacity-50 transition text-sm font-medium"
      >
        {evaluating ? "Evaluating..." : "Evaluate Resume"}
      </button>
      {error && <p className="text-error text-sm">{error}</p>}
      {result && (
        <div data-testid="evaluate-result" className="flex flex-col gap-3 overflow-y-auto">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-foreground">{result.match_score}%</span>
            <span className="text-sm text-muted-foreground">ATS keyword match</span>
          </div>
          <p className="text-sm text-foreground">{result.critique}</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-medium text-success mb-1">Matched Keywords</p>
              <div className="flex flex-wrap gap-1">
                {result.matched_keywords.map((k) => (
                  <span key={k} className="px-2 py-0.5 text-xs bg-card border border-border rounded text-success">{k}</span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-warning mb-1">Missing Keywords</p>
              <div className="flex flex-wrap gap-1">
                {result.missing_keywords.map((k) => (
                  <span key={k} className="px-2 py-0.5 text-xs bg-card border border-border rounded text-warning">{k}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write chat unit test**

```tsx
// frontend/src/__tests__/ChatPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import ChatPanel from "@/components/ChatPanel";
import { api } from "@/lib/api";
import * as sse from "@/lib/sse";

jest.mock("@/lib/api");
jest.mock("@/lib/sse");

const mockResume = { id: 1, user_id: "default", yaml_content: "cv:\n  name: Test", updated_at: "" };

test("renders chat input and send button", async () => {
  (api.getChatHistory as jest.Mock).mockResolvedValue([]);
  render(<ChatPanel masterResume={mockResume} onAction={jest.fn()} />);
  await waitFor(() => expect(screen.getByTestId("chat-input")).toBeInTheDocument());
  expect(screen.getByTestId("chat-send")).toBeInTheDocument();
});

test("displays message after send", async () => {
  (api.getChatHistory as jest.Mock).mockResolvedValue([]);
  async function* mockStream() {
    yield { event: "token", data: { delta: "Hello!" } };
    yield { event: "done", data: { result: { text: "Hello!", action: null } } };
  }
  (sse.readSseStream as jest.Mock).mockReturnValue(mockStream());
  render(<ChatPanel masterResume={mockResume} onAction={jest.fn()} />);
  await waitFor(() => screen.getByTestId("chat-input"));
  fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Hi" } });
  fireEvent.click(screen.getByTestId("chat-send"));
  await waitFor(() => expect(screen.getAllByTestId("chat-message").length).toBeGreaterThan(0));
});
```

- [ ] **Step 4: Run all tests**

```bash
npm test
```

Expected: all PASSED

- [ ] **Step 5: Final build check**

```bash
npm run build
```

Expected: `out/` directory produced, no build errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): chat panel, evaluation panel, all tests pass — Wave 1 frontend complete"
```

---

## Task 7: Rules Form (in GenerationPanel)

**Files:**
- Modify: `frontend/src/components/GenerationPanel.tsx` — add collapsible rules section

- [ ] **Step 1: Add rules form to GenerationPanel**

Add inside `GenerationPanel.tsx` below the generate button:

```tsx
// Add to GenerationPanel.tsx imports:
import { useEffect, useState as useStateRules } from "react"; // already imported
import type { Rule } from "@/lib/types";

// Add inside component (after existing state):
const [rules, setRules] = useState<Rule[]>([]);
const [rulesOpen, setRulesOpen] = useState(false);

useEffect(() => {
  api.getRules().then(setRules);
}, []);

async function handleRuleChange(section: string, key: string, value: string) {
  const updated = await api.updateRules([{ section, rule_key: key, rule_value: value }]);
  setRules(updated);
}
```

Add JSX below the error display and before generated preview:

```tsx
<div>
  <button
    onClick={() => setRulesOpen((o) => !o)}
    className="text-xs text-muted-foreground hover:text-foreground"
  >
    Generation Rules {rulesOpen ? "▲" : "▼"}
  </button>
  {rulesOpen && (
    <form data-testid="rules-form" className="mt-2 grid grid-cols-2 gap-2">
      {rules.map((r) => (
        <div key={`${r.section}-${r.rule_key}`} className="flex flex-col gap-0.5">
          <label className="text-xs text-muted-foreground">{r.section} / {r.rule_key}</label>
          <input
            type="number"
            defaultValue={r.rule_value}
            onBlur={(e) => handleRuleChange(r.section, r.rule_key, e.target.value)}
            className="bg-input border border-border rounded px-2 py-1 text-xs text-foreground w-full"
          />
        </div>
      ))}
    </form>
  )}
</div>
```

- [ ] **Step 2: Build check**

```bash
npm run build
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/GenerationPanel.tsx
git commit -m "feat(frontend): generation rules form — Wave 1 frontend complete"
```

---

**Definition of done:** `npm run build` produces `frontend/out/` without errors. `npm test` — all tests pass. All `data-testid` attributes from the required list exist in the components.
