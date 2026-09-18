"use client";

import * as React from "react";
import { Check, Warning } from "@phosphor-icons/react";
import { cn } from "./cn";

export interface ProgressStage {
  id: string;
  /** Shown to the user. No em dash (section 7). */
  label: string;
}

export interface ProgressRailProps {
  stages: ProgressStage[];
  /** Index of the stage in flight. Everything before it is done. */
  currentIndex: number;
  /** `error` stops the rail at `currentIndex` and paints that stage critical. */
  status?: "running" | "error" | "complete";
  /** Shown under the rail when `status` is `error`. */
  errorMessage?: string;
  /** Names what is being tracked, for the accessible label. */
  label?: string;
}

type StageState = "done" | "active" | "error" | "pending";

function stageState(
  index: number,
  currentIndex: number,
  status: NonNullable<ProgressRailProps["status"]>,
): StageState {
  if (status === "complete") return "done";
  if (index < currentIndex) return "done";
  if (index > currentIndex) return "pending";
  return status === "error" ? "error" : "active";
}

const DOT: Record<StageState, string> = {
  done: "border-lp-positive bg-lp-positive text-lp-paper-raised",
  active: "border-lp-accent bg-lp-accent-wash text-lp-accent",
  error: "border-lp-critical bg-lp-critical-wash text-lp-critical",
  pending: "border-lp-rule-control bg-lp-paper-raised text-lp-ink-tertiary",
};

const TEXT: Record<StageState, string> = {
  done: "text-lp-ink-secondary",
  active: "text-lp-ink font-medium",
  error: "text-lp-critical font-medium",
  pending: "text-lp-ink-tertiary",
};

/**
 * Determinate named-stage rail (DESIGN-SYSTEM.md 4.1, 2.7). Generation has
 * three known backend stages, so it shows three named steps rather than the
 * circular spinner the shipped panels use for shaped work (D-09 in the spec's
 * section 1 table).
 *
 * The active stage is announced politely and the error assertively, which is
 * the split section 5 requires.
 */
export function ProgressRail({
  stages,
  currentIndex,
  status = "running",
  errorMessage,
  label = "Progress",
}: ProgressRailProps) {
  const current = stages[Math.min(Math.max(currentIndex, 0), stages.length - 1)];
  const doneCount = status === "complete" ? stages.length : Math.max(currentIndex, 0);

  return (
    <div className="font-lp-sans">
      <ol
        aria-label={label}
        className="flex flex-col gap-lp-3"
        // Not role="progressbar": the stages are the information, and a
        // percentage would invent precision the backend does not report.
      >
        {stages.map((stage, index) => {
          const state = stageState(index, currentIndex, status);
          return (
            <li key={stage.id} className="flex items-center gap-lp-3">
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-lp-6 w-lp-6 shrink-0 items-center justify-center rounded-lp-pill border",
                  DOT[state],
                )}
              >
                {state === "done" ? (
                  <Check size={12} weight="bold" />
                ) : state === "error" ? (
                  <Warning size={12} weight="bold" />
                ) : (
                  <span className="font-lp-mono text-lp-caption tabular-nums">{index + 1}</span>
                )}
              </span>
              <span className={cn("text-lp-label", TEXT[state])}>{stage.label}</span>
            </li>
          );
        })}
      </ol>

      <p aria-live="polite" className="sr-only">
        {status === "complete"
          ? `${label} complete`
          : status === "error"
            ? ""
            : current
              ? `${label}: ${current.label}, step ${doneCount + 1} of ${stages.length}`
              : ""}
      </p>
      {status === "error" && errorMessage ? (
        <p role="alert" className="mt-lp-3 max-w-[65ch] text-lp-caption text-lp-critical">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
