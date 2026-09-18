import * as React from "react";
import { cn } from "./cn";

export interface EmptyStateProps {
  /** A Phosphor icon element. Never a raw <svg> path (2.6). */
  icon?: React.ReactNode;
  /** One line saying what goes here. No em dash (section 7). */
  title: string;
  /** At most one supporting sentence. */
  description?: string;
  /** Exactly one action, or none. Two actions is a decision, not an empty state. */
  action?: React.ReactNode;
  className?: string;
}

/**
 * Generic empty state (DESIGN-SYSTEM.md 4.1, 4.3). The onboarding-specific
 * `components/EmptyState.tsx` is a different surface and stays where it is
 * until task 2.3 splits it into the onboarding route and this primitive.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-lp-3 rounded-lp-surface",
        "border border-dashed border-lp-rule-control bg-lp-paper-sunken p-lp-8 text-center",
        "font-lp-sans",
        className,
      )}
    >
      {icon ? (
        <span aria-hidden="true" className="text-lp-ink-tertiary">
          {icon}
        </span>
      ) : null}
      <p className="text-lp-heading font-semibold text-lp-ink">{title}</p>
      {description ? (
        <p className="max-w-[48ch] text-lp-body text-lp-ink-secondary">{description}</p>
      ) : null}
      {action ? <div className="mt-lp-1">{action}</div> : null}
    </div>
  );
}
