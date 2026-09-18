"use client";

import * as React from "react";
import { cn } from "./cn";

export interface ScoreDialProps {
  /** 0 to 100. Out-of-range values are clamped rather than drawn off the ring. */
  score: number;
  className?: string;
}

const RADIUS = 38;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Score bands. Three of them, with text labels, because section 5 forbids
 * communicating the score by colour alone: the numeral and the band name each
 * carry it independently of the ring's tone.
 */
function band(score: number): { label: string; tone: "positive" | "caution" | "critical" } {
  if (score >= 75) return { label: "Strong match", tone: "positive" };
  if (score >= 50) return { label: "Partial match", tone: "caution" };
  return { label: "Weak match", tone: "critical" };
}

// Applied via inline `style`, not a `stroke-*` utility: Tailwind's `stroke`
// core plugin is a separate theme key from `colors`, and pinning the ring's
// tone to a raw `var(--lp-*)` custom property is guaranteed correct across
// the v3-to-v4 migration this same task performs, rather than depending on
// how each engine resolves an extended `stroke` theme entry.
const STROKE: Record<"positive" | "caution" | "critical", string> = {
  positive: "var(--lp-positive)",
  caution: "var(--lp-caution)",
  critical: "var(--lp-critical)",
};

const TEXT: Record<"positive" | "caution" | "critical", string> = {
  positive: "text-lp-positive",
  caution: "text-lp-caution",
  critical: "text-lp-critical",
};

/**
 * The drawn score dial (DESIGN-SYSTEM.md 4.1), replacing the numeral-and-band
 * placeholder Evaluate shipped in task 2.3 while this primitive did not exist
 * yet.
 *
 * The ring draws in from empty over `--lp-duration-dial` (700ms) `ease-out`
 * (2.7): mounted at a fully-hidden `stroke-dashoffset` and moved to the real
 * one a frame later, so the browser has a value change to transition rather
 * than painting the final ring on the first frame. A later score change (a
 * re-run) animates the same way, from wherever the ring currently sits.
 * `prefers-reduced-motion` needs no separate check here: `globals.css`
 * already clamps every transition duration to near-zero globally.
 *
 * Section 5: the score is never communicated by colour alone. The ring's tone
 * is decorative and `aria-hidden`; the one `role="img"` wrapper carries the
 * whole sentence, numeral and band label together, as its `aria-label`, so a
 * screen reader gets a single coherent announcement rather than three
 * fragments.
 */
export function ScoreDial({ score, className }: ScoreDialProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const { label, tone } = band(clamped);
  const targetOffset = CIRCUMFERENCE * (1 - clamped / 100);

  const [offset, setOffset] = React.useState(CIRCUMFERENCE);
  React.useEffect(() => {
    const frame = requestAnimationFrame(() => setOffset(targetOffset));
    return () => cancelAnimationFrame(frame);
  }, [targetOffset]);

  return (
    <div
      role="img"
      aria-label={`Match score ${clamped} out of 100. ${label}.`}
      data-testid="score-dial"
      className={cn("inline-flex items-center gap-lp-4", className)}
    >
      <svg
        width="88"
        height="88"
        viewBox="0 0 88 88"
        aria-hidden="true"
        className="-rotate-90 shrink-0"
      >
        <circle
          cx="44"
          cy="44"
          r={RADIUS}
          fill="none"
          strokeWidth="8"
          style={{ stroke: "var(--lp-rule)" }}
        />
        <circle
          cx="44"
          cy="44"
          r={RADIUS}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          style={{
            stroke: STROKE[tone],
            transition: "stroke-dashoffset var(--lp-duration-dial) var(--lp-ease-out)",
          }}
        />
      </svg>
      <div aria-hidden="true" className="flex flex-col gap-lp-1">
        <span className="font-lp-mono text-lp-display font-semibold leading-none tabular-nums text-lp-ink">
          {clamped}
        </span>
        <span className={cn("font-lp-sans text-lp-label font-medium", TEXT[tone])}>{label}</span>
      </div>
    </div>
  );
}
