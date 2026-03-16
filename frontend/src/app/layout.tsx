import type { Metadata } from "next";
import { Syne, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { DevErrorProvider } from "@/components/DevErrorOverlay";

const syne = Syne({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-syne",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
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
    <html lang="en" className={`${syne.variable} ${jetbrainsMono.variable}`}>
      <body className="antialiased">
        <DevErrorProvider>
          {children}
        </DevErrorProvider>
      </body>
    </html>
  );
}
