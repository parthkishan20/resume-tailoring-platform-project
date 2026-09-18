"use client";

import * as React from "react";
import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react";
import { cn, focusRing } from "./cn";

/**
 * Modal dialog (DESIGN-SYSTEM.md 4.1): generation rules, assistant prompt,
 * appearance. Radix gives the whole section 5 contract for free: focus is
 * trapped while open, returned to the trigger on close, and Escape closes the
 * top layer only.
 */
export const Dialog = RadixDialog.Root;
export const DialogTrigger = RadixDialog.Trigger;
export const DialogClose = RadixDialog.Close;

export interface DialogContentProps extends React.ComponentPropsWithoutRef<
  typeof RadixDialog.Content
> {
  title: string;
  /** Optional one-line subtitle. Wired to aria-describedby. No em dash. */
  description?: string;
  /** Label for the close control. It is icon-only, so this is required. */
  closeLabel?: string;
}

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof RadixDialog.Content>,
  DialogContentProps
>(function DialogContent(
  { title, description, closeLabel = "Close", className, children, ...rest },
  ref,
) {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 z-40 bg-lp-scrim data-[state=open]:animate-lp-fade-in motion-reduce:animate-none" />
      <RadixDialog.Content
        ref={ref}
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(92vw,560px)] -translate-x-1/2 -translate-y-1/2",
          "rounded-lp-surface border border-lp-rule bg-lp-paper-overlay p-lp-6 shadow-lp-overlay",
          "font-lp-sans text-lp-body text-lp-ink",
          "data-[state=open]:animate-lp-fade-in motion-reduce:animate-none",
          className,
        )}
        {...rest}
      >
        <div className="mb-lp-4 flex items-start justify-between gap-lp-4">
          <div className="flex flex-col gap-lp-1">
            <RadixDialog.Title className="text-lp-heading font-semibold text-lp-ink">
              {title}
            </RadixDialog.Title>
            {description ? (
              <RadixDialog.Description className="text-lp-caption text-lp-ink-tertiary">
                {description}
              </RadixDialog.Description>
            ) : null}
          </div>
          <RadixDialog.Close
            aria-label={closeLabel}
            className={cn(
              "inline-flex h-lp-control w-lp-control shrink-0 items-center justify-center",
              "rounded-lp-control text-lp-ink-secondary hover:bg-lp-paper-sunken hover:text-lp-ink",
              focusRing,
            )}
          >
            <X size={16} aria-hidden="true" />
          </RadixDialog.Close>
        </div>
        {children}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  );
});

/** Right-aligned action row. Primary action last, matching platform order. */
export function DialogFooter({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-lp-6 flex justify-end gap-lp-2", className)} {...rest} />;
}
