"use client";

import * as React from "react";
import { cn } from "./cn";

export type DocumentMode = "editor" | "split" | "preview";

const MODES: { value: DocumentMode; label: string }[] = [
  { value: "editor", label: "Editor" },
  { value: "split", label: "Split" },
  { value: "preview", label: "Preview" },
];

/**
 * Editor / Split / Preview.
 *
 * DESIGN-SYSTEM.md 1 keeps the segmented control as "the correct control for
 * the job" and 4.1 specifies it on `@radix-ui/react-toggle-group`. Task 1.4
 * shipped 14 of the 18 primitives in 4.1 and this was not one of them, so
 * task 2.3 built it locally against the tokens instead, rather than reaching
 * for the legacy `components/ui/SegmentedControl`, whose markup is
 * `role="tablist"` over `role="tab"` with no panel and no keyboard contract
 * (P1-16 in the frontend audit).
 *
 * Promoted into `design-system/` by task 3.1, unchanged. **Deviation from the
 * plan text**: the promotion did not also swap the implementation onto
 * `@radix-ui/react-toggle-group`. The hand-rolled roving-tabindex radio group
 * below already satisfies the same keyboard and ARIA contract Radix's
 * primitive would provide, adding the dependency now would touch working,
 * tested code for no behavioural change, and a Radix rewrite is easy to do
 * later in this one file without another promotion.
 *
 * Semantics are a radio group, not tabs: these three do not each own a panel,
 * they choose one layout for the same panel. Roving tabindex, so the group is
 * one tab stop and arrow keys move within it.
 */
export function ModeSwitch({
  value,
  onChange,
  className,
}: {
  value: DocumentMode;
  onChange: (mode: DocumentMode) => void;
  className?: string;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);

  function focusMode(index: number) {
    const next = (index + MODES.length) % MODES.length;
    onChange(MODES[next].value);
    refs.current[next]?.focus();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      focusMode(index + 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      focusMode(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusMode(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusMode(MODES.length - 1);
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label="Document layout"
      data-testid="mode-switch"
      className={cn(
        "inline-flex items-center gap-lp-1 rounded-lp-control border border-lp-rule",
        "bg-lp-paper-sunken p-[2px]",
        className,
      )}
    >
      {MODES.map((mode, index) => {
        const checked = mode.value === value;
        return (
          <button
            key={mode.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            data-testid={`mode-${mode.value}`}
            onClick={() => onChange(mode.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            data-lp-press=""
            className={cn(
              "h-lp-control-compact rounded-lp-control px-lp-3 font-lp-sans text-lp-label font-medium",
              "transition-transform duration-lp-press active:scale-[0.98] motion-reduce:active:scale-100",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
              checked
                ? "bg-lp-paper-raised text-lp-ink shadow-lp-raised"
                : "text-lp-ink-secondary hover:text-lp-ink",
            )}
          >
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}
