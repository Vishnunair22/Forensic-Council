import { Suspense } from "react";
import { Outfit, Geist, Geist_Mono } from "next/font/google";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { RouteExperience } from "@/components/ui/RouteExperience";
import { Toaster } from "@/components/ui/Toaster";
import { GlobalBackground } from "@/components/ui/GlobalBackground";
import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-outfit",
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
  title: "Forensic Council",
  description: "Multi Agent Forensic Evidence Analysis System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <body
        className={`${outfit.variable} ${geist.variable} ${geistMono.variable} font-sans text-slate-100 antialiased min-h-screen flex flex-col`}
        style={{ background: "#080c14" }}
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

        <div className="flex-1 relative z-10" id="main-content">
          {children}
        </div>

        <GlobalFooter />
        <Toaster />
      </body>
    </html>
  );
}
