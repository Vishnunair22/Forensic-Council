import type { Metadata } from "next";
import { Poppins, Fira_Code } from "next/font/google";
import "./globals.css";
import { DevErrorProvider } from "@/components/DevErrorOverlay";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800", "900"],
  variable: "--font-poppins",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-fira-code",
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
    <html lang="en" className={`${poppins.variable} ${firaCode.variable}`}>
      <body className="antialiased">
        <DevErrorProvider>
          {children}
        </DevErrorProvider>
      </body>
    </html>
  );
}
