import type { Config } from "tailwindcss";

/**
 * Two token namespaces live here on purpose.
 *
 * The unprefixed keys (`surface`, `accent`, `muted`, ...) are the outgoing
 * "tailor's thread" palette. Ten shipped components still compile against
 * them. DEPRECATED: task 2.3 deletes them together with the legacy `:root`
 * block in `globals.css`.
 *
 * The `lp` keys are the Letterpress system from `docs/design/DESIGN-SYSTEM.md`.
 * Every one resolves to a `--lp-*` custom property defined in
 * `src/design-system/tokens.css`, so this file holds no colour value of its
 * own and the Tailwind v4 migration (decision D6, deferred to task 2.3) is a
 * mechanical lift of these blocks into an `@theme` directive.
 */
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // --- DEPRECATED: removed by task 2.3 -----------------------------
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: "var(--card)",
        surface: {
          1: "var(--surface-1)",
          2: "var(--surface-2)",
        },
        border: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
          hover: "var(--primary-hover)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
          hover: "var(--accent-hover)",
          dim: "var(--accent-dim)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        faint: "var(--faint-foreground)",
        input: "var(--input)",
        ring: "var(--ring)",
        error: "var(--error)",
        warning: "var(--warning)",
        success: "var(--success)",
        destructive: "var(--destructive)",

        // --- Letterpress (DESIGN-SYSTEM.md 2.1) ---------------------------
        lp: {
          paper: {
            DEFAULT: "var(--lp-paper)",
            raised: "var(--lp-paper-raised)",
            sunken: "var(--lp-paper-sunken)",
            overlay: "var(--lp-paper-overlay)",
          },
          ink: {
            DEFAULT: "var(--lp-ink)",
            secondary: "var(--lp-ink-secondary)",
            tertiary: "var(--lp-ink-tertiary)",
          },
          rule: {
            DEFAULT: "var(--lp-rule)",
            strong: "var(--lp-rule-strong)",
            control: "var(--lp-rule-control)",
          },
          accent: {
            DEFAULT: "var(--lp-accent)",
            hover: "var(--lp-accent-hover)",
            active: "var(--lp-accent-active)",
            contrast: "var(--lp-accent-contrast)",
            wash: "var(--lp-accent-wash)",
            edge: "var(--lp-accent-edge)",
          },
          positive: {
            DEFAULT: "var(--lp-positive)",
            wash: "var(--lp-positive-wash)",
          },
          caution: {
            DEFAULT: "var(--lp-caution)",
            wash: "var(--lp-caution-wash)",
          },
          critical: {
            DEFAULT: "var(--lp-critical)",
            wash: "var(--lp-critical-wash)",
          },
          focus: "var(--lp-focus-ring)",
          scrim: "var(--lp-scrim)",
        },
      },
      fontFamily: {
        // DEPRECATED: removed by task 2.3.
        sans: ["var(--font-inter)", "sans-serif"],
        display: ["var(--font-fraunces)", "serif"],
        mono: ["var(--font-mono)", "monospace"],
        // Letterpress (2.2). One sans family, one mono. No display serif.
        "lp-sans": ["var(--font-geist-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        "lp-mono": ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      // Letterpress type scale (2.2). 12px is the floor; there is no smaller key.
      fontSize: {
        "lp-display": [
          "var(--lp-text-display)",
          { lineHeight: "var(--lp-leading-display)", letterSpacing: "var(--lp-tracking-display)" },
        ],
        "lp-title": [
          "var(--lp-text-title)",
          { lineHeight: "var(--lp-leading-tight)", letterSpacing: "var(--lp-tracking-title)" },
        ],
        "lp-heading": ["var(--lp-text-heading)", { lineHeight: "var(--lp-leading-tight)" }],
        "lp-body": ["var(--lp-text-body)", { lineHeight: "var(--lp-leading-body)" }],
        "lp-label": ["var(--lp-text-label)", { lineHeight: "var(--lp-leading-tight)" }],
        "lp-caption": ["var(--lp-text-caption)", { lineHeight: "var(--lp-leading-body)" }],
        "lp-code": ["var(--lp-text-code)", { lineHeight: "var(--lp-leading-code)" }],
      },
      // Letterpress space and layout scale (2.4).
      spacing: {
        "lp-1": "var(--lp-space-1)",
        "lp-2": "var(--lp-space-2)",
        "lp-3": "var(--lp-space-3)",
        "lp-4": "var(--lp-space-4)",
        "lp-5": "var(--lp-space-5)",
        "lp-6": "var(--lp-space-6)",
        "lp-7": "var(--lp-space-7)",
        "lp-8": "var(--lp-space-8)",
        "lp-control": "var(--lp-control-h)",
        "lp-control-compact": "var(--lp-control-h-compact)",
        "lp-control-primary": "var(--lp-control-h-primary)",
        "lp-panel-header": "var(--lp-panel-header-h)",
        "lp-inspector": "var(--lp-inspector-w)",
        "lp-nav": "var(--lp-nav-w)",
        "lp-nav-collapsed": "var(--lp-nav-w-collapsed)",
      },
      backgroundImage: {
        "lp-shimmer": "var(--lp-shimmer)",
      },
      // Letterpress shape scale (2.3). Three radii, no others.
      borderRadius: {
        "lp-control": "var(--lp-radius-control)",
        "lp-surface": "var(--lp-radius-surface)",
        "lp-pill": "var(--lp-radius-pill)",
      },
      // Letterpress elevation (2.5).
      boxShadow: {
        "lp-raised": "var(--lp-shadow-raised)",
        "lp-overlay": "var(--lp-shadow-overlay)",
        "lp-page": "var(--lp-shadow-page)",
      },
      // Letterpress motion (2.7). Every duration maps to a row in that table.
      transitionDuration: {
        "lp-press": "80ms",
        "lp-swap": "120ms",
        "lp-toast": "160ms",
      },
      transitionTimingFunction: {
        "lp-out": "var(--lp-ease-out)",
      },
      keyframes: {
        "lp-shimmer": {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "lp-toast-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "lp-toast-out": {
          from: { opacity: "1", transform: "translateY(0)" },
          to: { opacity: "0", transform: "translateY(8px)" },
        },
        "lp-fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "lp-shimmer": "lp-shimmer 1.4s linear infinite",
        "lp-toast-in": "lp-toast-in 160ms var(--lp-ease-out)",
        "lp-toast-out": "lp-toast-out 160ms var(--lp-ease-out)",
        "lp-fade-in": "lp-fade-in 120ms linear",
      },
    },
  },
  plugins: [],
};
export default config;
