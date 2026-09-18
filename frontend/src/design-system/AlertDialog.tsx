"use client";

import * as React from "react";
import * as RadixAlertDialog from "@radix-ui/react-alert-dialog";
import { cn, focusRing, pressable } from "./cn";

/**
 * Destructive confirmation (DESIGN-SYSTEM.md 4.1, 4.2). Replaces
 * `ui/ConfirmButton`, which is a two-click button pretending to be a
 * confirmation: it announces nothing, traps no focus, and a stray second
 * click confirms a delete the user never read.
 *
 * Radix's alert dialog is `role="alertdialog"`, opens with focus on the
 * cancel action, and does not close on an outside click, which is the correct
 * behaviour for a question that destroys data.
 */
export const AlertDialog = RadixAlertDialog.Root;
export const AlertDialogTrigger = RadixAlertDialog.Trigger;

export interface AlertDialogContentProps {
  title: string;
  /** What is about to happen and what it costs. No em dash (section 7). */
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  /** `danger` paints the confirm action critical. Default for deletes. */
  tone?: "danger" | "neutral";
}

export function AlertDialogContent({
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  tone = "danger",
}: AlertDialogContentProps) {
  return (
    <RadixAlertDialog.Portal>
      <RadixAlertDialog.Overlay className="fixed inset-0 z-40 bg-lp-scrim data-[state=open]:animate-lp-fade-in motion-reduce:animate-none" />
      <RadixAlertDialog.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2",
          "rounded-lp-surface border border-lp-rule bg-lp-paper-overlay p-lp-6 shadow-lp-overlay",
          "font-lp-sans text-lp-ink",
          "data-[state=open]:animate-lp-fade-in motion-reduce:animate-none",
        )}
      >
        <RadixAlertDialog.Title className="text-lp-heading font-semibold">
          {title}
        </RadixAlertDialog.Title>
        <RadixAlertDialog.Description className="mt-lp-2 max-w-[65ch] text-lp-body text-lp-ink-secondary">
          {description}
        </RadixAlertDialog.Description>
        <div className="mt-lp-6 flex justify-end gap-lp-2">
          <RadixAlertDialog.Cancel
            className={cn(
              "inline-flex h-lp-control items-center rounded-lp-control border border-lp-rule-control",
              "bg-lp-paper-raised px-lp-4 text-lp-label font-medium text-lp-ink hover:bg-lp-paper-sunken",
              focusRing,
              pressable,
            )}
            data-lp-press=""
          >
            {cancelLabel}
          </RadixAlertDialog.Cancel>
          <RadixAlertDialog.Action
            onClick={onConfirm}
            className={cn(
              "inline-flex h-lp-control items-center rounded-lp-control border border-transparent px-lp-4",
              "text-lp-label font-medium",
              tone === "danger"
                ? "bg-lp-critical text-lp-accent-contrast hover:opacity-90"
                : "bg-lp-accent text-lp-accent-contrast hover:bg-lp-accent-hover",
              focusRing,
              pressable,
            )}
            data-lp-press=""
          >
            {confirmLabel}
          </RadixAlertDialog.Action>
        </div>
      </RadixAlertDialog.Content>
    </RadixAlertDialog.Portal>
  );
}
