"use client";

import * as React from "react";
import { ThemeProvider } from "next-themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastHost, TooltipProvider } from "@/design-system";

/**
 * Application-wide client providers.
 *
 * Theme (D-11, DESIGN-SYSTEM.md 2.1 and section 6). `next-themes` writes
 * `data-theme="light" | "dark"` onto <html>, defaults to the operating system
 * preference, and injects its own blocking script so the correct theme is on
 * the element before first paint: no flash, no hydration mismatch.
 *
 * `enableColorScheme` stays off deliberately. `globals.css` sets
 * `color-scheme: var(--lp-color-scheme)` on `:root`, which flips with the
 * theme attribute; letting next-themes also write an inline `color-scheme`
 * would give one value two sources, and the inline style would win.
 *
 * Server state (AGENTS.md section 9: "Server state in TanStack Query; UI state
 * in component state"). The client is created inside a `useState` initialiser
 * so a re-render never swaps the cache out from under the tree, and never
 * shared across requests.
 */

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A single-user workstation: nothing changes behind the user's back
        // except through their own mutations, which invalidate explicitly.
        // A short window is enough to dedupe remounts without going stale.
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(makeQueryClient);

  return (
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      enableColorScheme={false}
    >
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <ToastHost>{children}</ToastHost>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
