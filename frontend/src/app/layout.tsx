import type { Metadata } from "next";
import "./globals.css";
import { DevErrorProvider } from "@/components/DevErrorOverlay";

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
    <html lang="en">
      <body className="antialiased">
        <DevErrorProvider>
          {children}
        </DevErrorProvider>
      </body>
    </html>
  );
}
