import type { Metadata } from "next";

export const metadata: Metadata = { title: "Evidence Analysis" };

export default function EvidenceLayout({ children }: { children: React.ReactNode }) {
  return children;
}
