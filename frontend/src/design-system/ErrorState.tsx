"use client";

import * as React from "react";
import { WarningCircle } from "@phosphor-icons/react";
import { cn } from "./cn";

export interface ErrorStateProps {
  /** What went wrong, in the user's terms. No em dash (section 7). */
  title: string;
  /**
   * The cause, when it is known. Rendered verbatim and selectable, because a
   * renderer message the user cannot copy is a message they cannot report
   * (DESIGN-SYSTEM.md 4.3, document frame row).
   */
  cause?: string;
  /** The retry control. Every error surface has one (4.3). */
  action?: React.ReactNode;
  className?: string;
}

/**
 * Error state. `role="alert"` so it is announced assertively the moment it
 * mounts, which section 5 requires and which no error surface in the shipped
 * UI does today (D-44).
 */
export function ErrorState({ title, cause, action, className }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-start gap-lp-3 rounded-lp-surface border border-lp-critical",
        "bg-lp-critical-wash p-lp-5 font-lp-sans",
        className,
      )}
    >
      <p className="flex items-center gap-lp-2 text-lp-heading font-semibold text-lp-critical">
        <WarningCircle size={18} aria-hidden="true" />
        {title}
      </p>
      {cause ? (
        <pre className="max-w-full select-text overflow-x-auto whitespace-pre-wrap rounded-lp-control bg-lp-paper-raised p-lp-3 font-lp-mono text-lp-code text-lp-ink-secondary">
          {cause}
        </pre>
      ) : null}
      {action}
    </div>
  );
}
