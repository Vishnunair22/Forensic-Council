import { Suspense } from "react";
import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Orbitron } from "next/font/google";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { RouteExperience } from "@/components/ui/RouteExperience";
import { Toaster } from "@/components/ui/Toaster";
import { DarkBackgroundAnimation } from "@/components/ui/DarkBackgroundAnimation";
import { QueryProvider } from "@/components/ui/QueryProvider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Forensic Council", template: "%s | Forensic Council" },
  description: "Multi-Agent Forensic Evidence Analysis System — Court-grade digital evidence verification.",
  openGraph: { type: "website", title: "Forensic Council", siteName: "Forensic Council" },
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${orbitron.variable} ${jetbrainsMono.variable} font-sans text-slate-100 antialiased min-h-screen flex flex-col`}
      >
        <DarkBackgroundAnimation />
        <Suspense fallback={null}>
          <RouteExperience />
        </Suspense>
        <GlobalNavbar />

        {/* Skip navigation — visible on focus for keyboard users */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-[9999] focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-sky-500 focus:text-white focus:rounded focus:font-bold"
        >
          Skip to main content
        </a>

        <QueryProvider>
          <main className="flex-1 relative z-10" id="main-content">
            {/* Navbar Safe Zone / Masking Gradient */}
            <div className="fixed top-0 left-0 right-0 h-32 bg-gradient-to-b from-background via-background/80 to-transparent pointer-events-none z-[150] opacity-60" />
            
            {children}
          </main>

          <GlobalFooter />
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
