import { Poppins, Fira_Code } from "next/font/google";
import { GlobalNavbar } from "@/components/ui/GlobalNavbar";
import { GlobalFooter } from "@/components/ui/GlobalFooter";
import { GlassBackground } from "@/components/ui/GlassBackground";
import { DevErrorProvider } from "@/components/DevErrorOverlay";
import "./globals.css";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800", "900"],
  variable: "--font-poppins",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-fira-code",
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
    <html lang="en" dir="ltr" className="dark">
      <body className={`${poppins.variable} ${firaCode.variable} font-sans text-slate-50 antialiased min-h-screen flex flex-col`} style={{ background: "transparent" }}>
        {/* Shared glass background — visible on all pages */}
        <GlassBackground />
        <GlobalNavbar />

        {/* Skip navigation — visible on focus for keyboard users */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-[9999] focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-cyan-500 focus:text-black focus:rounded focus:font-bold"
        >
          Skip to main content
        </a>
        {/* Main content takes up available space */}
        <div className="flex-1 relative z-10" id="main-content">
          <DevErrorProvider>
            {children}
          </DevErrorProvider>
        </div>
        
        {/* Global Footer anchors to the bottom of the layout */}
        <GlobalFooter />
      </body>
    </html>
  );
}
