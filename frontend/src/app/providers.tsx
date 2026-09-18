"use client";

import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/design-system";

/**
 * Application-wide client providers.
 *
 * Theme (D-11, DESIGN-SYSTEM.md 2.1 and section 6): `next-themes` was a
 * dependency that nothing imported, while `layout.tsx` hardcoded dark. It now
 * writes `data-theme="light" | "dark"` onto <html>, defaults to the operating
 * system preference, and injects its own blocking script so the correct theme
 * is on the element before first paint - no flash, no hydration mismatch.
 *
 * The `className="dark"` on <html> in `layout.tsx` is deliberately still
 * there. Nothing reads it (no `dark:` variant appears anywhere in
 * `src/components/`), but Tailwind's `darkMode: "class"` is still configured
 * against it and removing it is task 2.3's job, in the same change that moves
 * the ten legacy components onto the Letterpress tokens.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      // DEPRECATED, removed by task 2.3. Left off so next-themes does not
      // write `color-scheme` onto <html>: the ten legacy components are
      // still painted dark from the old tokens, and a resolved light theme
      // would give them light scrollbars and light native controls.
      // Letterpress surfaces set `color-scheme` themselves, scoped to
      // [data-lp-surface] in globals.css.
      enableColorScheme={false}
    >
      <TooltipProvider>{children}</TooltipProvider>
    </ThemeProvider>
  );
}
