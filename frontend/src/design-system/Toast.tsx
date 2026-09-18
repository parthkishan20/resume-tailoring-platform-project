"use client";

import * as React from "react";
import * as RadixToast from "@radix-ui/react-toast";
import { cn, focusRing } from "./cn";

export type ToastTone = "neutral" | "positive" | "critical";

export interface ToastMessage {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastContextValue {
  /** Show a transient result: saved, rendered, deleted, copied (4.1). */
  toast: (message: Omit<ToastMessage, "id" | "tone"> & { tone?: ToastTone }) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

/**
 * `useToast` throws outside a `ToastHost` rather than silently doing nothing,
 * because a swallowed success message is indistinguishable from a failure.
 */
export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside a ToastHost");
  }
  return ctx;
}

const TONE_ACCENT: Record<ToastTone, string> = {
  neutral: "border-l-lp-rule-strong",
  positive: "border-l-lp-positive",
  critical: "border-l-lp-critical",
};

/**
 * Toast host. Radix puts the viewport in a live region and gives every toast
 * a swipe and an F8 hotkey to reach it from the keyboard, so a result that
 * happens off-screen is still reachable without a pointer (section 5).
 *
 * Enter and exit are a 160ms translate plus fade, the row 2.7 allows.
 */
export function ToastHost({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = React.useState<ToastMessage[]>([]);
  const nextId = React.useRef(0);

  const toast = React.useCallback<ToastContextValue["toast"]>(({ title, description, tone }) => {
    nextId.current += 1;
    setMessages((current) => [
      ...current,
      { id: nextId.current, title, description, tone: tone ?? "neutral" },
    ]);
  }, []);

  const value = React.useMemo<ToastContextValue>(() => ({ toast }), [toast]);

  const dismiss = React.useCallback((id: number) => {
    setMessages((current) => current.filter((message) => message.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={value}>
      <RadixToast.Provider swipeDirection="right" duration={5000}>
        {children}
        {messages.map((message) => (
          <RadixToast.Root
            key={message.id}
            onOpenChange={(open) => {
              if (!open) dismiss(message.id);
            }}
            className={cn(
              "flex w-[min(92vw,360px)] flex-col gap-lp-1 rounded-lp-surface border border-l-4 border-lp-rule",
              "bg-lp-paper-overlay p-lp-4 font-lp-sans shadow-lp-overlay",
              TONE_ACCENT[message.tone],
              "data-[state=open]:animate-lp-toast-in data-[state=closed]:animate-lp-toast-out",
              "motion-reduce:animate-none",
            )}
          >
            <RadixToast.Title className="text-lp-label font-medium text-lp-ink">
              {message.title}
            </RadixToast.Title>
            {message.description ? (
              <RadixToast.Description className="text-lp-caption text-lp-ink-secondary">
                {message.description}
              </RadixToast.Description>
            ) : null}
            <RadixToast.Close
              aria-label="Dismiss"
              className={cn(
                "absolute right-lp-2 top-lp-2 rounded-lp-control px-lp-1 text-lp-caption",
                "text-lp-ink-tertiary hover:text-lp-ink",
                focusRing,
              )}
            >
              Close
            </RadixToast.Close>
          </RadixToast.Root>
        ))}
        <RadixToast.Viewport className="fixed bottom-lp-5 right-lp-5 z-50 flex flex-col gap-lp-2 outline-none" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}
