"use client";

export function GlobalFooter() {
  return (
    <footer
      className="relative z-10 py-8 mt-12"
      style={{ borderTop: "1px solid rgba(255,255,255,0.05)", background: "rgba(3,11,26,0.4)" }}
    >
      <div className="max-w-5xl mx-auto flex flex-col items-center gap-4">
        <p className="text-[9px] text-white/20 text-center leading-relaxed max-w-3xl font-sans font-medium uppercase tracking-[0.12em]">
          Forensic Council is an Academic Project and can occasionally make mistakes.{" "}
          <br />
          All analysis results should be verified by human forensic specialists.
        </p>
        <div
          className="shrink-0 px-4 py-1.5 rounded-full"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.06)"
          }}
        >
          <span className="text-[8px] font-mono text-white/15 tracking-widest uppercase">v1.0.4</span>
        </div>
      </div>
    </footer>
  );
}
