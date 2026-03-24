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
    <footer className="relative z-10 py-12 mt-20 border-t border-border-subtle px-6">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-8">
        {/* Brand mark */}
        <div className="flex items-center gap-3 shrink-0 group">
          <div className="w-8 h-8 rounded-lg border border-border-bold bg-surface-mid flex items-center justify-center shadow-sm transition-all group-hover:border-indigo-400/40">
            <ShieldCheck className="w-4 h-4 text-indigo-400" aria-hidden="true" />
          </div>
          <span className="text-[10px] font-bold text-foreground/40 uppercase tracking-[0.2em]">Forensic Council</span>
        </div>

        {/* Disclaimer */}
        <p className="text-[10px] text-foreground/30 text-center leading-relaxed max-w-md font-mono font-bold uppercase tracking-wider">
          <span className="text-indigo-500/40 mr-1">//</span> ACADEMIC PROJECT. RESULTS ARE AI-GENERATED AND SHOULD NOT BE USED AS SOLE EVIDENCE.
        </p>

        {/* Version tag */}
        <div className="shrink-0 px-3 py-1 rounded-full bg-surface-low border border-border-subtle">
          <span className="text-[9px] font-mono text-foreground/20 font-bold tracking-widest uppercase">Build v1.2.0</span>
        </div>
      </div>
    </footer>
  );
}
