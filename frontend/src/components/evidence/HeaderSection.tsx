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
      className="sticky top-4 max-w-6xl mx-auto flex items-center justify-between mb-12 z-50 px-8 py-5 glass-panel rounded-[2rem] border-white/5 shadow-[0_8px_32px_rgba(0,0,0,0.4)]"
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
        <div className="relative w-11 h-11 flex items-center justify-center rounded-xl bg-gradient-to-br from-cyan-600/30 to-violet-700/30 border border-cyan-400/30 group-hover:border-cyan-300/60 transition-all duration-300 shadow-[0_0_20px_rgba(0,212,255,0.2)]">
          <div className="absolute inset-0 bg-black/20 rounded-xl backdrop-blur-md" />
          <span className="relative z-10 font-black text-white text-sm tracking-widest">FC</span>
        </div>
        <div className="flex flex-col justify-center">
          <span className="text-lg font-bold tracking-tight text-white group-hover:text-cyan-100 transition-colors block leading-tight font-heading">
            Forensic Council
          </span>
          <span className="text-[10px] font-mono text-cyan-400 group-hover:text-cyan-300 uppercase tracking-[0.25em] transition-colors leading-relaxed font-bold">
            Live Stream
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
            className="btn btn-ghost px-5 py-2.5 text-xs uppercase tracking-wider rounded-xl font-semibold border-white/10"
            aria-label="Browse system for new evidence file"
          >
            Browse System
          </motion.button>
        )}
      </div>
    </motion.header>
  );
}
