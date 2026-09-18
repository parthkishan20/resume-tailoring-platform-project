"use client";

import * as React from "react";
import { cn, focusRing } from "./cn";

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "id"> {
  /** Always rendered above the field. Never collapsed into the placeholder. */
  label: string;
  /** Sits below the field. Replaced by `error` when there is one. */
  helper?: string;
  /** Renders in `--lp-critical`, wires aria-invalid, and announces politely. */
  error?: string;
  id?: string;
}

/**
 * Text input (DESIGN-SYSTEM.md 4.1): label above, helper below, error below,
 * never placeholder-as-label. The placeholder is supplementary only, so
 * nothing is lost when it disappears on first keystroke.
 */
export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, helper, error, id, className, ...rest },
  ref,
) {
  const reactId = React.useId();
  const inputId = id ?? `lp-input-${reactId}`;
  const helperId = `${inputId}-helper`;
  const errorId = `${inputId}-error`;
  const describedBy = error ? errorId : helper ? helperId : undefined;

  return (
    <div className="flex flex-col gap-lp-1 font-lp-sans">
      <label htmlFor={inputId} className="text-lp-label font-medium text-lp-ink">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          "h-lp-control w-full rounded-lp-control border bg-lp-paper-raised px-lp-3",
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
