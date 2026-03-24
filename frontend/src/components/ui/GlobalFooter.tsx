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
    <footer className="relative z-10 py-10 mt-12 border-t border-white/[0.04] px-6 bg-gradient-to-b from-transparent to-black/40">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Brand mark */}
        <div className="flex items-center gap-3 shrink-0 opacity-80 hover:opacity-100 transition-opacity">
          <div className="w-7 h-7 rounded border border-white/10 bg-gradient-to-br from-cyan-900/40 to-violet-900/40 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4 text-cyan-400" aria-hidden="true" />
          </div>
          <span className="text-xs font-semibold text-slate-200 uppercase tracking-widest">Forensic Council</span>
        </div>

        {/* Disclaimer */}
        <p className="text-[12px] text-slate-300 text-center leading-loose max-w-lg font-mono">
          <span className="text-cyan-400">///</span> FORENSIC COUNCIL IS AN ACADEMIC PROJECT. RESULTS ARE AI-GENERATED AND SHOULD NOT BE USED AS SOLE EVIDENCE.
        </p>

        {/* Version tag */}
        <div className="shrink-0 px-3 py-1 rounded-full bg-white/[0.05] border border-white/[0.1]">
          <span className="text-[11px] font-mono text-slate-400 tracking-wider">v1.2.0</span>
        </div>
      </div>
    </footer>
  );
}
