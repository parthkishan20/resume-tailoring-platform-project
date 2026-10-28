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

/**
 * Link-preview (Open Graph and Twitter card) metadata.
 *
 * The app has no public deployment, so the canonical URL is the GitHub repo and
 * the card image is served by raw.githubusercontent.com from `public/og-image.png`
 * on `main`. Both must be absolute https URLs for LinkedIn's crawler. When the app
 * gets a real host, change these two constants (and keep the trailing slash).
 * Titles stay under 70 characters and descriptions under 160, with no em-dashes.
 */
const SITE_URL = "https://github.com/parthkishan20/resume-tailoring-platform-project/";
const OG_IMAGE_URL =
  "https://raw.githubusercontent.com/parthkishan20/resume-tailoring-platform-project/main/frontend/public/og-image.png";
const OG_TITLE = "ResumeTailor: AI resume tailoring workstation";
const OG_DESCRIPTION =
  "Keep one master resume in YAML, tailor it to any job description, and edit it by chat with an AI assistant.";

export const metadata: Metadata = {
  title: "ResumeTailor",
  description: OG_DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "Parthkumar Patel",
    title: OG_TITLE,
    description: OG_DESCRIPTION,
    url: SITE_URL,
    images: [{ url: OG_IMAGE_URL, width: 1200, height: 627, alt: "ResumeTailor screenshot" }],
  },
  twitter: {
    card: "summary_large_image",
    title: OG_TITLE,
    description: OG_DESCRIPTION,
    images: [OG_IMAGE_URL],
  },
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
