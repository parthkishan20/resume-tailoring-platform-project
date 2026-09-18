/**
 * Runtime schemas for every response body, and the proof they match the server.
 *
 * D-60 and D-40's shared root cause: the old client did
 * `JSON.parse(text) as T` and the hand-written `T` was checked by nobody, on
 * either side. A renamed column, a `null` where a string was expected, or a
 * 200 from a proxy that is not this API at all reached a React component as if
 * it were the declared type, and the failure surfaced three layers away as
 * "cannot read property of undefined".
 *
 * Two mechanisms, and the second is the one that keeps the first honest:
 *
 * 1. **zod validates at the boundary.** Nothing in this module is trusted
 *    because it came over HTTP; `http.ts` parses every body through the schema
 *    for that route and throws a `RESPONSE_SHAPE_INVALID` `ApiError` if it does
 *    not fit. Objects strip unknown keys rather than rejecting them, so a
 *    server that adds a field does not break a deployed client.
 *
 * 2. **TypeScript proves each schema equals the generated type.** The schemas
 *    below are hand-written, so on their own they would be a second,
 *    unverified copy of the contract: exactly the problem being fixed. The
 *    `contractIsInSync` block at the bottom compares each `z.infer` against
 *    the matching type in `generated/schema.d.ts`, which comes from the
 *    backend's own OpenAPI document. If the backend changes a field and the
 *    types are regenerated, `tsc` fails here and names the schema to fix.
 *
 * The generated types are the source of truth for *shape*. These schemas are
 * the source of truth for *what arrives at runtime*. Keeping both, and proving
 * they agree, is what makes either one worth anything.
 */

import { z } from "zod";

import type { components, operations } from "./generated/schema";

type Schemas = components["schemas"];

// -- response bodies --------------------------------------------------------

export const healthSchema = z.object({
  status: z.literal("ok"),
});

export const masterResumeSchema = z.object({
  id: z.number(),
  user_id: z.string(),
  yaml_content: z.string(),
  updated_at: z.string(),
});

export const generatedResumeSchema = z.object({
  id: z.number(),
  user_id: z.string(),
  name: z.string(),
  job_description: z.string(),
  yaml_content: z.string(),
  pdf_path: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

/**
 * A library row. No `yaml_content`: the list query never selected it, which is
 * the one place the list shape and the detail shape genuinely differ.
 */
export const resumeSummarySchema = z.object({
  id: z.number(),
  user_id: z.string(),
  name: z.string(),
  job_description: z.string(),
  pdf_path: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const resumePageSchema = z.object({
  items: z.array(resumeSummarySchema),
  total: z.number(),
  page: z.number(),
  limit: z.number(),
});

/**
 * `role` is `string`, not `"user" | "assistant"`.
 *
 * That is what the server declares (`db/models.py` types the column as `str`),
 * and narrowing it here would mean a row written by anything else crashing the
 * transcript instead of rendering. The two roles the app writes are in
 * `lib/types.ts`'s `ChatRole`, for components that want to switch on them.
 */
export const chatMessageSchema = z.object({
  id: z.number(),
  user_id: z.string(),
  role: z.string(),
  content: z.string(),
  created_at: z.string(),
});

export const generationRuleSchema = z.object({
  section: z.string(),
  rule_key: z.string(),
  rule_value: z.string(),
});

export const systemPromptSchema = z.object({
  id: z.number(),
  user_id: z.string(),
  content: z.string(),
  updated_at: z.string(),
});

export const evaluationResultSchema = z.object({
  match_score: z.number(),
  critique: z.string(),
  matched_keywords: z.array(z.string()),
  missing_keywords: z.array(z.string()),
});

export const chatMessageListSchema = z.array(chatMessageSchema);
export const generationRuleListSchema = z.array(generationRuleSchema);

// -- server-sent event frames ----------------------------------------------

export const sseProgressFrameSchema = z.object({ message: z.string() });
export const sseTokenFrameSchema = z.object({ delta: z.string() });
export const sseErrorFrameSchema = z.object({ error: z.string(), code: z.string() });

export const chatActionSchema = z.object({
  type: z.string(),
  resume_id: z.number().nullable(),
});

export const chatResultSchema = z.object({
  text: z.string(),
  action: chatActionSchema.nullable(),
});

export const chatDoneFrameSchema = z.object({ result: chatResultSchema });
export const generateDoneFrameSchema = z.object({ result: generatedResumeSchema });
export const evaluateDoneFrameSchema = z.object({ result: evaluationResultSchema });

// -- types -----------------------------------------------------------------

export type Health = z.infer<typeof healthSchema>;
export type MasterResume = z.infer<typeof masterResumeSchema>;
export type GeneratedResume = z.infer<typeof generatedResumeSchema>;
export type ResumeSummary = z.infer<typeof resumeSummarySchema>;
export type ResumePage = z.infer<typeof resumePageSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type GenerationRule = z.infer<typeof generationRuleSchema>;
export type SystemPrompt = z.infer<typeof systemPromptSchema>;
export type EvaluationResult = z.infer<typeof evaluationResultSchema>;

export type SseProgressFrame = z.infer<typeof sseProgressFrameSchema>;
export type SseTokenFrame = z.infer<typeof sseTokenFrameSchema>;
export type SseErrorFrame = z.infer<typeof sseErrorFrameSchema>;
export type ChatAction = z.infer<typeof chatActionSchema>;
export type ChatResult = z.infer<typeof chatResultSchema>;
export type ChatDoneFrame = z.infer<typeof chatDoneFrameSchema>;
export type GenerateDoneFrame = z.infer<typeof generateDoneFrameSchema>;
export type EvaluateDoneFrame = z.infer<typeof evaluateDoneFrameSchema>;

// -- request bodies and query parameters ------------------------------------
//
// Taken straight from the generated types rather than re-declared: a request
// body is validated by the server, so there is nothing for zod to add, and the
// only thing worth having is the compiler refusing to send the wrong shape.

export type MasterResumeBody = Schemas["MasterResumeBody"];
export type GenerateRequestBody = Schemas["GenerateRequest"];
export type EvaluateRequestBody = Schemas["EvaluateRequest"];
export type ChatRequestBody = Schemas["ChatRequest"];
export type ResumeUpdateBody = Schemas["ResumeUpdate"];
export type RulesBody = Schemas["RulesBody"];
export type SystemPromptBody = Schemas["SystemPromptBody"];

type ListResumesQuery = NonNullable<
  operations["list_generated_api_resumes_get"]["parameters"]["query"]
>;

/** `"date" | "jd"`, from the route's own `Literal`. D-10. */
export type SortField = NonNullable<ListResumesQuery["sort"]>;
/** `"asc" | "desc"`, from the route's own `Literal`. D-10. */
export type SortOrder = NonNullable<ListResumesQuery["order"]>;

// -- the proof -------------------------------------------------------------

/**
 * `true` only when `A` and `B` are the same type, not merely compatible.
 *
 * Mutual `extends` is not enough: `{a: string}` and `{a: string; b?: number}`
 * each extend the other in one direction and would pass. Comparing two
 * identical generic signatures makes the compiler use its own type identity
 * check, which is the strictest thing available from inside the type system.
 */
type Exact<A, B> =
  (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;

/**
 * Every schema above, checked against the type generated from the backend's
 * OpenAPI document.
 *
 * A mismatch is a compile error naming the property, which is the whole point:
 * `npm run typecheck` is where a contract change gets noticed, not a user's
 * browser. Regenerate with `npm run api:generate` after any backend change to
 * a response shape, then fix whatever this block reports.
 */
const contractIsInSync: {
  health: Exact<Health, Schemas["HealthResponse"]>;
  masterResume: Exact<MasterResume, Schemas["MasterResume"]>;
  generatedResume: Exact<GeneratedResume, Schemas["GeneratedResume"]>;
  resumeSummary: Exact<ResumeSummary, Schemas["ResumeSummary"]>;
  resumePage: Exact<ResumePage, Schemas["ResumePage"]>;
  chatMessage: Exact<ChatMessage, Schemas["ChatMessage"]>;
  generationRule: Exact<GenerationRule, Schemas["GenerationRule"]>;
  systemPrompt: Exact<SystemPrompt, Schemas["SystemPrompt"]>;
  evaluationResult: Exact<EvaluationResult, Schemas["EvaluationResult"]>;
  sseProgressFrame: Exact<SseProgressFrame, Schemas["SseProgressFrame"]>;
  sseTokenFrame: Exact<SseTokenFrame, Schemas["SseTokenFrame"]>;
  sseErrorFrame: Exact<SseErrorFrame, Schemas["SseErrorFrame"]>;
  chatAction: Exact<ChatAction, Schemas["ChatAction"]>;
  chatResult: Exact<ChatResult, Schemas["ChatResult"]>;
  chatDoneFrame: Exact<ChatDoneFrame, Schemas["ChatDoneFrame"]>;
  generateDoneFrame: Exact<GenerateDoneFrame, Schemas["GenerateDoneFrame"]>;
  evaluateDoneFrame: Exact<EvaluateDoneFrame, Schemas["EvaluateDoneFrame"]>;
} = {
  health: true,
  masterResume: true,
  generatedResume: true,
  resumeSummary: true,
  resumePage: true,
  chatMessage: true,
  generationRule: true,
  systemPrompt: true,
  evaluationResult: true,
  sseProgressFrame: true,
  sseTokenFrame: true,
  sseErrorFrame: true,
  chatAction: true,
  chatResult: true,
  chatDoneFrame: true,
  generateDoneFrame: true,
  evaluateDoneFrame: true,
};

/**
 * Exported so the block above is not dead code that a bundler or a future
 * `noUnusedLocals` could remove along with the check it performs.
 */
export const CONTRACT_IN_SYNC = contractIsInSync;
