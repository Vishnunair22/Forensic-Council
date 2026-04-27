import { Suspense } from "react";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Plus_Jakarta_Sans, Geist_Mono } from "next/font/google";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { RouteExperience } from "@/components/ui/RouteExperience";
import { Toaster } from "@/components/ui/Toaster";
import { QueryProvider } from "@/components/ui/QueryProvider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});


export const metadata: Metadata = {
  title: { default: "Forensic Council", template: "%s | Forensic Council" },
  description: "Multi-Agent Forensic Evidence Analysis System — Court-grade digital evidence verification.",
  openGraph: { type: "website", title: "Forensic Council", siteName: "Forensic Council" },
  robots: { index: false, follow: false },
};

import { LandingBackground } from "@/components/ui/LandingBackground";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${plusJakarta.variable} ${jetbrainsMono.variable} ${geistMono.variable} font-sans text-foreground antialiased min-h-screen flex flex-col overflow-x-hidden`}
      >
        <LandingBackground />
        <Suspense fallback={null}>
          <RouteExperience />
        </Suspense>
        <GlobalNavbar />
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-[9999] focus:top-2 focus:left-2 focus:px-4 focus:py-2 glass-panel font-bold"
        >
          Skip to main content
        </a>

        <QueryProvider>
          <main className="flex-1 relative z-10" id="main-content">
            {children}
          </main>

          <GlobalFooter />
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
