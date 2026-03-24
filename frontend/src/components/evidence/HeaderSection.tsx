/**
 * HeaderSection Component
 * =======================
 * 
 * Displays the header with app branding and navigation controls.
 * Located at the top of the evidence page.
 */
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { HistoryDrawer } from "@/components/ui/HistoryDrawer";

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
    <motion.header
      initial={{ y: -40, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="sticky top-4 max-w-6xl mx-auto flex items-center justify-between mb-12 z-50 px-8 py-5 surface-panel rounded-3xl border-border-subtle shadow-xl bg-background/80 backdrop-blur-md"
    >
      {/* Logo and Branding */}
      <div
        role="button"
        tabIndex={0}
        className="flex items-center space-x-4 cursor-pointer group"
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
        <div className="relative w-10 h-10 flex items-center justify-center rounded-xl bg-surface-high border border-border-bold group-hover:border-indigo-500/40 transition-all duration-300 shadow-sm">
          <span className="relative z-10 font-bold text-indigo-400 text-xs tracking-widest">FC</span>
        </div>
        <div className="flex flex-col justify-center">
          <span className="text-base font-bold tracking-tight text-foreground transition-colors block leading-tight">
            Forensic Council
          </span>
          <span className="text-[10px] font-mono text-indigo-500/60 uppercase tracking-[0.2em] transition-colors leading-relaxed font-bold">
            Investigation Node
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <HistoryDrawer />
        
        {/* Browse Button */}
        {showBrowse && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onBrowseClick}
            className="btn btn-secondary px-6 py-2.5 text-[10px] uppercase tracking-widest rounded-xl font-bold border-border-subtle"
            aria-label="Browse system for new evidence file"
          >
            Browse System
          </motion.button>
        )}
      </div>
    </motion.header>
  );
}
