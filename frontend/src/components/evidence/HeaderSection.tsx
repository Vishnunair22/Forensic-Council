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
        <div className="w-10 h-10 bg-emerald-500/10 border border-emerald-500/30 rounded-lg flex items-center justify-center font-bold text-emerald-400 group-hover:bg-emerald-500/20 transition-colors shadow-[0_0_15px_rgba(16,185,129,0.1)]">
          FC
        </div>
        <span className="text-xl font-bold tracking-tight">Forensic Council</span>
      </div>

      {/* Browse Button */}
      {showBrowse && (
        <button
          onClick={onBrowseClick}
          className="text-emerald-400 font-mono text-sm hover:underline hover:text-emerald-300 transition-colors"
          aria-label="Browse system for new evidence file"
        >
          Browse System
        </button>
      )}
    </header>
  );
}
