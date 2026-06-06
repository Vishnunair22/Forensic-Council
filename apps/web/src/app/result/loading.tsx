export default function ResultLoading() {
  return (
    <div
      className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4"
      aria-busy="true"
      aria-label="Loading forensic report"
    >
      <div className="w-full max-w-2xl space-y-6">
        {/* Verdict header skeleton */}
        <div className="fc-skeleton h-10 w-48 rounded-lg mx-auto" />
        {/* Confidence bar */}
        <div className="fc-skeleton h-3 w-full rounded-full" />
        {/* Agent cards row */}
        <div className="grid grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="fc-skeleton h-24 rounded-[var(--radius-2xl)]" />
          ))}
        </div>
        {/* Report body */}
        <div className="space-y-3">
          <div className="fc-skeleton h-4 w-full rounded" />
          <div className="fc-skeleton h-4 w-5/6 rounded" />
          <div className="fc-skeleton h-4 w-4/6 rounded" />
        </div>
      </div>
    </div>
  );
}
