import { Suspense } from "react";
import { Poppins, Geist, Geist_Mono } from "next/font/google";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { RouteExperience } from "@/components/ui/RouteExperience";
import { Toaster } from "@/components/ui/Toaster";
import { GlobalBackground } from "@/components/ui/GlobalBackground";
import { QueryProvider } from "@/components/ui/QueryProvider";
import "./globals.css";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-poppins",
  display: "swap",
});

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata = {
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
        className={`${poppins.variable} ${geist.variable} ${geistMono.variable} font-sans text-slate-100 antialiased min-h-screen flex flex-col`}
      >
        <GlobalBackground />
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
            {children}
          </main>

          <GlobalFooter />
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
