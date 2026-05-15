import { Suspense } from "react";
import type { Metadata } from "next";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { RouteExperience } from "@/components/ui/RouteExperience";
import { Toaster } from "@/components/ui/Toaster";
import { QueryProvider } from "@/components/ui/QueryProvider";
import { LandingBackground } from "@/components/ui/LandingBackground";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-mono-family",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Forensic Council", template: "%s | Forensic Council" },
  description: "Multi-Agent Forensic Evidence Analysis System — Court-grade digital evidence verification.",
  openGraph: { type: "website", title: "Forensic Council", siteName: "Forensic Council" },
  robots: { index: false, follow: false },
};

export const viewport = { themeColor: "#020617", width: "device-width", initialScale: 1 } as const;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} font-sans text-foreground antialiased min-h-screen flex flex-col overflow-x-clip`}>
        <LandingBackground />
        <Suspense fallback={null}>
          <RouteExperience />
        </Suspense>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-[9999] focus:top-2 focus:left-2 focus:px-4 focus:py-2 glass-panel font-bold"
        >
          Skip to main content
        </a>

        <QueryProvider>
          <GlobalNavbar />
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
