"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { Button, cn } from "@/design-system";
import { Gallery } from "./gallery";

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const;

function ThemeSwitch() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // `theme` is unknown until the client has read storage, so the control
  // renders unselected on the server and settles after mount. Without this
  // the markup mismatches and React warns on hydration.
  React.useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div
      role="group"
      aria-label="Appearance"
      className="inline-flex items-center gap-lp-1 rounded-lp-control border border-lp-rule bg-lp-paper-sunken p-lp-1"
    >
      {THEMES.map((option) => (
        <Button
          key={option.value}
          size="sm"
          variant={mounted && theme === option.value ? "primary" : "ghost"}
          aria-pressed={mounted ? theme === option.value : undefined}
          onClick={() => {
            setTheme(option.value);
          }}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

function Pane({ pin, title, note }: { pin: "light" | "dark"; title: string; note: string }) {
  return (
    <div
      data-theme={pin}
      data-lp-surface=""
      className={cn(
        "min-w-0 flex-1 rounded-lp-surface border border-lp-rule p-lp-5",
        "bg-lp-paper text-lp-ink",
      )}
    >
      <div className="mb-lp-5 flex flex-col gap-lp-1">
        <h2 className="text-lp-title font-semibold text-lp-ink">{title}</h2>
        <p className="text-lp-caption text-lp-ink-tertiary">{note}</p>
      </div>
      <Gallery scope={pin} />
    </div>
  );
}

/**
 * Letterpress preview route.
 *
 * Every primitive in every state, rendered twice: once pinned light and once
 * pinned dark, side by side. That is the section 7 box "both themes opened
 * and checked" made mechanical rather than a promise, and it is how task 2.3
 * checks it has not regressed anything.
 *
 * Not linked from the product navigation. It is a contributor surface.
 */
export default function DesignPreviewPage() {
  return (
    <main
      data-lp-surface=""
      className="min-h-[100dvh] bg-lp-paper px-lp-5 py-lp-7 font-lp-sans text-lp-ink"
    >
      <header className="mx-auto mb-lp-7 flex max-w-[1400px] flex-wrap items-end justify-between gap-lp-4">
        <div className="flex flex-col gap-lp-2">
          <h1 className="text-lp-display font-semibold tracking-[-0.03em] text-lp-ink">
            Letterpress
          </h1>
          <p className="max-w-[65ch] text-lp-body text-lp-ink-secondary">
            The design system in docs/design/DESIGN-SYSTEM.md, as running code. Every primitive,
            every state, both themes at once.
          </p>
        </div>
        <ThemeSwitch />
      </header>

      <div className="mx-auto flex max-w-[1400px] flex-col gap-lp-5 xl:flex-row">
        <Pane pin="light" title="Light" note="The base definition." />
        <Pane pin="dark" title="Dark" note="A full token swap, not an afterthought." />
      </div>
    </main>
  );
}
