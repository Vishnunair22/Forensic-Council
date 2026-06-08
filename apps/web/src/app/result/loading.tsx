// Suspense fallback for /result (redirect shell). Solid dark full-viewport cover
// — mirrors result/[sessionId]/loading.tsx — so the hand-off into the report
// never flashes a blank/empty scaffold.
export default function ResultLoading() {
  return (
    <div
      className="fixed inset-0 z-[10001] flex flex-col items-center justify-center bg-background px-6 select-none"
      aria-busy="true"
      aria-label="Loading forensic report"
    >
      <div className="flex items-center gap-4 mb-6">
        <div className="relative w-9 h-9 flex items-center justify-center border border-primary/30 rounded-xl bg-primary/5">
          <span className="absolute inset-0 rounded-xl border border-primary/40 animate-ping" />
          <span className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse" />
        </div>
        <span className="fc-eyebrow fc-text-muted">Council Arbiter</span>
      </div>
      <p className="fc-eyebrow fc-text-muted mb-5">Decrypting Forensic Ledger</p>
      <div className="h-2 w-56 max-w-[70vw] overflow-hidden rounded-full bg-white/10">
        <div className="fc-skeleton h-full w-full rounded-full" />
      </div>
    </div>
  );
}
