"use client";

import { useCallback } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type UseInfiniteQueryResult,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { LLMUsage, ResumeUpdateBody } from "@/lib/api";
import type {
  ChatMessage,
  GeneratedResume,
  MasterResume,
  ResumeListResponse,
  Rule,
  SortField,
  SortOrder,
  SystemPrompt,
} from "@/lib/types";

/**
 * Server state for the workspace shell.
 *
 * KEY CONVENTION. Every key is built here and nowhere else, so an
 * invalidation can never miss a cache entry because two call sites spelled the
 * same key differently. The shape is
 *
 *     [<resource>]                       a singleton
 *     [<resource>, <scope>]              a collection or sub-resource
 *     [<resource>, <scope>, <params>]    a parameterised view of one
 *
 * with `<resource>` matching the API path segment it comes from. Concretely:
 *
 *     ["master-resume"]                            the master document
 *     ["resumes", "list", { sort, order, page }]    a page of the library
 *     ["resumes", "detail", id]                     one generated resume
 *     ["rules"]                                    generation rules
 *     ["system-prompt"]                            the assistant prompt
 *     ["chat", "history"]                          the transcript
 *
 * Tasks 3.1 and 3.2 add to this file rather than calling `useQuery` with an
 * inline key. Invalidate the widest prefix that is still correct:
 * `queryKeys.resumes.all` after a generate or a delete, the exact list key
 * only when the page is known not to have moved.
 *
 * CANCELLATION. Every `queryFn` below takes the `signal` TanStack Query hands
 * it and passes it to the client, which is the half of D-40 that belongs to
 * the query layer: a query that is still in flight when its component
 * unmounts, or when a refetch supersedes it, is aborted instead of running to
 * completion and resolving into a cache nobody is reading. Mutations do not
 * get one, because TanStack does not supply one: a mutation the user has
 * already committed to should finish.
 */
export const queryKeys = {
  masterResume: ["master-resume"] as const,
  resumes: {
    all: ["resumes"] as const,
    list: (params: ResumeListParams) => ["resumes", "list", params] as const,
    detail: (id: number) => ["resumes", "detail", id] as const,
  },
  rules: ["rules"] as const,
  systemPrompt: ["system-prompt"] as const,
  chatHistory: ["chat", "history"] as const,
  llmUsage: ["llm-usage"] as const,
};

export interface ResumeListParams {
  sort: SortField;
  order: SortOrder;
  page: number;
}

export const DEFAULT_RESUME_LIST_PARAMS: ResumeListParams = {
  sort: "date",
  order: "desc",
  page: 1,
};

/**
 * The master document. `null` is a real, expected value: it means the user has
 * not imported one yet, and it is what routes the shell to onboarding. Any
 * other failure rejects, so a backend outage can never be rendered as "you
 * have no resume" (D-32, closed in task 0.2 and preserved here).
 */
export function useMasterResume(): UseQueryResult<MasterResume | null> {
  return useQuery({
    queryKey: queryKeys.masterResume,
    queryFn: ({ signal }) => api.getMasterResume({ signal }),
  });
}

export function useSaveMasterResume(): UseMutationResult<MasterResume, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (yaml: string) => api.saveMasterResume(yaml),
    onSuccess: (saved) => {
      client.setQueryData(queryKeys.masterResume, saved);
    },
  });
}

export function useDeleteMasterResume(): UseMutationResult<void, Error, void> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.deleteMasterResume(),
    onSuccess: () => {
      client.setQueryData(queryKeys.masterResume, null);
    },
  });
}

/**
 * A page of the library. The shell reads `total` from here rather than
 * counting the rows it happens to hold, which is the half of D-45 that is a
 * cache-shape problem rather than a UI one; the pagination controls are task
 * 3.2's.
 */
export function useResumeList(
  params: ResumeListParams = DEFAULT_RESUME_LIST_PARAMS,
): UseQueryResult<ResumeListResponse> {
  return useQuery({
    queryKey: queryKeys.resumes.list(params),
    queryFn: ({ signal }) => api.listResumes(params.sort, params.order, params.page, { signal }),
  });
}

/**
 * One generated resume, with `yaml_content`. `useResumeList` rows never carry
 * it (the list query does not select it), so opening a document for editing
 * needs this second fetch. Gated the same way `useSystemPrompt` is: pass
 * `enabled: false` and a placeholder id while nothing is selected.
 */
export function useResume(id: number, enabled = true): UseQueryResult<GeneratedResume> {
  return useQuery({
    queryKey: queryKeys.resumes.detail(id),
    queryFn: ({ signal }) => api.getResume(id, { signal }),
    enabled,
  });
}

/**
 * `useResume` for a nullable id, for callers (Evaluate) that don't already
 * hold an explicit enabled flag: `-1` is never a real id, so the query key
 * stays derivable and `enabled` collapses to a single `id !== null` check.
 */
export function useResumeDetail(id: number | null): UseQueryResult<GeneratedResume> {
  return useResume(id ?? -1, id !== null);
}

/** Rename and/or edit a generated resume's YAML (D-45). Either field, or both. */
export function useUpdateResume(
  id: number,
): UseMutationResult<GeneratedResume, Error, ResumeUpdateBody> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: ResumeUpdateBody) => api.updateResume(id, patch),
    onSuccess: (updated) => {
      client.setQueryData(queryKeys.resumes.detail(id), updated);
      void client.invalidateQueries({ queryKey: queryKeys.resumes.all });
    },
  });
}

/** Re-render a stored resume's PDF from its current saved YAML (D-45). */
export function useRenderResume(id: number): UseMutationResult<GeneratedResume, Error, void> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.renderResume(id),
    onSuccess: (updated) => {
      client.setQueryData(queryKeys.resumes.detail(id), updated);
      void client.invalidateQueries({ queryKey: queryKeys.resumes.all });
    },
  });
}

export function useDeleteResume(): UseMutationResult<void, Error, number> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteResume(id),
    onSuccess: (_result, id) => {
      client.removeQueries({ queryKey: queryKeys.resumes.detail(id) });
      void client.invalidateQueries({ queryKey: queryKeys.resumes.all });
    },
  });
}

export function useRules(): UseQueryResult<Rule[]> {
  return useQuery({
    queryKey: queryKeys.rules,
    queryFn: ({ signal }) => api.getRules({ signal }),
  });
}

export function useUpdateRules(): UseMutationResult<Rule[], Error, Rule[]> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (rules: Rule[]) => api.updateRules(rules),
    onSuccess: (updated) => {
      client.setQueryData(queryKeys.rules, updated);
    },
  });
}

export function useResetRules(): UseMutationResult<Rule[], Error, void> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.resetRules(),
    onSuccess: (reset) => {
      client.setQueryData(queryKeys.rules, reset);
    },
  });
}

/**
 * The assistant prompt. Gated, because the only surface that reads it is a
 * dialog that is closed almost all of the time, and a query in a component
 * body runs on mount whether or not anything is showing its result.
 */
export function useSystemPrompt(enabled = true): UseQueryResult<SystemPrompt> {
  return useQuery({
    queryKey: queryKeys.systemPrompt,
    queryFn: ({ signal }) => api.getSystemPrompt({ signal }),
    enabled,
  });
}

export function useUpdateSystemPrompt(): UseMutationResult<SystemPrompt, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => api.updateSystemPrompt(content),
    onSuccess: (saved) => {
      client.setQueryData(queryKeys.systemPrompt, saved);
    },
  });
}

export function useResetSystemPrompt(): UseMutationResult<SystemPrompt, Error, void> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.resetSystemPrompt(),
    onSuccess: (reset) => {
      client.setQueryData(queryKeys.systemPrompt, reset);
    },
  });
}

/** One page's worth of transcript, oldest first (B-07). */
export const CHAT_PAGE_SIZE = 30;

/**
 * The chat transcript, paged backward from the most recent message.
 *
 * `GET /api/chat` grew `limit` and `before_id` in B-07 (D-21's network half):
 * each page asks for `CHAT_PAGE_SIZE` messages, and `fetchNextPage` (wired to
 * the "Load earlier" control in `features/assistant/Chat.tsx`) passes the id
 * of the oldest message already held as `before_id`, so it actually bounds
 * the network payload rather than windowing an already-fully-fetched list.
 *
 * `data.pages` arrives newest-page-first (fetch order); each page is itself
 * oldest-first. The caller reverses the page order and flattens to get one
 * chronological list -- see `Chat.tsx`.
 */
export function useChatHistory(): UseInfiniteQueryResult<InfiniteData<ChatMessage[]>> {
  return useInfiniteQuery({
    queryKey: queryKeys.chatHistory,
    // `?? []` guards against nothing on the real route (`requestJson` never
    // resolves to `undefined`, only to a schema-validated array); it is here
    // because TanStack Query v5 throws on an `undefined` query result, and the
    // Assistant tab is `forceMount`ed everywhere the shell renders, including
    // integration tests for other surfaces whose `api` mocks stop at the
    // handful of calls their own scenario needs.
    queryFn: async ({ pageParam, signal }) =>
      (await api.getChatHistory({ limit: CHAT_PAGE_SIZE, beforeId: pageParam }, { signal })) ?? [],
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.length === CHAT_PAGE_SIZE ? lastPage[0]?.id : undefined,
  });
}

/** How often {@link useLlmUsage} polls, in milliseconds. */
const LLM_USAGE_POLL_MS = 15_000;

/**
 * How much of the provider's per-minute/per-day rate limit this process has
 * used, for the counter next to the assistant (openrouter/free: 20/minute,
 * 50/day).
 *
 * Polled rather than invalidated after each LLM-triggering mutation: Tailor,
 * Evaluate, PDF import and Chat all consume the same global quota (it is not
 * scoped to any one of them), so polling one cheap indexed count is simpler
 * than wiring an invalidation into every call site that can move it.
 */
export function useLlmUsage(): UseQueryResult<LLMUsage> {
  return useQuery({
    queryKey: queryKeys.llmUsage,
    queryFn: ({ signal }) => api.getLlmUsage({ signal }),
    refetchInterval: LLM_USAGE_POLL_MS,
    refetchOnWindowFocus: true,
  });
}

/** Called after a generate or a delete: the whole library has moved. */
export function useInvalidateResumes(): () => void {
  const client = useQueryClient();
  return useCallback(() => {
    void client.invalidateQueries({ queryKey: queryKeys.resumes.all });
  }, [client]);
}

export type { GeneratedResume };
