"use client";

import * as React from "react";
import { PaperPlaneTilt } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, EmptyState, ErrorState, Skeleton, Textarea, cn } from "@/design-system";
import { queryKeys, useChatHistory } from "@/features/queries";
import { streamChat, type ChatAction } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

/**
 * How many of the persisted transcript's most recent messages are rendered at
 * once, with "Load earlier messages" revealing more (D-21's frontend half).
 *
 * `GET /api/chat` has no `limit` or cursor (see `queries.ts`'s
 * `useChatHistory` doc), so this windows what is already fetched rather than
 * fetching less: it bounds the DOM, not the network payload. The network half
 * needs a route change this task does not own; see PLAN.md's Open blockers.
 */
const PAGE_SIZE = 30;

const SUGGESTIONS = [
  "Tighten my summary for a senior role.",
  "Add a bullet about leading a migration.",
  "Rewrite my skills section to match this posting.",
];

let localId = -1;
function nextLocalId(): number {
  localId -= 1;
  return localId;
}

/**
 * A human-readable line for a tool-call result, without assuming which of the
 * four fixed tools (D8) produced it.
 *
 * ## The D-33 seam
 *
 * Task 3.3 (running concurrently) is what makes `action` ever non-null:
 * `POST /api/chat/stream`'s `done` frame already declares `result.action` as
 * `{ type: string, resume_id: number | null } | null` (`schemas.ts`), and
 * today the backend always sends `null` because no tool calls anything yet.
 * This renders whatever arrives without hard-coding 3.3's eventual type
 * strings: `type` is humanized generically (`master_resume_updated` becomes
 * "Master resume updated"), so the moment 3.3 starts sending real actions
 * this reads sensibly with no change here, and nothing breaks if the exact
 * strings differ from any guess made today.
 */
function describeAction(action: ChatAction): string {
  const words = action.type.split("_").filter(Boolean);
  const sentence = words.length === 0 ? "Action completed" : words.join(" ");
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

type LiveMessage = ChatMessage & { streaming?: boolean };

export function Chat() {
  const queryClient = useQueryClient();
  const history = useChatHistory();

  const [windowSize, setWindowSize] = React.useState(PAGE_SIZE);
  const [live, setLive] = React.useState<LiveMessage[]>([]);
  const [lastAction, setLastAction] = React.useState<ChatAction | null>(null);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [failedMessage, setFailedMessage] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const persisted = history.data ?? [];
  const windowed = persisted.slice(-windowSize);
  const hasEarlier = persisted.length > windowed.length;
  const visible = [...windowed, ...live];

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visible.length]);

  async function send(message: string) {
    if (!message.trim() || sending) return;
    setInput("");
    setSending(true);
    setError(null);
    setFailedMessage(null);
    setLastAction(null);

    const userMessage: LiveMessage = {
      id: nextLocalId(),
      user_id: "default",
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    setLive([userMessage]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let assistantText = "";
    const assistantId = nextLocalId();

    try {
      for await (const frame of streamChat({ message }, { signal: controller.signal })) {
        if (frame.event === "token") {
          assistantText += frame.data.delta;
          setLive([
            userMessage,
            {
              id: assistantId,
              user_id: "default",
              role: "assistant",
              content: assistantText,
              created_at: new Date().toISOString(),
              streaming: true,
            },
          ]);
        } else if (frame.event === "done") {
          const { action } = frame.data.result;
          if (action) {
            setLastAction(action);
            void queryClient.invalidateQueries({ queryKey: queryKeys.masterResume });
            if (action.resume_id !== null) {
              void queryClient.invalidateQueries({ queryKey: queryKeys.resumes.all });
            }
          }
          await queryClient.invalidateQueries({ queryKey: queryKeys.chatHistory });
          setLive([]);
        } else if (frame.event === "error") {
          setError(frame.data.error);
          setFailedMessage(message);
        }
      }
    } catch (caught: unknown) {
      if (controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : "The message could not be sent");
      setFailedMessage(message);
    } finally {
      setSending(false);
    }
  }

  const waitingForReply = sending && live.length > 0 && live[live.length - 1]?.role === "user";

  return (
    <div data-testid="chat-panel" className="flex h-full flex-col overflow-hidden">
      <div className="flex min-h-0 flex-1 flex-col gap-lp-4 overflow-y-auto p-lp-4">
        {history.isPending ? (
          <div className="flex flex-col gap-lp-3" aria-busy="true">
            <p aria-live="polite" className="sr-only">
              Loading the conversation
            </p>
            <Skeleton shape="text" className="w-2/3" />
            <Skeleton shape="text" className="w-1/2" />
            <Skeleton shape="text" className="w-3/5" />
          </div>
        ) : history.isError ? (
          <ErrorState
            title="The conversation could not be loaded"
            cause={history.error.message}
            action={
              <Button variant="secondary" size="sm" onClick={() => void history.refetch()}>
                Try again
              </Button>
            }
          />
        ) : (
          <>
            {hasEarlier ? (
              <button
                type="button"
                data-testid="chat-load-earlier"
                onClick={() => setWindowSize((size) => size + PAGE_SIZE)}
                className="self-center font-lp-sans text-lp-caption font-medium text-lp-accent hover:underline"
              >
                Load earlier messages
              </button>
            ) : null}

            {visible.length === 0 && !sending ? (
              <EmptyState
                title="Ask the assistant for edits"
                description="Rewrite a section, add a bullet, restructure the YAML. Changes apply directly to your master resume."
                action={
                  <div className="flex flex-col gap-lp-2">
                    {SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        data-testid="chat-suggestion"
                        onClick={() => setInput(suggestion)}
                        className={cn(
                          "rounded-lp-control border border-lp-rule-control bg-lp-paper-raised px-lp-3 py-lp-2",
                          "text-left font-lp-sans text-lp-label text-lp-ink hover:border-lp-rule-strong hover:bg-lp-paper-sunken",
                        )}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                }
              />
            ) : (
              visible.map((message) => <MessageBubble key={message.id} message={message} />)
            )}

            {waitingForReply ? (
              <div className="flex items-center gap-lp-2.5">
                <span
                  className="h-1.5 w-1.5 animate-pulse rounded-lp-pill bg-lp-accent motion-reduce:animate-none"
                  aria-hidden="true"
                />
                <span className="text-lp-caption text-lp-ink-tertiary">Thinking</span>
              </div>
            ) : null}

            {lastAction ? (
              <p
                data-testid="chat-action-note"
                className="self-center font-lp-sans text-lp-caption text-lp-ink-tertiary"
              >
                {describeAction(lastAction)}
              </p>
            ) : null}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 border-t border-lp-rule p-lp-3">
        {error ? (
          <div className="mb-lp-2 flex items-center justify-between gap-lp-2">
            <p role="alert" className="text-lp-caption text-lp-critical">
              {error}
            </p>
            {failedMessage ? (
              <button
                type="button"
                data-testid="chat-retry"
                onClick={() => void send(failedMessage)}
                className="shrink-0 font-lp-sans text-lp-caption font-medium text-lp-accent hover:underline"
              >
                Retry
              </button>
            ) : null}
          </div>
        ) : null}
        <form
          className="flex items-end gap-lp-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          <Textarea
            data-testid="chat-input"
            label="Message the assistant"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(input);
              }
            }}
            placeholder="Ask the assistant..."
            rows={2}
            className="max-h-32 flex-1 resize-none"
            disabled={sending}
          />
          <Button
            type="submit"
            data-testid="chat-send"
            variant="primary"
            size="md"
            icon={<PaperPlaneTilt size={15} />}
            disabled={sending || !input.trim()}
            loading={sending}
            loadingLabel="Sending"
          >
            <span className="sr-only">Send message</span>
          </Button>
        </form>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: LiveMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      data-testid="chat-message"
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      {isUser ? (
        <div className="max-w-[85%] rounded-lp-surface rounded-br-md bg-lp-paper-sunken px-lp-3 py-lp-2 text-lp-body text-lp-ink">
          {message.content}
        </div>
      ) : (
        <div className="flex max-w-[95%] gap-lp-2">
          <span
            className="mt-lp-1 h-1.5 w-1.5 shrink-0 rounded-lp-pill bg-lp-accent"
            aria-hidden="true"
          />
          <div className="whitespace-pre-wrap text-lp-body leading-relaxed text-lp-ink">
            {message.content}
          </div>
        </div>
      )}
    </div>
  );
}
