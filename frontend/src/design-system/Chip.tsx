import * as React from "react";
import { cn } from "./cn";

export type ChipTone = "neutral" | "positive" | "critical";

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: ChipTone;
  /**
   * Text read out before the chip label, for when tone carries meaning that
   * colour alone would otherwise have to carry (section 5). Example: "Added".
   */
  toneLabel?: string;
}

const TONE: Record<ChipTone, string> = {
  neutral: "bg-lp-paper-sunken text-lp-ink-secondary border-lp-rule",
  positive: "bg-lp-positive-wash text-lp-positive border-lp-positive",
  critical: "bg-lp-critical-wash text-lp-critical border-lp-critical",
};

/**
 * Keyword chip (DESIGN-SYSTEM.md 4.1). Pill radius, which 2.3 permits for
 * exactly two things: status indicators and keyword chips.
 */
export function Chip({ tone = "neutral", toneLabel, className, children, ...rest }: ChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-lp-1 rounded-lp-pill border px-lp-2 py-[3px]",
        "font-lp-mono text-lp-caption tabular-nums",
        TONE[tone],
        className,
      )}
      {...rest}
    >
      {toneLabel ? <span className="sr-only">{toneLabel}: </span> : null}
      {children}
    </span>
  );
}
