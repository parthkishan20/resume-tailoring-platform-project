import * as React from "react";
import { render, type RenderResult } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastHost, TooltipProvider } from "@/design-system";

/**
 * The provider stack the workspace needs, for tests.
 *
 * Not in a `__tests__` directory on purpose: jest treats every file under one
 * as a suite, and a helper with no `test()` in it fails the run.
 *
 * `retry: false` is the one deliberate difference from `app/providers.tsx`. A
 * test that asserts on an error state should reach it on the first rejection
 * rather than after the production retry, and a test that asserts on success
 * should not be able to pass because a retry papered over a first failure.
 */
/**
 * jsdom has no `matchMedia`, and `next-themes` calls it on mount to read
 * `prefers-color-scheme`. Added here rather than in
 * `design-system/test-polyfills.ts`, which belongs to task 1.4.
 *
 * It answers "no match" to everything, which resolves `system` to light: light
 * is the base token definition (DESIGN-SYSTEM.md 2.1), so that is the right
 * default for a test that has not said otherwise.
 */
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  });
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderInWorkspace(
  ui: React.ReactElement,
  options: { queryClient?: QueryClient } = {},
): RenderResult & { queryClient: QueryClient } {
  const queryClient = options.queryClient ?? createTestQueryClient();

  const result = render(
    <ThemeProvider attribute="data-theme" defaultTheme="light" enableColorScheme={false}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <ToastHost>{ui}</ToastHost>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );

  return { ...result, queryClient };
}
