import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";
import { DevErrorProvider } from "@/components/DevErrorOverlay";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
  variable: "--font-poppins",
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
    <html lang="en" className={poppins.variable}>
      <head>
        <meta
          httpEquiv="Content-Security-Policy"
          content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' ws: wss:; font-src 'self';"
        />
      </head>
      <body className="antialiased">
        <DevErrorProvider>
          {children}
        </DevErrorProvider>
      </body>
    </html>
  );
}
