import { Suspense } from "react";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { RouteExperience } from "@/components/ui/RouteExperience";
import { Toaster } from "@/components/ui/Toaster";
import { QueryProvider } from "@/components/ui/QueryProvider";
import { LandingBackground } from "@/components/ui/LandingBackground";
import { GlobalLoadingOverlay } from "@/components/ui/GlobalLoadingOverlay";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: { default: "Forensic Council", template: "%s | Forensic Council" },
  description: "Multi-Agent Forensic Evidence Analysis System — Court-grade digital evidence verification.",
  openGraph: { type: "website", title: "Forensic Council", siteName: "Forensic Council" },
  robots: { index: false, follow: false },
};

// V-M-1: themeColor mirrors --color-background (#02040A) so the browser
// chrome / status bar matches the canvas instead of slate-950.
export const viewport = { themeColor: "#02040A", width: "device-width", initialScale: 1 } as const;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="font-sans text-foreground antialiased min-h-screen flex flex-col overflow-x-clip">
        <LandingBackground />
        <Suspense fallback={null}>
          <RouteExperience />
        </Suspense>
        <a
          href="#main-content"
          className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:z-50 focus-visible:top-2 focus-visible:left-2 focus-visible:px-4 focus-visible:py-2 focus-visible:rounded-full fc-surface-elevated fc-text-primary font-semibold text-sm fc-focus-ring"
        >
          Skip to main content
        </a>

        <QueryProvider>
          <GlobalLoadingOverlay />
          <GlobalNavbar />
          <main className="flex-1 relative z-10 pt-16" id="main-content" tabIndex={-1} style={{ outline: "none" }}>
            {children}
          </main>

          <GlobalFooter />
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
