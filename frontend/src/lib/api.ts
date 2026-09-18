import type {
  MasterResume, GeneratedResume, ResumeListResponse,
  ChatMessage, Rule, SystemPrompt, SortField, SortOrder,
} from "./types";

/** Error carrying the HTTP status and the backend's machine-readable `code`, when it sent one. */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// FastAPI's HTTPException emits {detail}; the custom handlers in main.py emit {error, code}.
interface ErrorBody { detail?: unknown; error?: unknown; code?: unknown }

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const body: ErrorBody | null = await res.json().catch(() => null);
    const message =
      asString(body?.detail) ?? asString(body?.error) ??
      (res.statusText || `Request failed (${res.status})`);
    throw new ApiError(message, res.status, asString(body?.code) ?? undefined);
  }
  // 204 and any other empty body: nothing to parse, and res.json() would reject.
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  // Master Resume
  // Only a genuine 404 means "no resume yet"; every other failure must reach the caller.
  getMasterResume: (): Promise<MasterResume | null> =>
    request<MasterResume>("/api/master-resume").catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
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
