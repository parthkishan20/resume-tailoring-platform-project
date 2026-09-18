"use client";

import * as React from "react";
import * as RadixTooltip from "@radix-ui/react-tooltip";
import { cn } from "./cn";

/**
 * Tooltip. Required on every icon-only control (DESIGN-SYSTEM.md 4.1, 5).
 *
 * The tooltip is decoration on top of an `aria-label`, never a replacement for
 * one: a pointer user gets the label visually, a screen-reader user gets it
 * from the accessible name, and neither depends on the other.
 */
export const TooltipProvider = RadixTooltip.Provider;

export interface TooltipProps {
  /** Tooltip text. No em dash (section 7). */
  label: string;
  side?: "top" | "right" | "bottom" | "left";
  children: React.ReactNode;
}

export function Tooltip({ label, side = "top", children }: TooltipProps) {
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          sideOffset={6}
          className={cn(
            "z-50 rounded-lp-control border border-lp-rule bg-lp-paper-overlay",
            "px-lp-2 py-lp-1 font-lp-sans text-lp-caption text-lp-ink shadow-lp-overlay",
            "animate-lp-fade-in motion-reduce:animate-none",
          )}
        >
          {label}
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
