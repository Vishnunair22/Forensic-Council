export default function EvidenceLoading() {
  return (
    <div
      className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4"
      aria-busy="true"
      aria-label="Loading evidence analysis"
    >
      <div className="w-full max-w-xl space-y-4">
        {/* Upload zone skeleton */}
        <div className="fc-skeleton rounded-[var(--radius-4xl)] h-64 w-full" />
        {/* Button row */}
        <div className="flex gap-3 justify-center">
          <div className="fc-skeleton h-11 w-36 rounded-full" />
          <div className="fc-skeleton h-11 w-28 rounded-full" />
        </div>
      </div>
    </div>
  );
}
