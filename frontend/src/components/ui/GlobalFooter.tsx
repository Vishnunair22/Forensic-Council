"use client";

import { AlertCircle } from "lucide-react";

export function GlobalFooter() {
  return (
    <footer className="w-full border-t border-white/5 bg-slate-950/80 backdrop-blur-md py-6 px-6 relative z-50">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-center gap-2 text-center">
        <AlertCircle className="w-4 h-4 text-slate-500" aria-hidden="true" />
        <p className="text-sm text-slate-500 font-light tracking-wide">
          Forensic Council is an academic project and can occasionally make mistakes.
        </p>
      </div>
    </footer>
  );
}
