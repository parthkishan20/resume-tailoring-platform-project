"use client";

import * as React from "react";
import { cn } from "@/design-system";

export interface ResizeHandleProps {
  /** Announced name, for example "Editor and preview split". No em dash. */
  label: string;
  /** Current position as a percentage, for `aria-valuenow`. */
  value: number;
  min: number;
  max: number;
  /** Called with a new percentage during a drag and on an arrow keypress. */
  onChange: (next: number) => void;
  /**
   * Maps a pointer position to a percentage. Owned by the caller because only
   * it knows which element the percentage is measured against and in which
   * direction it grows.
   */
  measure: (event: PointerEvent) => number | null;
  /** Nudge per arrow keypress, in percentage points. */
  step?: number;
  className?: string;
  "data-testid"?: string;
}

/**
 * Draggable divider (D-43: "the editor split is also not draggable").
 *
 * `role="separator"` with a `tabIndex` is the ARIA window splitter: it takes a
 * value, a range, and arrow keys, so the split is adjustable without a pointer
 * as section 5 requires of every action. The visual line is 1px and the hit
 * area is widened to 9px through padding rather than by drawing a thick rule,
 * because a 9px rule between two panes would read as a third pane.
 *
 * Pointer capture rather than window listeners: the element keeps receiving
 * move events even when the pointer outruns it, which is the normal case when
 * a divider is dragged quickly, and the capture is released on `pointerup`
 * and `pointercancel` alike so a drag cannot survive a lost pointer.
 */
export function ResizeHandle({
  label,
  value,
  min,
  max,
  onChange,
  measure,
  step = 2,
  className,
  "data-testid": testId,
}: ResizeHandleProps) {
  const [dragging, setDragging] = React.useState(false);

  const clamp = React.useCallback((next: number) => Math.min(Math.max(next, min), max), [min, max]);

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    // Only the primary button starts a drag; a right-click must not.
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    const next = measure(event.nativeEvent);
    if (next !== null) onChange(clamp(next));
  }

  function endDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const delta =
      event.key === "ArrowLeft" || event.key === "ArrowUp"
        ? -step
        : event.key === "ArrowRight" || event.key === "ArrowDown"
          ? step
          : 0;

    if (delta !== 0) {
      event.preventDefault();
      onChange(clamp(value + delta));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      onChange(min);
    } else if (event.key === "End") {
      event.preventDefault();
      onChange(max);
    }
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={Math.round(value)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      data-testid={testId}
      data-dragging={dragging ? "" : undefined}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={handleKeyDown}
      className={cn(
        "group relative z-10 hidden w-[9px] shrink-0 cursor-col-resize touch-none select-none",
        "items-stretch justify-center md:flex",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-lp-focus",
        className,
      )}
    >
      <span
        aria-hidden="true"
        // No transition: 2.7 lists every animation the system permits and a
        // divider hover is not one of them, so the colour change is instant.
        className={cn(
          "w-px bg-lp-rule group-hover:bg-lp-accent group-focus-visible:bg-lp-accent",
          "group-data-[dragging]:bg-lp-accent",
        )}
      />
    </div>
  );
}
