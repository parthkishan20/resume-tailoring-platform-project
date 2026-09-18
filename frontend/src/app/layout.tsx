import type { Metadata } from "next";
import { Inter, Fraunces, JetBrains_Mono } from "next/font/google";
import { geistMono, geistSans } from "@/design-system/fonts";
import { Providers } from "./providers";
import "./globals.css";

// DEPRECATED (DESIGN-SYSTEM.md 1, rows 3 and 4): Fraunces is a banned display
// serif and Inter is the discouraged body default. They stay only so the ten
// components under src/components/ keep rendering. Task 2.3 removes all three
// of these along with the matching fontFamily keys in tailwind.config.ts.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  axes: ["opsz"],
});
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

// Letterpress (DESIGN-SYSTEM.md 2.2). Self-hosted through next/font/local,
// so no <link> to Google Fonts is emitted and the files are served from the
// app's own origin. See src/design-system/fonts.ts for why the loader is
// called there rather than importing `geist/font/sans` directly.
const letterpressFonts = `${geistSans.variable} ${geistMono.variable}`;

export const metadata: Metadata = {
  title: "ResumeTailor",
  description: "AI-powered resume tailoring workstation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning is required by next-themes: it writes
    // data-theme onto this element before React hydrates.
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${fraunces.variable} ${jetbrainsMono.variable} ${letterpressFonts} antialiased`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
