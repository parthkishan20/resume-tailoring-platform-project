import * as React from "react";
import { cn } from "./cn";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * `text` for a line of copy, `block` for a region, `page` for the document
   * sheet. Skeletons are shape-matched, never a circle (DESIGN-SYSTEM.md 4.2).
   */
  shape?: "text" | "block" | "page";
}

const SHAPE: Record<NonNullable<SkeletonProps["shape"]>, string> = {
  text: "h-[0.9em] rounded-lp-control",
  block: "rounded-lp-surface",
  page: "aspect-[1/1.294] w-full max-w-[420px] rounded-lp-surface shadow-lp-page",
};

/**
 * Loading placeholder. The shimmer is the one infinite loop 2.7 permits, and
 * `data-lp-shimmer` is what `tokens.css` stops under reduced motion.
 *
 * `aria-hidden`: a skeleton has nothing to announce. The region that owns it
 * carries the `aria-busy` and the live-region message.
 */
export function Skeleton({ shape = "block", className, ...rest }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      data-lp-shimmer=""
      className={cn(
        "animate-lp-shimmer bg-lp-paper-sunken",
        "bg-lp-shimmer bg-[length:200%_100%]",
        SHAPE[shape],
        className,
      )}
      {...rest}
    />
  );
}
