/**
 * GlobalFooter
 * ============
 * Academic disclaimer footer used on every page of the app.
 * Import and render at the bottom of any page component.
 */
"use client";

import { ShieldCheck } from "lucide-react";

export function GlobalFooter() {
  return (
    <footer className="relative z-10 py-8 border-t border-white/[0.06] px-6">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* Brand mark */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-6 h-6 rounded bg-gradient-to-br from-cyan-400/80 to-violet-500/60 flex items-center justify-center">
            <ShieldCheck className="w-3.5 h-3.5 text-white" aria-hidden="true" />
          </div>
          <span className="text-xs font-semibold text-slate-500 tracking-wide">Forensic Council</span>
        </div>

        {/* Disclaimer */}
        <p className="text-xs text-slate-600 text-center leading-relaxed max-w-xl">
          Forensic Council is an academic project and can occasionally make mistakes.
          Results are AI-generated and should not be used as sole evidence in legal proceedings.
        </p>

        {/* Version tag */}
        <span className="text-[10px] font-mono text-slate-700 shrink-0">v1.0.5</span>
      </div>
    </footer>
  );
}
