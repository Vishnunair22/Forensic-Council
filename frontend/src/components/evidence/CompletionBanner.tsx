/**
 * CompletionBanner Component
 * ==========================
 * 
 * Displays a completion banner when the forensic analysis is complete.
 * Shows summary info and action buttons for viewing results.
 */

import { motion } from "framer-motion";
import { CheckCircle2, ArrowRight, RotateCcw, FileText } from "lucide-react";

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
  return (
    <motion.div
      key="completion"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, y: 20 }}
      className="flex flex-col items-center justify-center min-h-[60vh] max-w-3xl mx-auto"
    >
      {/* Success Icon */}
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.2, type: "spring", stiffness: 100 }}
        className="mb-8"
      >
        <div className="w-24 h-24 rounded-full bg-emerald-500/10 border-2 border-emerald-500/30 flex items-center justify-center shadow-[0_0_40px_rgba(16,185,129,0.2)]">
          <CheckCircle2 className="w-12 h-12 text-emerald-400" />
        </div>
      </motion.div>

      {/* Completion Message */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="text-center mb-8"
      >
        <h2 className="text-4xl md:text-5xl font-black mb-4 tracking-tight text-white">
          Council Consensus Reached.
        </h2>
        <p className="text-slate-400 text-lg max-w-2xl mx-auto mb-4">
          All {completedCount} forensic agents have completed their analysis and
          compiled their findings. The evidence has been thoroughly examined from
          multiple perspectives.
        </p>
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-sm font-mono tracking-wide">
          <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
          <span>{completedCount} of {agentCount} agents reported</span>
        </div>
      </motion.div>

      {/* Details Grid */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="w-full grid grid-cols-1 md:grid-cols-2 gap-4 mb-8"
      >
        <div className="p-4 rounded-xl glass-panel border border-white/[0.08]">
          <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-2">Analysis Status</p>
          <p className="text-base font-semibold text-emerald-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" aria-hidden="true" /> Complete
          </p>
        </div>
        <div className="p-4 rounded-xl glass-panel border border-white/[0.08]">
          <p className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-2">Agents Deployed</p>
          <p className="text-base font-semibold text-white">{completedCount} <span className="text-slate-500">/ {agentCount}</span></p>
        </div>
      </motion.div>

      {/* Action Buttons */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="w-full max-w-md flex flex-col gap-3"
      >
        <button
          onClick={onViewResults}
          className="btn btn-primary w-full py-4 rounded-xl font-bold text-base"
        >
          <FileText className="w-5 h-5" aria-hidden="true" />
          View Final Report
          <ArrowRight className="w-4 h-4" aria-hidden="true" />
        </button>
        <button
          onClick={onAnalyzeNew}
          className="btn btn-ghost w-full py-3 rounded-xl"
        >
          <RotateCcw className="w-4 h-4" aria-hidden="true" />
          Analyze New Evidence
        </button>
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
