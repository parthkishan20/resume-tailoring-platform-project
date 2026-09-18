import type { Metadata } from "next";
import { geistMono, geistSans } from "@/design-system/fonts";
import { Providers } from "./providers";
import "./globals.css";

/**
 * Root layout.
 *
 * Geist and Geist Mono only (DESIGN-SYSTEM.md 2.2). Inter, Fraunces and
 * JetBrains Mono are gone: 2.2 bans the first two by name and section 7
 * forbids a serif anywhere in the product. The three `--font-*` variables the
 * deprecated Tailwind keys still read are aliased onto Geist in `globals.css`,
 * so nothing that has not been rewritten yet loses its family.
 *
 * `className="dark"` is gone with them. The theme is resolved by `next-themes`
 * into `data-theme` on this element (D-11), defaulting to the operating system
 * preference, with light as the base token definition.
 */

export const metadata: Metadata = {
  title: "ResumeTailor",
  description: "AI-powered resume tailoring workstation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning is required by next-themes: it writes
    // data-theme onto this element before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
