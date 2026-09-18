"use client";

import * as React from "react";
import { cn, focusRing, pressable } from "./cn";
import { Tooltip } from "./Tooltip";

export type IconButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type IconButtonSize = "sm" | "md";

export interface IconButtonProps extends Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  "type" | "children"
> {
  /**
   * The accessible name and the tooltip text. Both are required and both come
   * from this one prop, so they can never drift apart (DESIGN-SYSTEM.md 5).
   * No em dash (section 7).
   */
  label: string;
  icon: React.ReactNode;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
  tooltipSide?: "top" | "right" | "bottom" | "left";
  type?: "button" | "submit" | "reset";
}

const VARIANT: Record<IconButtonVariant, string> = {
  primary:
    "bg-lp-accent text-lp-accent-contrast hover:bg-lp-accent-hover border border-transparent",
  secondary:
    "bg-lp-paper-raised text-lp-ink border border-lp-rule-control hover:border-lp-rule-strong hover:bg-lp-paper-sunken",
  ghost:
    "bg-transparent text-lp-ink-secondary border border-transparent hover:bg-lp-paper-sunken hover:text-lp-ink",
  danger: "bg-lp-critical text-lp-accent-contrast hover:opacity-90 border border-transparent",
};

// Both sizes clear the 32px minimum pointer target from section 5: `sm` keeps
// a 28px visual box but pads its hit area out to 32px.
const SIZE: Record<IconButtonSize, string> = {
  sm: "h-lp-control-compact w-lp-control-compact after:absolute after:-inset-[2px] after:content-['']",
  md: "h-lp-control w-lp-control",
};

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  {
    label,
    icon,
    variant = "ghost",
    size = "md",
    tooltipSide = "top",
    className,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <Tooltip label={label} side={tooltipSide}>
      <button
        ref={ref}
        type={type}
        aria-label={label}
        data-lp-press=""
        className={cn(
          "relative inline-flex shrink-0 items-center justify-center rounded-lp-control",
          "disabled:cursor-not-allowed disabled:opacity-50",
          SIZE[size],
          VARIANT[variant],
          focusRing,
          pressable,
          className,
        )}
        {...rest}
      >
        <span aria-hidden="true" className="inline-flex items-center justify-center">
          {icon}
        </span>
      </button>
    </Tooltip>
  );
});
