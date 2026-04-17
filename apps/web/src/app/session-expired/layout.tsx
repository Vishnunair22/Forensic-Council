import type { Metadata } from "next";

export const metadata: Metadata = { title: "Session Expired" };

export default function SessionExpiredLayout({ children }: { children: React.ReactNode }) {
  return children;
}
