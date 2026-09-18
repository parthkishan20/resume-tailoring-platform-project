import localFont from "next/font/local";

/**
 * Geist and Geist Mono, self-hosted (DESIGN-SYSTEM.md 2.2 and section 6).
 *
 * The spec's snippet is `import { GeistSans } from "geist/font/sans"`. That
 * import works, but under Next 14.2.5 it also prints
 *
 *   Failed to load font file: .../Geist-Variable.woff2
 *   Error: Unknown font format
 *
 * on every build, for both families, in both the sans and mono entry points.
 * The cause is not the `geist` package: 1.3.1 and 1.7.2 fail identically, and
 * the files are valid woff2. Next 14's font loader cannot read *variable*
 * woff2 metrics, and `geist/font/*` leaves `adjustFontFallback` on, so it
 * tries. The fonts still ship and still render; what silently does not get
 * built is the size-adjusted fallback face, which is the thing that reduces
 * layout shift before the webfont arrives.
 *
 * So the loader is called here instead, against the same files in the `geist`
 * package, with `adjustFontFallback` off and a hand-written fallback stack in
 * its place. Same self-hosted files, no build error, and the fallback is
 * explicit rather than absent. Revisit when the app moves to Next 15, where
 * `geist/font/*` can be used directly.
 */

export const geistSans = localFont({
  src: "../../node_modules/geist/dist/fonts/geist-sans/Geist-Variable.woff2",
  variable: "--font-geist-sans",
  weight: "100 900",
  style: "normal",
  display: "swap",
  adjustFontFallback: false,
  // Inline, not a shared const: the font loader only accepts literals.
  fallback: [
    "ui-sans-serif",
    "system-ui",
    "-apple-system",
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
    "sans-serif",
  ],
});

export const geistMono = localFont({
  src: "../../node_modules/geist/dist/fonts/geist-mono/GeistMono-Variable.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  style: "normal",
  display: "swap",
  adjustFontFallback: false,
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "monospace"],
});
