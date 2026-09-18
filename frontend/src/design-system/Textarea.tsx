"use client";

import * as React from "react";
import { cn, focusRing } from "./cn";

export interface TextareaProps extends Omit<
  React.TextareaHTMLAttributes<HTMLTextAreaElement>,
  "id"
> {
  label: string;
  helper?: string;
  error?: string;
  id?: string;
}

/**
 * Multi-line input (DESIGN-SYSTEM.md 4.1). Same contract as `Input`: label
 * above, helper or error below, placeholder never carries the label.
 */
export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, helper, error, id, className, rows = 6, ...rest },
  ref,
) {
  const reactId = React.useId();
  const fieldId = id ?? `lp-textarea-${reactId}`;
  const helperId = `${fieldId}-helper`;
  const errorId = `${fieldId}-error`;
  const describedBy = error ? errorId : helper ? helperId : undefined;

  return (
    <div className="flex flex-col gap-lp-1 font-lp-sans">
      <label htmlFor={fieldId} className="text-lp-label font-medium text-lp-ink">
        {label}
      </label>
      <textarea
        ref={ref}
        id={fieldId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          "w-full resize-y rounded-lp-control border bg-lp-paper-raised px-lp-3 py-lp-2",
          "text-lp-body text-lp-ink placeholder:text-lp-ink-tertiary",
          "disabled:cursor-not-allowed disabled:bg-lp-paper-sunken disabled:text-lp-ink-tertiary",
          error ? "border-lp-critical" : "border-lp-rule-control hover:border-lp-rule-strong",
          focusRing,
          className,
        )}
        {...rest}
      />
      {error ? (
        <p id={errorId} role="alert" className="text-lp-caption text-lp-critical">
          {error}
        </p>
      ) : helper ? (
        <p id={helperId} className="text-lp-caption text-lp-ink-tertiary">
          {helper}
        </p>
      ) : null}
    </div>
  );
});
