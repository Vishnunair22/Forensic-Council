import type { Metadata } from "next";
import { Cormorant_Garamond, Montserrat, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { DevErrorProvider } from "@/components/DevErrorOverlay";

const cormorantGaramond = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-heading",
});

const montserrat = Montserrat({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800", "900"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Forensic Council | Multi-Agent Analysis System",
  description: "Advanced multi-agent system for digital forensic evidence analysis, deepfake detection, and scene reconstruction.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${cormorantGaramond.variable} ${montserrat.variable} ${jetbrainsMono.variable}`}>
      <body className="antialiased">
        <DevErrorProvider>
          {children}
        </DevErrorProvider>
      </body>
    </html>
  );
}
