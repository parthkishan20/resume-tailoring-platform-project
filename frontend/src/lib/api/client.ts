/**
 * The typed client. One function per route, each cancellable and validated.
 *
 * Replaces the 112-line hand-written `lib/api.ts`. The method names and
 * argument order are unchanged, deliberately: `features/queries.ts` and eight
 * components call these, none of them is this task's file, and a client that
 * cannot be dropped in is a client nobody adopts. What changed is underneath
 * each one:
 *
 * * the response is parsed by a zod schema and the schema is proved equal to
 *   the type generated from the backend's OpenAPI document (`schemas.ts`);
 * * every function takes an optional `signal` and cancels when it aborts
 *   (D-40);
 * * every failure arrives as an `ApiError` with the server's `code` on it,
 *   whichever of the three error bodies the server sent (D-42).
 *
 * The streaming routes are in `sse.ts`, not here: their result is a sequence
 * of frames rather than a response.
 */

import { ApiError } from "./errors";
import { bare, jsonBody, query, requestJson, requestNoContent, type RequestOptions } from "./http";
import {
  chatMessageListSchema,
  generatedResumeSchema,
  generationRuleListSchema,
  healthSchema,
  masterResumeSchema,
  resumePageSchema,
  systemPromptSchema,
  type ChatMessage,
  type GeneratedResume,
  type GenerationRule,
  type Health,
  type MasterResume,
  type ResumePage,
  type ResumeUpdateBody,
  type SortField,
  type SortOrder,
  type SystemPrompt,
} from "./schemas";

/** The page size the library asks for. The route caps it at 100 (D-10). */
const PAGE_SIZE = 20;

export const api = {
  /** Liveness. Says nothing about the database or the provider. */
  getHealth: (options?: RequestOptions): Promise<Health> =>
    requestJson("/api/health", healthSchema, bare("GET", options)),

  /**
   * The master document, or `null` when the user has not imported one.
   *
   * `null` is a real value and only a 404 produces it. Every other failure
   * rejects, so a backend outage can never be rendered as "you have no
   * resume" and route the user into onboarding (D-32).
   */
  getMasterResume: (options?: RequestOptions): Promise<MasterResume | null> =>
    requestJson("/api/master-resume", masterResumeSchema, bare("GET", options)).catch(
      (cause: unknown) => {
        if (cause instanceof ApiError && cause.status === 404) return null;
        throw cause;
      },
    ),

  saveMasterResume: (yaml_content: string, options?: RequestOptions): Promise<MasterResume> =>
    requestJson(
      "/api/master-resume",
      masterResumeSchema,
      jsonBody({ yaml_content }, "PUT", options),
    ),

  deleteMasterResume: (options?: RequestOptions): Promise<void> =>
    requestNoContent("/api/master-resume", bare("DELETE", options)),

  /** Import a PDF and replace the master document with what was read out of it. */
  importPdf: (file: File, options?: RequestOptions): Promise<MasterResume> => {
    const form = new FormData();
    form.append("file", file);
    // No Content-Type header: the browser has to set the multipart boundary.
    return requestJson("/api/master-resume/import", masterResumeSchema, {
      method: "POST",
      body: form,
      signal: options?.signal,
    });
  },

  listResumes: (
    sort: SortField = "date",
    order: SortOrder = "desc",
    page = 1,
    options?: RequestOptions,
  ): Promise<ResumePage> =>
    requestJson(
      `/api/resumes${query({ sort, order, page, limit: PAGE_SIZE })}`,
      resumePageSchema,
      bare("GET", options),
    ),

  getResume: (id: number, options?: RequestOptions): Promise<GeneratedResume> =>
    requestJson(`/api/resumes/${id}`, generatedResumeSchema, bare("GET", options)),

  updateResume: (
    id: number,
    patch: ResumeUpdateBody,
    options?: RequestOptions,
  ): Promise<GeneratedResume> =>
    requestJson(`/api/resumes/${id}`, generatedResumeSchema, jsonBody(patch, "PATCH", options)),

  deleteResume: (id: number, options?: RequestOptions): Promise<void> =>
    requestNoContent(`/api/resumes/${id}`, bare("DELETE", options)),

  /** Re-render a stored resume's PDF from its current YAML. */
  renderResume: (id: number, options?: RequestOptions): Promise<GeneratedResume> =>
    requestJson(`/api/resumes/${id}/render`, generatedResumeSchema, bare("POST", options)),

  /**
   * A page of the transcript, oldest first.
   *
   * `limit` bounds the page; `beforeId` pages backward from there (the id of
   * the oldest message already held). Neither given returns the whole
   * transcript, unchanged from before B-07.
   */
  getChatHistory: (
    params?: { limit?: number; beforeId?: number },
    options?: RequestOptions,
  ): Promise<ChatMessage[]> =>
    requestJson(
      `/api/chat${query({ limit: params?.limit, before_id: params?.beforeId })}`,
      chatMessageListSchema,
      bare("GET", options),
    ),

  clearChat: (options?: RequestOptions): Promise<void> =>
    requestNoContent("/api/chat", bare("DELETE", options)),

  getRules: (options?: RequestOptions): Promise<GenerationRule[]> =>
    requestJson("/api/rules", generationRuleListSchema, bare("GET", options)),

  updateRules: (rules: GenerationRule[], options?: RequestOptions): Promise<GenerationRule[]> =>
    requestJson("/api/rules", generationRuleListSchema, jsonBody({ rules }, "PUT", options)),

  resetRules: (options?: RequestOptions): Promise<GenerationRule[]> =>
    requestJson("/api/rules", generationRuleListSchema, bare("DELETE", options)),

  getSystemPrompt: (options?: RequestOptions): Promise<SystemPrompt> =>
    requestJson("/api/system-prompt", systemPromptSchema, bare("GET", options)),

  updateSystemPrompt: (content: string, options?: RequestOptions): Promise<SystemPrompt> =>
    requestJson("/api/system-prompt", systemPromptSchema, jsonBody({ content }, "PUT", options)),

  resetSystemPrompt: (options?: RequestOptions): Promise<SystemPrompt> =>
    requestJson("/api/system-prompt", systemPromptSchema, bare("DELETE", options)),

  /**
   * The URL of a stored PDF, for an `<iframe>` or an `<object>`.
   *
   * Not a request: the browser fetches it. A caller that needs the bytes, and
   * therefore cancellation and an error envelope, should fetch this path
   * itself with a signal.
   */
  getPdfUrl: (id: number): string => `/api/resumes/${id}/pdf`,
};
