/**
 * The typed API client. `import { api } from "@/lib/api"`.
 *
 * This directory replaces the three hand-written modules that were
 * `lib/api.ts`, `lib/types.ts` and `lib/sse.ts` (PLAN.md 2.2, D-40, D-42,
 * D-54, D-60). The resolution of `@/lib/api` is unchanged, which is why every
 * existing call site compiles untouched: it used to reach `lib/api.ts` and now
 * reaches `lib/api/index.ts`.
 *
 * What is where:
 *
 * * `generated/` - `openapi.json` exported from the running application's
 *   route table, and `schema.d.ts` generated from it. Both are committed
 *   build artifacts. Regenerate with `npm run api:generate`.
 * * `schemas.ts` - the zod schema for every response body, each proved equal
 *   at compile time to the generated type for the same shape.
 * * `errors.ts` - `ApiError`, and the one place that reads the three error
 *   bodies this API produces.
 * * `http.ts` - the request function, `abortable()`, query-string building.
 * * `sse.ts` - the streaming readers.
 * * `client.ts` - one function per non-streaming route.
 */

export { api } from "./client";
export {
  ApiError,
  CLIENT_ERROR_CODES,
  errorFromResponse,
  hasCode,
  isAbortError,
  type ClientErrorCode,
  type ErrorCode,
} from "./errors";
export { abortable, type RequestOptions } from "./http";
export {
  readSseStream,
  streamChat,
  streamEvaluate,
  streamTailor,
  type ChatFrame,
  type EvaluateFrame,
  type SseEvent,
  type TailorFrame,
} from "./sse";
export type {
  ChatAction,
  ChatDoneFrame,
  ChatMessage,
  ChatRequestBody,
  ChatResult,
  EvaluateDoneFrame,
  EvaluateRequestBody,
  EvaluationResult,
  GenerateDoneFrame,
  GenerateRequestBody,
  GeneratedResume,
  GenerationRule,
  Health,
  MasterResume,
  MasterResumeBody,
  ResumePage,
  ResumeSummary,
  ResumeUpdateBody,
  RulesBody,
  SortField,
  SortOrder,
  SseErrorFrame,
  SseProgressFrame,
  SseTokenFrame,
  SystemPrompt,
  SystemPromptBody,
} from "./schemas";
