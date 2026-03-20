/**
 * HeaderSection Component
 * =======================
 * 
 * Displays the header with app branding and navigation controls.
 * Located at the top of the evidence page.
 */

import { useRouter } from "next/navigation";

interface HeaderSectionProps {
  /** Status of the investigation */
  status: string;
  /** Whether to show the browse system button */
  showBrowse: boolean;
  /** Callback when browse is clicked */
  onBrowseClick: () => void;
}

export function HeaderSection({
  status,
  showBrowse,
  onBrowseClick,
}: HeaderSectionProps) {
  const router = useRouter();

  return (
    <header className="max-w-6xl mx-auto flex items-center justify-between mb-8 z-10 relative">
      {/* Logo and Branding */}
      <div
        role="button"
        tabIndex={0}
        className="flex items-center space-x-3 cursor-pointer group"
        onClick={() => {
          if (status !== "analyzing") router.push("/");
        }}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && status !== "analyzing") {
            e.preventDefault();
            router.push("/");
          }
        }}
        aria-label="Return to Forensic Council home"
      >
        <div className="w-10 h-10 bg-gradient-to-br from-emerald-500/18 to-emerald-600/8
          border border-emerald-500/35 rounded-xl flex items-center justify-center
          font-bold text-emerald-300 text-sm
          group-hover:border-emerald-400/55 group-hover:bg-emerald-500/25
          transition-all duration-200 shadow-[0_0_18px_rgba(16,185,129,0.14)]">
          FC
        </div>
        <div>
          <span className="text-lg font-bold tracking-tight text-white block leading-tight">Forensic Council</span>
          <span className="text-[10px] font-mono text-slate-600 uppercase tracking-widest">Evidence Analysis</span>
        </div>
      </div>

      {/* Browse Button */}
      {showBrowse && (
        <button
          onClick={onBrowseClick}
          className="btn btn-ghost px-4 py-2 text-sm rounded-xl"
          aria-label="Browse system for new evidence file"
        >
          Browse System
        </button>
      )}
    </header>
  );
}
