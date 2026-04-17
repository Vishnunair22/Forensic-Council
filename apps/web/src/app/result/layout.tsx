import type { Metadata } from "next";

export const metadata: Metadata = { title: "Investigation Report" };

export default function ResultLayout({ children }: { children: React.ReactNode }) {
  return children;
}
