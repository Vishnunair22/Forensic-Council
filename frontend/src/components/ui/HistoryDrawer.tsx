"use client";

import React, { useEffect, useState } from "react";
import { X, History, Trash2, ShieldCheck, FileText, AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import { useRouter } from "next/navigation";

export interface HistoryItem {
  sessionId: string;
  fileName: string;
  verdict: string;
  timestamp: number;
  type: "Initial" | "Deep";
}

export function HistoryDrawer() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const loadHistory = () => {
    try {
      const stored = localStorage.getItem("forensic_history");
      if (stored) {
        setHistory(JSON.parse(stored));
      }
    } catch (e) {
      console.error("Failed to parse history", e);
    }
  };

  useEffect(() => {
    loadHistory();
    // Re-load history if it opens
  }, [isOpen]);

  const removeHistoryItem = (sessionId: string) => {
    const updated = history.filter(h => h.sessionId !== sessionId);
    setHistory(updated);
    localStorage.setItem("forensic_history", JSON.stringify(updated));
  };

  const clearAllHistory = () => {
    setHistory([]);
    localStorage.setItem("forensic_history", JSON.stringify([]));
  };

  // Verdict config to match result page icons
  const getVerdictUi = (v: string) => {
    const u = (v || "").toUpperCase();
    if (u === "AUTHENTIC" || u === "CERTAIN") return { color: "text-emerald-400", dot: "bg-emerald-400", Icon: CheckCircle };
    if (u === "MANIPULATED" || u === "MANIPULATION DETECTED" || u === "LIKELY_MANIPULATED") return { color: "text-red-400", dot: "bg-red-400", Icon: AlertTriangle };
    if (u === "INCONCLUSIVE") return { color: "text-amber-400", dot: "bg-amber-400", Icon: AlertCircle };
    return { color: "text-amber-400", dot: "bg-amber-400", Icon: AlertTriangle };
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed top-1/2 right-0 -translate-y-1/2 translate-x-[2px] transition-transform hover:translate-x-0 z-40 bg-[#0d0d14] border border-violet-500/30 border-r-0 rounded-l-2xl p-3 shadow-[-4px_0_24px_rgba(139,92,246,0.15)] group"
        aria-label="Open History"
      >
        <span className="flex flex-col items-center gap-2">
           <History className="w-5 h-5 text-violet-400 group-hover:text-violet-300" />
           <span className="[writing-mode:vertical-lr] rotate-180 text-[10px] font-mono tracking-[0.2em] text-violet-400 uppercase opacity-60 group-hover:opacity-100 mt-2">History</span>
        </span>
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            />
            <motion.div
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed inset-y-0 right-0 w-80 max-w-[85vw] bg-[#08080c] border-l border-white/10 z-50 flex flex-col shadow-2xl"
            >
              <div className="flex items-center justify-between p-5 border-b border-white/5 bg-white/[0.01]">
                <h2 className="text-sm font-bold tracking-widest uppercase text-slate-300 flex items-center gap-2">
                  <History className="w-4 h-4 text-violet-400" /> Analysis History
                </h2>
                <button onClick={() => setIsOpen(false)} className="p-1 rounded-full hover:bg-white/10 text-slate-400 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {history.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-500 opacity-60">
                    <History className="w-10 h-10 mb-3" />
                    <p className="text-xs uppercase tracking-widest font-mono">No History Found</p>
                  </div>
                ) : (
                  history.map((item) => {
                    const ui = getVerdictUi(item.verdict);
                    const UIcon = ui.Icon;
                    return (
                      <div key={item.sessionId} className="relative group bg-white/[0.03] border border-white/[0.06] rounded-xl p-3 hover:border-violet-500/30 transition-colors overflow-hidden">
                        <div className="flex justify-between items-start mb-2 pr-6">
                           <div className="flex items-center gap-2 overflow-hidden">
                              <FileText className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                              <span className="text-xs font-semibold text-slate-300 truncate" title={item.fileName}>{item.fileName}</span>
                           </div>
                        </div>

                        <div className="space-y-1.5">
                           <div className="flex items-center gap-1.5">
                              <UIcon className={clsx("w-3.5 h-3.5 shrink-0", ui.color)} />
                              <span className={clsx("text-[10px] font-bold uppercase tracking-wide", ui.color)}>
                                {item.verdict.replace(/_/g, " ")}
                              </span>
                           </div>
                           <div className="flex justify-between items-center text-[9px] text-slate-500 font-mono">
                              <span className="px-1.5 py-0.5 rounded border border-white/10 bg-white/5 uppercase">{item.type} Analysis</span>
                              <span>{new Date(item.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                           </div>
                        </div>

                        {/* Inline delete individual element */}
                        <button
                          onClick={() => removeHistoryItem(item.sessionId)}
                          className="absolute top-2.5 right-2.5 p-1.5 rounded-full hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                          title="Clear Item"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })
                )}
              </div>

              {history.length > 0 && (
                <div className="p-4 border-t border-white/5 bg-white/[0.01]">
                  <button
                    onClick={clearAllHistory}
                    className="w-full py-2.5 rounded-lg border border-red-500/20 bg-red-500/10 text-red-400 hover:bg-red-500/20 text-xs font-bold uppercase tracking-widest transition-colors flex items-center justify-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" /> Clear All History
                  </button>
                </div>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
