"use client";

import * as React from "react";
import { cn, focusRing, pressable } from "./cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Rendered before the label. Use a Phosphor icon; never a raw <svg>. */
  icon?: React.ReactNode;
  /**
   * Swaps the label for an inline indicator and disables the control. The
   * label stays in the DOM at `visibility: hidden`, so the button keeps its
   * width and the layout does not jump (DESIGN-SYSTEM.md 4.1).
   */
  loading?: boolean;
  /** Announced while `loading`. Must not contain an em dash (section 7). */
  loadingLabel?: string;
  type?: "button" | "submit" | "reset";
}

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-lp-accent text-lp-accent-contrast hover:bg-lp-accent-hover active:bg-lp-accent-active border border-transparent",
  secondary:
    "bg-lp-paper-raised text-lp-ink border border-lp-rule-control hover:border-lp-rule-strong hover:bg-lp-paper-sunken",
  ghost:
    "bg-transparent text-lp-ink-secondary border border-transparent hover:bg-lp-paper-sunken hover:text-lp-ink",
  danger:
    "bg-lp-critical text-lp-accent-contrast hover:opacity-90 active:opacity-100 border border-transparent",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-lp-control-compact px-lp-3 gap-lp-2",
  md: "h-lp-control px-lp-4 gap-lp-2",
};

/** A 14px inline indicator. The only circular spinner the system permits. */
function InlineIndicator() {
  return (
    <span
      aria-hidden="true"
      className="absolute h-[14px] w-[14px] animate-spin rounded-lp-pill border-2 border-current border-r-transparent motion-reduce:animate-none"
    />
  );
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    icon,
    loading = false,
    loadingLabel = "Working",
    className,
    children,
    disabled,
    type = "button",
    ...rest
  },
  ref,
) {
  const isDisabled = disabled === true || loading;

  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      data-lp-press=""
      data-loading={loading ? "" : undefined}
      className={cn(
        "relative inline-flex items-center justify-center whitespace-nowrap rounded-lp-control",
        "font-lp-sans text-lp-label font-medium",
        "disabled:cursor-not-allowed disabled:opacity-50",
        SIZE[size],
        VARIANT[variant],
        focusRing,
        pressable,
        className,
      )}
      {...rest}
    >
      {loading ? <InlineIndicator /> : null}
      <span
        className={cn("inline-flex items-center gap-lp-2", loading && "invisible")}
        aria-hidden={loading || undefined}
      >
        {icon ? (
          <span aria-hidden="true" className="inline-flex shrink-0 items-center">
            {icon}
          </span>
        ) : null}
        {children}
      </span>
      {loading ? <span className="sr-only">{loadingLabel}</span> : null}
    </button>
  );
});
