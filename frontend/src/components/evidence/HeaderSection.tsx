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
      className="sticky top-3 max-w-6xl mx-auto flex items-center justify-between mb-6 z-50 px-5 py-3 surface-panel rounded-2xl border-border-subtle shadow-lg bg-background/80 backdrop-blur-md"
    >
      {/* Logo and Branding */}
      <button
        type="button"
        className="flex items-center space-x-4 cursor-pointer group"
        onClick={() => {
          if (status !== "analyzing") router.push("/");
        }}
        aria-label="Return to Forensic Council home"
      >
        <div className="relative w-8 h-8 flex items-center justify-center rounded bg-amber-500/10 border border-amber-500/20 group-hover:border-amber-400/50 transition-all duration-300 shadow-sm">
          <span className="relative z-10 font-black text-amber-500 text-[10px] tracking-widest">FC</span>
        </div>
        <div className="flex flex-col justify-center">
          <span className="text-[11px] font-black tracking-[0.1em] text-white transition-colors block leading-tight uppercase">
            Forensic Council
          </span>
          <span className="text-[8px] font-mono text-amber-500/60 uppercase tracking-[0.3em] transition-colors leading-relaxed font-bold">
            Investigation Node
          </span>
        </div>
      </button>

      <div className="flex items-center gap-3">
        <HistoryDrawer />
        
        {/* Browse Button */}
        {showBrowse && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onBrowseClick}
            className="btn-premium-glass px-6 py-2 border-white/5"
            aria-label="Browse system for new evidence file"
          >
            Browse System
          </motion.button>
        )}
      </div>
    </motion.header>
  );
}
