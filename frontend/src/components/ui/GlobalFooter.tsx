/**
 * GlobalFooter
 * ============
 * Academic disclaimer footer used on every page of the app.
 * Import and render at the bottom of any page component.
 */
"use client";


export function GlobalFooter() {
  return (
    <footer className="relative z-10 py-8 mt-12 border-t border-border-subtle bg-background">
      <div className="max-w-5xl mx-auto flex flex-col items-center gap-4">
        {/* Disclaimer */}
        <p className="text-[10px] text-foreground/30 text-center leading-relaxed max-w-3xl font-sans font-medium uppercase tracking-[0.1em]">
          Forensic Council is an Academic Project and can occasionally make mistakes. <br />
          All analysis results should be verified by human forensic specialists.
        </p>

        {/* Version tag */}
        <div className="shrink-0 px-4 py-1.5 rounded-full bg-surface-low border border-border-subtle">
          <span className="text-[9px] font-mono text-foreground/20 tracking-widest uppercase">v1.0.4</span>
        </div>
      </div>
    </footer>
  );
}
