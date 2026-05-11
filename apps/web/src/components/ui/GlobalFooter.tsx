export function GlobalFooter() {
  return (
    <footer
      className="w-full px-6 py-8 relative z-10 mt-auto overflow-hidden"
      style={{ borderTop: "1px solid rgba(165,200,255,0.06)" }}
    >
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-[11px] font-mono text-white/22 leading-relaxed">
          Forensic Council · Academic project · AI analysis may contain errors
        </p>
        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{
              background: "var(--color-success)",
              boxShadow: "0 0 6px rgba(45,212,160,0.6)",
            }}
          />
          <span className="text-[9px] font-mono text-white/18 tracking-[0.2em] uppercase">System Online</span>
        </div>
      </div>
    </footer>
  );
}
