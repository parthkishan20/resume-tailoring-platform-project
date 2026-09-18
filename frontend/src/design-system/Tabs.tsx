"use client";

import * as React from "react";
import * as RadixTabs from "@radix-ui/react-tabs";
import { cn, focusRing } from "./cn";

/**
 * Inspector tabs (DESIGN-SYSTEM.md 4.1). Radix supplies the real
 * roving-tabindex contract the hand-rolled `role="tab"` markup in the shipped
 * UI never had (D-44): one tab stop for the whole list, arrow keys move
 * between tabs, Home and End jump to the ends, and the selected tab is the
 * one that holds the tab stop.
 *
 * Content swap is a 120ms opacity change and nothing else, so the layout does
 * not move when the panel changes (2.7).
 */
export const Tabs = RadixTabs.Root;

export const TabsList = React.forwardRef<
  React.ElementRef<typeof RadixTabs.List>,
  React.ComponentPropsWithoutRef<typeof RadixTabs.List>
>(function TabsList({ className, ...rest }, ref) {
  return (
    <RadixTabs.List
      ref={ref}
      className={cn(
        "flex items-stretch gap-lp-1 border-b border-lp-rule bg-lp-paper-sunken px-lp-2",
        className,
      )}
      {...rest}
    />
  );
});

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof RadixTabs.Trigger>,
  React.ComponentPropsWithoutRef<typeof RadixTabs.Trigger>
>(function TabsTrigger({ className, ...rest }, ref) {
  return (
    <RadixTabs.Trigger
      ref={ref}
      className={cn(
        "relative -mb-px h-lp-panel-header px-lp-3 font-lp-sans text-lp-label font-medium",
        "text-lp-ink-secondary hover:text-lp-ink",
        "border-b-2 border-transparent",
        "data-[state=active]:border-lp-accent data-[state=active]:text-lp-ink",
        "disabled:cursor-not-allowed disabled:opacity-50",
        focusRing,
        className,
      )}
      {...rest}
    />
  );
});

export const TabsContent = React.forwardRef<
  React.ElementRef<typeof RadixTabs.Content>,
  React.ComponentPropsWithoutRef<typeof RadixTabs.Content>
>(function TabsContent({ className, ...rest }, ref) {
  return (
    <RadixTabs.Content
      ref={ref}
      className={cn(
        "p-lp-4 font-lp-sans text-lp-body text-lp-ink",
        "data-[state=active]:animate-lp-fade-in motion-reduce:animate-none",
        focusRing,
        className,
      )}
      {...rest}
    />
  );
});
