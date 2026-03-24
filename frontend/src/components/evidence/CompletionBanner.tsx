/**
 * CompletionBanner Component
 * ==========================
 * 
 * Displays a completion banner when the forensic analysis is complete.
 * Shows summary info and action buttons for viewing results.
 */

import { motion } from "framer-motion";
import { CheckCircle2, ArrowRight, RotateCcw, FileText, ShieldCheck } from "lucide-react";
import { useSound } from "@/hooks/useSound";
import { useEffect } from "react";

interface CompletionBannerProps {
  agentCount: number;
  completedCount: number;
  onViewResults: () => void;
  onAnalyzeNew: () => void;
}

export function CompletionBanner({
  agentCount,
  completedCount,
  onViewResults,
  onAnalyzeNew,
}: CompletionBannerProps) {
  const { playSound } = useSound();

  useEffect(() => {
    playSound("complete");
  }, [playSound]);

  return (
    <motion.div
      key="completion"
      initial={{ opacity: 0, scale: 0.98, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col items-center justify-center min-h-[60vh] max-w-3xl mx-auto"
    >
      {/* Success Icon */}
      <motion.div
        initial={{ scale: 0, rotate: -30 }}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ delay: 0.2, type: "spring", stiffness: 200, damping: 20 }}
        className="mb-10 relative group"
      >
        <div className="absolute inset-0 bg-emerald-500/20 blur-xl rounded-full group-hover:bg-emerald-500/30 transition-colors" />
        <div className="relative w-28 h-28 rounded-full bg-gradient-to-br from-emerald-500/20 to-emerald-900/40 border border-emerald-400/50 flex items-center justify-center shadow-[0_0_50px_rgba(16,185,129,0.3),inset_0_0_20px_rgba(16,185,129,0.2)]">
          <ShieldCheck className="w-14 h-14 text-emerald-300 drop-shadow-[0_0_15px_rgba(16,185,129,0.8)]" strokeWidth={1.5} />
        </div>
      </motion.div>

      {/* Completion Message */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.5 }}
        className="text-center mb-10"
      >
        <h2 className="text-4xl md:text-5xl font-black mb-5 tracking-tight bg-gradient-to-br from-white via-emerald-100 to-emerald-400/60 bg-clip-text text-transparent pb-1">
          Analysis Complete.
        </h2>
        <p className="text-slate-400 text-lg max-w-2xl mx-auto mb-6 leading-relaxed">
          The autonomous synthesis layer has finalised its review. {completedCount} forensic agents have compiled their respective findings across all vectors.
        </p>
        <div 
          role="status"
          aria-live="polite"
          className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono tracking-widest uppercase shadow-[0_0_20px_rgba(16,185,129,0.15)]"
        >
          <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
          <span>{completedCount} / {agentCount} agents verified</span>
        </div>
      </motion.div>

      {/* Details Grid */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4, duration: 0.5 }}
        className="w-full grid grid-cols-1 md:grid-cols-2 gap-5 mb-10"
      >
        <div className="p-5 rounded-2xl glass-panel bg-white/[0.02] border border-white/[0.06] flex flex-col justify-center">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] mb-3">Integrity Check</p>
          <p className="text-xl font-black text-emerald-400 flex items-center gap-2 tracking-wide">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" aria-hidden="true" /> SECURE
          </p>
        </div>
        <div className="p-5 rounded-2xl glass-panel bg-white/[0.02] border border-white/[0.06] flex flex-col justify-center">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-[0.2em] mb-3">Cross-Validation</p>
          <p className="text-xl font-black text-white px-1 tracking-wide">{completedCount} <span className="text-slate-500 font-medium">/ {agentCount} pass</span></p>
        </div>
      </motion.div>

      {/* Action Buttons */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.5 }}
        className="w-full max-w-md flex flex-col gap-4"
      >
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => { playSound("click"); onViewResults(); }}
          className="btn btn-primary w-full py-4 rounded-xl font-bold text-base tracking-wide flex items-center justify-center gap-2 shadow-[0_0_30px_rgba(0,212,255,0.25)] relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-150%] animate-[shimmer_2s_infinite]" />
          <FileText className="w-5 h-5 relative z-10" aria-hidden="true" />
          <span className="relative z-10">Access Arbiter Report</span>
          <ArrowRight className="w-5 h-5 relative z-10" aria-hidden="true" />
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => { playSound("click"); onAnalyzeNew(); }}
          className="btn btn-ghost w-full py-4 rounded-xl text-sm font-semibold tracking-wide text-slate-300 hover:text-white border border-white/5 hover:border-white/10 transition-colors"
        >
          <RotateCcw className="w-4 h-4 opacity-70" aria-hidden="true" />
          Analyse New Evidence
        </motion.button>
      </motion.div>

      {/* Footer Note */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
        className="mt-8 text-xs text-slate-500 text-center"
      >
        All evidence and analysis data is encrypted and stored securely in your
        session. Conclusions should be reviewed by human investigators before
        use in official proceedings.
      </motion.p>
    </motion.div>
  );
}
