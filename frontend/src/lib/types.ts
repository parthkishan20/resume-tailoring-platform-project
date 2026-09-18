/**
 * The type names the pre-2.2 UI imports, pointing at the generated contract.
 *
 * `lib/api/schemas.ts` is where a shape is now defined, and it is derived from
 * the backend's own OpenAPI document. This module exists because fourteen call
 * sites across `src/components/**` and `src/features/**` import from
 * `@/lib/types`, none of those files belongs to task 2.2, and re-pointing them
 * one by one is work for 3.1 and 3.2 as each panel is rebuilt. New code should
 * import from `@/lib/api` directly.
 *
 * Everything here is either a re-export or derived from one. Nothing is
 * declared twice, so nothing can drift.
 */

export type {
  ChatAction,
  ChatMessage,
  EvaluationResult,
  MasterResume,
  ResumePage,
  ResumeSummary,
  SortField,
  SortOrder,
  SystemPrompt,
} from "@/lib/api";

import type { ResumeSummary, ResumePage, GenerationRule } from "@/lib/api";

/**
 * A generated resume as the current UI types it, which is a list row plus an
 * optional document.
 *
 * The API has two shapes and one name here: `GET /api/resumes` returns rows
 * without `yaml_content` (the list query never selected it) and
 * `GET /api/resumes/{id}` returns one with it. The components below the
 * library type both with this one name, so `yaml_content` stays optional.
 * Splitting them is part of rebuilding the Library (task 3.2); until then
 * `ResumeSummary` and `@/lib/api`'s `GeneratedResume` are the exact pair.
 */
export type GeneratedResume = ResumeSummary & { yaml_content?: string };

/** The response of `GET /api/resumes`. `ResumePage` is the contract's name. */
export type ResumeListResponse = ResumePage;

/** One generation rule. `GenerationRule` is the contract's name. */
export type Rule = GenerationRule;

/** The two roles the application writes, for a component switching on them. */
export type ChatRole = "user" | "assistant";

export interface SseProgressEvent {
  message: string;
}
export interface SseTokenEvent {
  delta: string;
}
export interface SseErrorEvent {
  error: string;
  code: string;
}

/** Which surface the pre-2.3 shell is showing. Not an API type. */
export type View = "editor" | "generate" | "resumes" | "evaluate";
