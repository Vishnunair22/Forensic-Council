"use client";

import { AlertCircle } from "lucide-react";

export function GlobalFooter() {
  return (
    <footer
      className="w-full py-5 px-6 relative z-50"
      style={{
        borderTop: "1px solid rgba(255,255,255,0.04)",
        background: "rgba(8,12,20,0.6)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
      }}
    >
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-center gap-2 text-center">
        <AlertCircle className="w-3.5 h-3.5 shrink-0" style={{ color: "rgba(255,255,255,0.2)" }} aria-hidden="true" />
        <p
          className="text-xs font-light"
          style={{ color: "rgba(255,255,255,0.25)", letterSpacing: "0.02em" }}
        >
          Forensic Council is an academic project and can occasionally make mistakes.
        </p>
      </div>
    </footer>
  );
}
